try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import difflib
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pandas as pd
import requests
import streamlit as st

from agent import run_agent

st.set_page_config(page_title="Kisan Advisor", page_icon="🌾", layout="centered")

st.markdown(
    """
    <style>
    #MainMenu, footer {visibility: hidden;}
    .stApp {background: linear-gradient(180deg, #f3f7ea 0%, #e3efdb 100%);}
    .block-container {max-width: 560px; padding-top: 1.2rem; padding-bottom: 3rem;}
    h1, h2, h3 {color: #1f5138;}
    .hero {background: #ffffff; border-radius: 24px; padding: 18px 20px; margin-bottom: 14px;
           box-shadow: 0 4px 18px rgba(31, 81, 56, 0.10);}
    .hero .hi {color: #6b8a76; font-size: 0.9rem;}
    .hero .name {color: #1f5138; font-size: 1.7rem; font-weight: 700; margin: 2px 0;}
    .hero .sub {color: #6b8a76; font-size: 0.95rem;}
    .grid {display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 10px 0 16px 0;}
    .tile {border-radius: 20px; padding: 14px; color: #fff; min-height: 96px;}
    .tile .k {font-size: 0.8rem; opacity: 0.92;}
    .tile .v {font-size: 1.45rem; font-weight: 700; margin-top: 4px; line-height: 1.15;}
    .tile .s {font-size: 0.75rem; opacity: 0.92; margin-top: 2px;}
    .t1 {background: #4f9a6f;} .t2 {background: #5a86a8;} .t3 {background: #eea23a;} .t4 {background: #8c76c8;}
    div[data-testid="stVerticalBlockBorderWrapper"] {background: #ffffff; border-radius: 22px;
           box-shadow: 0 3px 14px rgba(31, 81, 56, 0.08); border: none;}
    div[data-baseweb="select"] > div, textarea, input {border-radius: 14px !important;}
    div.stButton > button {border-radius: 16px; font-weight: 600; padding: 0.55rem 1rem;}
    div.stButton > button[kind="primary"] {background-color: #2f6b4f; border: none; color: #fff;}
    div.stButton > button[kind="primary"]:disabled {background-color: #b9cdbf;}
    .stTabs [data-baseweb="tab-list"] {gap: 6px;}
    .stTabs [data-baseweb="tab"] {border-radius: 14px; padding: 6px 14px; background: rgba(255,255,255,0.6);}
    .stTabs [aria-selected="true"] {background: #2f6b4f !important; color: #fff !important;}
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {display: none;}
    div[data-testid="stMetric"] {background: #f6faf2; border-radius: 14px; padding: 8px 12px;}
    </style>
    """,
    unsafe_allow_html=True,
)

IST = timezone(timedelta(hours=5, minutes=30))
hour = datetime.now(IST).hour
greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
st.markdown(
    f"""<div class="hero"><div class="hi">{greet} 👋</div>
    <div class="name">Kisan Advisor 🌾</div>
    <div class="sub">Live weather and mandi prices, in your language.</div></div>""",
    unsafe_allow_html=True,
)

LANGS = ["Same as my question", "English", "Hindi", "Marathi", "Tamil", "Telugu", "Kannada", "Bengali"]
VOICE_LANGS = LANGS[1:]
READ_ALOUD = " Answer in at most 3 short sentences (under 45 words), decision first, because it will be read aloud."

# ---------- data: dropdown options come from the live Mandi Price API ----------
BASE = "https://mandi-api.onrender.com/v1"


def _get(path, **params):
    r = requests.get(f"{BASE}{path}", params={k: v for k, v in params.items() if v}, timeout=60)
    r.raise_for_status()
    return r.json()


def _items(j):
    d = j.get("data", j) if isinstance(j, dict) else j
    if isinstance(d, dict):
        for k in ("states", "commodities", "markets", "items", "results"):
            if isinstance(d.get(k), list):
                return d[k]
        return []
    return d if isinstance(d, list) else []


def _names(j):
    out = set()
    for x in _items(j):
        if isinstance(x, str):
            out.add(x.strip())
        elif isinstance(x, dict):
            v = next((x[k] for k in ("state", "commodity", "name", "market", "value", "label")
                      if isinstance(x.get(k), str)), None) or next((v for v in x.values() if isinstance(v, str)), None)
            if v:
                out.add(v.strip())
    return sorted(n for n in out if n)


@st.cache_data(ttl=3600, show_spinner=False)
def get_states():
    return _names(_get("/states"))


@st.cache_data(ttl=3600, show_spinner=False)
def get_crops(state):
    return _names(_get("/commodities", state=state))


@st.cache_data(ttl=1800, show_spinner=False)
def get_districts(state):
    rows = [r for r in _items(_get("/prices", state=state)) if isinstance(r, dict) and r.get("district")]
    return sorted({r["district"].strip() for r in rows})


def match(value, options):
    """Match a spoken name to an option: exact, then close spelling, then containment."""
    if not value or not options:
        return None
    low = {o.lower(): o for o in options}
    v = str(value).strip().lower()
    if v in low:
        return low[v]
    hit = difflib.get_close_matches(v, list(low), n=1, cutoff=0.6)
    if hit:
        return low[hit[0]]
    sub = [o for k, o in low.items() if v in k or k in v]
    return sub[0] if len(sub) == 1 else None


# ---------- voice helpers ----------
SCRIPTS = [("hi", 0x0900, 0x097F), ("bn", 0x0980, 0x09FF), ("pa", 0x0A00, 0x0A7F), ("gu", 0x0A80, 0x0AFF),
           ("ta", 0x0B80, 0x0BFF), ("te", 0x0C00, 0x0C7F), ("kn", 0x0C80, 0x0CFF), ("ml", 0x0D00, 0x0D7F)]
LANG_CODE = {"english": "en", "hindi": "hi", "tamil": "ta", "marathi": "mr"}
PROMPTS = {
    "start": {"en": "Please say your state, your district or village, and your crop.",
              "hi": "कृपया अपना राज्य, ज़िला या गाँव, और फसल बताइए।",
              "ta": "உங்கள் மாநிலம், மாவட்டம் அல்லது ஊர், மற்றும் பயிரைச் சொல்லுங்கள்.",
              "mr": "कृपया तुमचे राज्य, जिल्हा किंवा गाव आणि पीक सांगा."},
    "state": {"en": "Please say only your state.", "hi": "कृपया सिर्फ़ अपना राज्य बताइए।",
              "ta": "உங்கள் மாநிலத்தை மட்டும் சொல்லுங்கள்.", "mr": "कृपया फक्त तुमचे राज्य सांगा."},
    "place": {"en": "Please say only your district or village.", "hi": "कृपया सिर्फ़ अपना ज़िला या गाँव बताइए।",
              "ta": "உங்கள் மாவட்டம் அல்லது ஊரை மட்டும் சொல்லுங்கள்.", "mr": "कृपया फक्त तुमचा जिल्हा किंवा गाव सांगा."},
    "crop": {"en": "Please say only your crop.", "hi": "कृपया सिर्फ़ अपनी फसल बताइए।",
             "ta": "உங்கள் பயிரை மட்டும் சொல்லுங்கள்.", "mr": "कृपया फक्त तुमचे पीक सांगा."},
    "lang": {"en": "Which language would you like the answer in?", "hi": "आप जवाब किस भाषा में चाहते हैं?",
             "ta": "எந்த மொழியில் பதில் வேண்டும்?", "mr": "तुम्हाला उत्तर कोणत्या भाषेत हवे आहे?"},
}


def speech_lang(text, whisper_lang=""):
    counts = {code: sum(lo <= ord(ch) <= hi for ch in text) for code, lo, hi in SCRIPTS}
    best = max(counts, key=counts.get)
    if counts[best] < 5:
        return "en"
    if best == "hi" and whisper_lang.lower().startswith("marathi"):
        return "mr"
    return best


def speech_text(text):
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("|")]
    t = re.sub(r"[*#`_>|]+", " ", " ".join(lines))
    t = re.sub(r"\s+-\s+", ". ", t)
    return re.sub(r"\s+", " ", t).strip()[:1500]


def make_audio(text, whisper_lang=""):
    from gtts import gTTS  # imported here so the app still starts if gTTS is missing
    buf = BytesIO()
    gTTS(text=speech_text(text), lang=speech_lang(text, whisper_lang)).write_to_fp(buf)
    return buf.getvalue()


def try_audio(text, lang_hint=""):
    try:
        return make_audio(text, lang_hint)
    except Exception:
        return None


def _client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ["LLM_BASE_URL"], timeout=60)


def transcribe(audio_file):
    resp = _client().audio.transcriptions.create(
        model=os.getenv("STT_MODEL", "whisper-large-v3"),
        file=("voice.wav", audio_file.getvalue()),
        response_format="verbose_json",
    )
    return (resp.text or "").strip(), (getattr(resp, "language", "") or "")


def extract(text, hint=None):
    """Ask the AI to pull state / place / crop / language out of what the farmer said."""
    system = ("You extract details from a farmer's spoken words in any Indian language. Reply with ONLY a JSON "
              'object with keys "state", "place", "crop", "language". Use English names: translate or '
              "transliterate (for example தஞ்சாவூர் -> Thanjavur, प्याज़ -> Onion, தமிழ்நாடு -> Tamil Nadu). "
              '"place" is a district, town or village. "language" must be one of: English, Hindi, Marathi, '
              "Tamil, Telugu, Kannada, Bengali, or null. Use null for anything not clearly said. Never guess.")
    user = (f'The farmer was asked only for their {hint}. They said: "{text}"' if hint
            else f'The farmer said: "{text}"')
    r = _client().chat.completions.create(model=os.environ["LLM_MODEL"], temperature=0,
                                          messages=[{"role": "system", "content": system},
                                                    {"role": "user", "content": user}])
    m = re.search(r"\{.*\}", r.choices[0].message.content or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    clean_v = lambda v: None if (not v or str(v).strip().lower() in ("null", "none", "")) else str(v).strip()
    return {k: clean_v(d.get(k)) for k in ("state", "place", "crop", "language")}


# ---------- agent helpers ----------
def find(trace, tool):
    for t in reversed(trace):
        if t["tool"] == tool and isinstance(t["result"], dict) and "error" not in t["result"]:
            return t["result"]
    return None


def clean(text):
    kept = [ln for ln in text.splitlines() if not ln.strip().lstrip("*#_> -").lower().startswith("sources")]
    return "\n".join(kept).strip()


def ask_agent(prompt):
    trace = []
    with st.spinner("Fetching live weather and mandi prices, then thinking..."):
        try:
            answer = clean(run_agent(prompt, trace))
        except Exception as e:
            answer = f"Something went wrong while contacting the AI service: {e}"
    return answer, trace


def build_query(state, place, district, crop, question, lang):
    q = f"State: {state}. "
    if district:
        q += f"District: {district}. Town for the weather forecast: {district}. "
    elif place:
        q += f"Place: {place} (use it for the weather forecast; use state-wide mandi prices). "
    q += f"Crop: {crop}. Question: {question or 'Should I sell now or wait?'} "
    q += "(Use the district for mandi prices. If the place cannot be geocoded, try another English spelling or the nearest large town.)"
    if lang and lang != "Same as my question":
        q += f" Reply in {lang}."
    return q + READ_ALOUD


def run_and_store(q, lang_hint=""):
    answer, trace = ask_agent(q)
    st.session_state["last"] = {"q": q, "answer": answer, "trace": trace, "lang": lang_hint,
                                "audio": try_audio(answer, lang_hint), "autoplay": True,
                                "followups": [], "n": 0}


# ---------- voice assistant state ----------
def new_va():
    return {"stage": "idle", "asking": None, "raw": {"state": None, "place": None, "crop": None},
            "slots": {"state": None, "district": None, "place": None, "crop": None},
            "lang": None, "pl": "en", "fails": {}, "prompt": "", "audio": None, "autoplay": False, "n": 0}


def say(va, key):
    va["prompt"] = PROMPTS[key].get(va["pl"], PROMPTS[key]["en"])
    va["audio"] = try_audio(va["prompt"])
    va["autoplay"] = True


def va_resolve(va):
    """Fill what we can from what was said. Returns the next thing to ask for, or None when complete."""
    raw, s, fails = va["raw"], va["slots"], va["fails"]
    if not s["state"]:
        m = match(raw["state"], get_states())
        if not m:
            raw["state"] = None
            return "state"
        s["state"] = m
    if not s["place"]:
        if not raw["place"]:
            return "place"
        s["place"] = raw["place"]
        s["district"] = match(raw["place"], get_districts(s["state"]))
    if not s["crop"]:
        if not raw["crop"]:
            return "crop"
        m = match(raw["crop"], get_crops(s["state"]))
        if m:
            s["crop"] = m
        elif fails.get("crop", 0) >= 1:
            s["crop"] = raw["crop"].title()
        else:
            fails["crop"] = fails.get("crop", 0) + 1
            raw["crop"] = None
            return "crop"
    return None


def va_process(va, rec):
    text, wl = transcribe(rec)
    if not text:
        st.warning("I could not hear anything. Please try again.")
        return
    va["pl"] = LANG_CODE.get(wl.lower(), va["pl"])
    va["heard"] = text
    if va["stage"] == "collect":
        data = extract(text, va["asking"])
        for k in ("state", "place", "crop"):
            if data.get(k):
                va["raw"][k] = data[k]
        nxt = va_resolve(va)
        if nxt:
            va["asking"] = nxt
            say(va, nxt)
        else:
            va["stage"], va["asking"] = "lang", "language"
            say(va, "lang")
    else:  # asking for the answer language
        lang = match(extract(text, "language").get("language"), VOICE_LANGS)
        if lang:
            va["lang"], va["stage"] = lang, "done"
            s = va["slots"]
            run_and_store(build_query(s["state"], s["place"], s["district"], s["crop"], "", lang), lang)
            va["prompt"], va["audio"] = "Here is your advice. You can ask a follow-up below.", None
        else:
            say(va, "lang")
    va["n"] += 1


# ---------- the two ways to ask ----------
tab_choose, tab_voice = st.tabs(["🗂  Choose", "🎙  Talk to me"])

with tab_choose:
    with st.container(border=True):
        try:
            with st.spinner("Loading states (the first load can take up to a minute)..."):
                states = get_states()
        except Exception:
            states = []
            st.warning("Could not load the list of states right now. Please try again in a minute.")
        state = st.selectbox("🗺 State", states, index=None, placeholder="Select your state", key="c_state")
        try:
            districts = get_districts(state) if state else []
        except Exception:
            districts = []
            st.warning("Could not load districts right now.")
        district = st.selectbox("📍 District / village", districts, index=None,
                                placeholder="Select your district", key="c_district", disabled=not state)
        try:
            crops = get_crops(state) if state else []
        except Exception:
            crops = []
            st.warning("Could not load crops right now.")
        crop = st.selectbox("🌱 Crop", crops, index=None, placeholder="Select your crop",
                            key="c_crop", disabled=not district)
        question = st.text_area("💬 Your question (optional)", value="", height=80,
                                placeholder="For example: Should I sell now or wait?")
        lang = st.selectbox("🗣 Answer language", LANGS, index=None, placeholder="Same as my question", key="c_lang")
        go = st.button("Get advice", type="primary", use_container_width=True,
                       disabled=not (state and district and crop))
    if go:
        run_and_store(build_query(state, None, district, crop, question.strip(), lang), lang or "")

with tab_voice:
    va = st.session_state.setdefault("va", new_va())
    with st.container(border=True):
        if va["stage"] == "idle":
            st.write("Speak instead of typing. I will ask for anything I did not catch, then read the advice aloud.")
            if st.button("🎙 Start", type="primary", use_container_width=True, key="va_start"):
                va["stage"] = "collect"
                say(va, "start")
                st.rerun()
        else:
            with st.chat_message("assistant"):
                st.write(va["prompt"])
                if va["audio"]:
                    st.audio(va["audio"], format="audio/mp3", autoplay=va["autoplay"])
                    va["autoplay"] = False
            if va.get("heard"):
                with st.chat_message("user"):
                    st.write(va["heard"])
            if va["stage"] == "collect" and va["asking"] == "state":
                try:
                    st.caption("States available: " + ", ".join(get_states()))
                except Exception:
                    pass
            if va["stage"] != "done":
                rec = st.audio_input("Tap the mic, speak, then tap stop", key=f"va_rec_{va['n']}")
                if st.button("Send", type="primary", use_container_width=True, key=f"va_send_{va['n']}"):
                    if rec is None:
                        st.warning("Please record your answer first.")
                    else:
                        try:
                            with st.spinner("Listening..."):
                                va_process(va, rec)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Something went wrong: {e}")
            if st.button("↺ Start over", use_container_width=True, key="va_reset"):
                st.session_state["va"] = new_va()
                st.session_state.pop("last", None)
                st.rerun()

# ---------- results (shared by both ways of asking) ----------
last = st.session_state.get("last")
if last:
    w = find(last["trace"], "get_weather")
    p = find(last["trace"], "get_mandi_prices")
    t1 = t2 = t3 = t4 = ("—", "")
    if w and w.get("forecast"):
        d0 = w["forecast"][0]
        t1 = (f"{d0['max_c']}°C", f"low {d0['min_c']}°C today")
        t2 = (f"{d0['rain_prob_pct']}%", f"{d0['rain_mm']} mm expected today")
    if p and p.get("markets"):
        t3 = (f"₹{p['avg_modal_price_rs_per_quintal']}", f"per quintal · {p['latest_data_date']}")
        t4 = (f"₹{p['highest_modal']['price']}", html.escape(str(p["highest_modal"]["market"])))
    st.markdown(
        f"""<div class="grid">
        <div class="tile t1"><div class="k">🌡 Temperature</div><div class="v">{t1[0]}</div><div class="s">{t1[1]}</div></div>
        <div class="tile t2"><div class="k">🌧 Rain chance</div><div class="v">{t2[0]}</div><div class="s">{t2[1]}</div></div>
        <div class="tile t3"><div class="k">🧺 Average price</div><div class="v">{t3[0]}</div><div class="s">{t3[1]}</div></div>
        <div class="tile t4"><div class="k">⭐ Best market</div><div class="v">{t4[0]}</div><div class="s">{t4[1]}</div></div>
        </div>""",
        unsafe_allow_html=True,
    )

    tab_advice, tab_weather, tab_price = st.tabs(["🧑‍🌾 Advice", "🌦 Weather", "🧺 Mandi prices"])
    with tab_advice:
        st.markdown(last["answer"])
        if last["audio"]:
            st.audio(last["audio"], format="audio/mp3", autoplay=last["autoplay"])
            last["autoplay"] = False
        else:
            st.caption("Voice playback is not available right now.")

    with tab_weather:
        if w and w.get("forecast"):
            df = pd.DataFrame(w["forecast"]).set_index("date")
            st.caption("Temperature (°C), next 7 days")
            st.line_chart(df[["max_c", "min_c"]])
            st.caption("Expected rain (mm)")
            st.bar_chart(df["rain_mm"])
        else:
            st.info("No weather data was fetched for this question.")

    with tab_price:
        if p and p.get("markets"):
            mdf = pd.DataFrame(p["markets"]).rename(
                columns={"market": "Market", "district": "District", "min": "Min", "max": "Max", "modal": "Modal"})
            st.dataframe(mdf, hide_index=True, use_container_width=True)
            st.bar_chart(mdf.set_index("Market")["Modal"])
            st.caption(f"Prices as of {p['latest_data_date']} (Rs per quintal)")
        else:
            st.info("No mandi price data was available for this choice.")

    with st.container(border=True):
        st.subheader("💬 Ask a follow-up")
        for fu in last["followups"]:
            with st.chat_message("user"):
                st.write(fu["q"])
            with st.chat_message("assistant"):
                st.markdown(fu["a"])
                if fu["audio"]:
                    st.audio(fu["audio"], format="audio/mp3")
        n = last["n"]  # new widget keys after each question give fresh, empty inputs
        fu_text = st.text_input("Type your follow-up question", key=f"fu_text_{n}")
        fu_audio = st.audio_input("...or record it", key=f"fu_audio_{n}")
        if st.button("Ask", type="primary", key=f"fu_btn_{n}", use_container_width=True):
            fq = (fu_text or "").strip()
            if not fq and fu_audio is not None:
                try:
                    with st.spinner("Listening..."):
                        fq, _ = transcribe(fu_audio)
                except Exception as e:
                    st.error(f"Could not understand the recording: {e}")
            if not fq:
                st.warning("Please type or record your follow-up question.")
            else:
                history = "".join(f"\nFarmer asked: {f['q']}\nYou answered: {f['a']}" for f in last["followups"])
                prompt = (f"{last['q']}\n\nYour earlier advice was: {last['answer']}{history}\n\n"
                          f'The farmer now asks a follow-up: "{fq}". Answer it for the same place and crop unless they '
                          "name a different one. Only call tools again if you need new data. "
                          "Reply in the language of the follow-up question." + READ_ALOUD)
                a, _ = ask_agent(prompt)
                last["followups"].append({"q": fq, "a": a, "audio": try_audio(a, last["lang"])})
                last["n"] += 1
                st.rerun()

st.caption("Weather: Open-Meteo · Mandi prices: Agmarknet (latest reported, may be a few days old)")
