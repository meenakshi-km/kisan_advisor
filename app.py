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

# Make sure the light theme file exists (the app creates it for you; Streamlit reads it when it starts)
try:
    _cfg = os.path.join(".streamlit", "config.toml")
    if not os.path.exists(_cfg):
        os.makedirs(".streamlit", exist_ok=True)
        with open(_cfg, "w") as _f:
            _f.write('[theme]\nbase = "light"\nprimaryColor = "#2f6b4f"\nbackgroundColor = "#cde6c0"\n'
                     'secondaryBackgroundColor = "#f1f7ea"\ntextColor = "#17321f"\n')
except Exception:
    pass

st.set_page_config(page_title="Kisan Advisor", page_icon="🌾", layout="centered")

st.markdown(
    """
    <style>
    #MainMenu, footer {visibility: hidden;}
    :root, .stApp {color-scheme: light;}
    .stApp {background: linear-gradient(180deg, #cde6c0 0%, #a6d198 100%);}
    [data-testid="stHeader"] {background: transparent;}
    [data-testid="stAudioInput"] > div {background: #f1f7ea !important; border-radius: 14px;}
    [data-testid="stChatMessage"] {background: #f1f7ea; border-radius: 16px;}
    .stApp, .stApp p, .stApp label, .stApp li, .stApp span,
    .stApp div[data-testid="stMarkdownContainer"], .stApp h1, .stApp h2, .stApp h3, .stApp h4 {color: #17321f;}
    .stApp small, .stApp [data-testid="stCaptionContainer"] {color: #35563f !important;}
    .block-container {max-width: 580px; padding-top: 1rem; padding-bottom: 3rem;}

    .hero {position: relative; overflow: hidden; background: linear-gradient(135deg, #1b5538 0%, #3f9163 100%);
           border-radius: 26px; padding: 22px 22px 16px; margin-bottom: 14px; box-shadow: 0 8px 22px rgba(23,50,31,0.28);}
    .hero::after {content: ""; position: absolute; right: -40px; top: -44px; width: 170px; height: 170px;
           border-radius: 50%; background: rgba(255,255,255,0.12);}
    .hero::before {content: ""; position: absolute; right: 50px; bottom: -70px; width: 140px; height: 140px;
           border-radius: 50%; background: rgba(255,255,255,0.08);}
    .hero, .hero * {color: #ffffff !important;}
    .hero .hi {opacity: 0.9; font-size: 0.9rem;}
    .hero .name {font-size: 1.9rem; font-weight: 800; margin: 2px 0;}
    .hero .sub {opacity: 0.93;}
    .chip {display: inline-block; background: rgba(255,255,255,0.22); border-radius: 20px;
           padding: 4px 12px; margin: 12px 6px 4px 0; font-size: 0.8rem;}
    .steps {display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px;}
    .step {background: rgba(255,255,255,0.88); border-radius: 18px; padding: 10px 6px; text-align: center;
           font-size: 0.78rem; box-shadow: 0 2px 8px rgba(23,50,31,0.12);}
    .step b {display: block; font-size: 1.3rem;}

    .grid {display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 10px 0 16px 0;}
    .tile {border-radius: 20px; padding: 14px; min-height: 100px; box-shadow: 0 4px 12px rgba(23,50,31,0.18);}
    .tile, .tile * {color: #ffffff !important;}
    .tile .k {font-size: 0.8rem; opacity: 0.95;}
    .tile .v {font-size: 1.5rem; font-weight: 800; margin-top: 4px; line-height: 1.15;}
    .tile .s {font-size: 0.75rem; opacity: 0.95; margin-top: 2px;}
    .t1 {background: linear-gradient(135deg, #2f8a5a, #56b17b);} .t2 {background: linear-gradient(135deg, #3f6f9a, #6a9cc4);}
    .t3 {background: linear-gradient(135deg, #e08a1e, #f2b247);} .t4 {background: linear-gradient(135deg, #7a5fc0, #a18ae0);}

    div[data-testid="stVerticalBlockBorderWrapper"] {background: #ffffff; border-radius: 22px; border: none;
           box-shadow: 0 4px 16px rgba(23,50,31,0.14);}
    div[data-baseweb="select"] > div, div[data-baseweb="input"], div[data-baseweb="textarea"] {
           background: #f1f7ea !important; border-radius: 14px !important; border: 1.5px solid #8fbf8c !important;}
    textarea, input {background: #f1f7ea !important; color: #17321f !important;}
    textarea::placeholder, input::placeholder {color: #6a8d73 !important; opacity: 1;}
    div[data-baseweb="select"] span, div[data-baseweb="select"] div {color: #17321f !important;}
    div[data-baseweb="popover"] ul, div[data-baseweb="popover"] li {background: #f1f7ea !important; color: #17321f !important;}

    div.stButton > button {border-radius: 16px; font-weight: 700; padding: 0.6rem 1rem; border: 2px solid #2a6b4a;
           background: #ffffff;}
    .stApp div.stButton > button[kind="primary"] {background: linear-gradient(135deg, #1f5e3f, #3f9163); border: none;}
    .stApp div.stButton > button[kind="primary"] p {color: #ffffff !important;}
    div.stButton > button:disabled {opacity: 0.5;}

    .stTabs [data-baseweb="tab-list"] {gap: 8px;}
    .stTabs [data-baseweb="tab"] {border-radius: 16px; padding: 8px 16px; background: rgba(255,255,255,0.78);}
    .stTabs [aria-selected="true"] {background: #1b5538 !important;}
    .stTabs [aria-selected="true"] p, .stTabs [aria-selected="true"] span {color: #ffffff !important;}
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {display: none;}
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
    <div class="sub">Live weather and mandi prices, explained in your language.</div>
    <span class="chip">🌦 Live weather</span><span class="chip">🧺 Mandi prices</span><span class="chip">🔊 Voice</span></div>
    <div class="steps"><div class="step"><b>1️⃣</b>Choose or speak</div>
    <div class="step"><b>2️⃣</b>We fetch live data</div><div class="step"><b>3️⃣</b>Advice you can hear</div></div>""",
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


POPULAR = ["onion", "tomato", "potato", "wheat", "rice", "maize", "soyabean", "cotton", "banana", "cabbage"]


@st.cache_data(ttl=1800, show_spinner=False)
def get_districts(state):
    """Districts with price data. One call returns only a slice of the records, so we combine the
    districts seen across the state as a whole and across its biggest crops."""
    districts = set()
    crops = safe(get_crops, state)
    big = [c for c in crops if c.lower() in POPULAR][:6]
    for crop in [None] + big:
        try:
            rows = _items(_get("/prices", state=state, commodity=crop, limit=1000))
        except Exception:
            continue
        districts |= {r["district"].strip() for r in rows if isinstance(r, dict) and r.get("district")}
    return sorted(districts)


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return []


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


def uid():
    """A number that is never reused, so widget keys never carry over old recordings or text."""
    st.session_state["_uid"] = st.session_state.get("_uid", 0) + 1
    return st.session_state["_uid"]


def sb(label, options, key, placeholder, disabled=False):
    """Selectbox that starts empty and forgets a value that is no longer one of the options."""
    options = list(options)
    if st.session_state.get(key) not in options:
        st.session_state[key] = None
    return st.selectbox(label, options, index=None, placeholder=placeholder, key=key, disabled=disabled)


# ---------- voice helpers ----------
SCRIPTS = [("hi", 0x0900, 0x097F), ("bn", 0x0980, 0x09FF), ("pa", 0x0A00, 0x0A7F), ("gu", 0x0A80, 0x0AFF),
           ("ta", 0x0B80, 0x0BFF), ("te", 0x0C00, 0x0C7F), ("kn", 0x0C80, 0x0CFF), ("ml", 0x0D00, 0x0D7F)]
LANG_CODE = {"english": "en", "hindi": "hi", "tamil": "ta", "marathi": "mr"}
PROMPTS = {
    "state": {"en": "I could not catch your state. Please record again and say only your state.",
              "hi": "मुझे आपका राज्य समझ नहीं आया। कृपया फिर से रिकॉर्ड करें और सिर्फ़ अपना राज्य बताएँ।",
              "ta": "உங்கள் மாநிலம் எனக்குப் புரியவில்லை. மீண்டும் பதிவு செய்து மாநிலத்தை மட்டும் சொல்லுங்கள்.",
              "mr": "मला तुमचे राज्य समजले नाही. कृपया पुन्हा रेकॉर्ड करा आणि फक्त राज्य सांगा."},
    "place": {"en": "I could not catch your district or village. Please record again and say only that.",
              "hi": "मुझे आपका ज़िला या गाँव समझ नहीं आया। कृपया फिर से रिकॉर्ड करें और सिर्फ़ वही बताएँ।",
              "ta": "உங்கள் மாவட்டம் அல்லது ஊர் எனக்குப் புரியவில்லை. மீண்டும் பதிவு செய்து அதை மட்டும் சொல்லுங்கள்.",
              "mr": "मला तुमचा जिल्हा किंवा गाव समजले नाही. कृपया पुन्हा रेकॉर्ड करा आणि फक्त तेच सांगा."},
    "crop": {"en": "I could not catch your crop. Please record again and say only your crop.",
             "hi": "मुझे आपकी फसल समझ नहीं आई। कृपया फिर से रिकॉर्ड करें और सिर्फ़ अपनी फसल बताएँ।",
             "ta": "உங்கள் பயிர் எனக்குப் புரியவில்லை. மீண்டும் பதிவு செய்து பயிரை மட்டும் சொல்லுங்கள்.",
             "mr": "मला तुमचे पीक समजले नाही. कृपया पुन्हा रेकॉर्ड करा आणि फक्त पीक सांगा."},
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
    """Ask the AI to pull state / place / crop / question / language out of what the farmer said."""
    system = ("You extract details from a farmer's spoken words in any Indian language. Reply with ONLY a JSON "
              'object with keys "state", "place", "crop", "question", "language". Use English names for state, '
              "place and crop: translate or transliterate (for example தஞ்சாவூர் -> Thanjavur, प्याज़ -> Onion, "
              'தமிழ்நாடு -> Tamil Nadu). "place" is a district, town or village. "question" is what the farmer wants '
              'to know, copied in the farmer\'s own words, without the place and crop names if possible. "language" '
              "must be one of: English, Hindi, Marathi, Tamil, Telugu, Kannada, Bengali, or null. Use null for "
              "anything not clearly said. Never guess.")
    user = (f'The farmer was asked to say their {hint}. They said: "{text}"' if hint
            else f'The farmer said: "{text}"')
    r = _client().chat.completions.create(model=os.environ["LLM_MODEL"], temperature=0,
                                          messages=[{"role": "system", "content": system},
                                                    {"role": "user", "content": user}])
    m = re.search(r"\{.*\}", r.choices[0].message.content or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    cv = lambda v: None if (not v or str(v).strip().lower() in ("null", "none", "")) else str(v).strip()
    return {k: cv(d.get(k)) for k in ("state", "place", "crop", "question", "language")}


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


def run_and_store(res_key, q, lang_hint=""):
    answer, trace = ask_agent(q)
    st.session_state[res_key] = {"q": q, "answer": answer, "trace": trace, "lang": lang_hint,
                                 "audio": try_audio(answer, lang_hint), "autoplay": True,
                                 "followups": [], "key": uid()}


def render_results(res_key, ns):
    """Show the tiles, advice, charts and follow-up box for one of the two tabs. Each tab has its own result."""
    last = st.session_state.get(res_key)
    if not last:
        return
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
        with st.container(border=True):
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
        st.markdown("#### 💬 Ask a follow-up")
        for fu in last["followups"]:
            with st.chat_message("user"):
                st.write(fu["q"])
            with st.chat_message("assistant"):
                st.markdown(fu["a"])
                if fu["audio"]:
                    st.audio(fu["audio"], format="audio/mp3")
        k = last["key"]  # a new key after each question gives fresh, empty inputs
        fu_text = st.text_input("Type your follow-up question", key=f"{ns}_fu_text_{k}")
        fu_audio = st.audio_input("...or record it", key=f"{ns}_fu_audio_{k}")
        if st.button("Ask", type="primary", key=f"{ns}_fu_btn_{k}", use_container_width=True):
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
                last["key"] = uid()
                st.rerun()


# ---------- voice: turn a recording into form values ----------
VOICE_FIELDS = ("v_state", "v_district", "v_crop", "v_lang")


def v_apply(data, targets):
    """Put what was heard into the form fields. Spoken names that are not in a list are kept so they can be edited."""
    ss = st.session_state
    if "state" in targets and data["state"]:
        m = match(data["state"], safe(get_states))
        if m:
            if m != ss.get("v_state"):
                ss["v_district"] = ss["v_crop"] = None
            ss["v_state"] = m
    raw = ss.setdefault("v_raw", {"place": None, "crop": None})
    if "place" in targets and data["place"]:
        raw["place"], ss["v_district"] = data["place"].title(), None
    if "crop" in targets and data["crop"]:
        raw["crop"], ss["v_crop"] = data["crop"].title(), None
    state = ss.get("v_state")
    if state:
        if raw["place"] and not ss.get("v_district"):
            ss["v_district"] = match(raw["place"], safe(get_districts, state)) or raw["place"]
        if raw["crop"] and not ss.get("v_crop"):
            ss["v_crop"] = match(raw["crop"], safe(get_crops, state)) or raw["crop"]
    if data.get("question") and (not (ss.get("v_question") or "").strip() or targets == {"state", "place", "crop"}):
        ss["v_question"] = data["question"]
    lang = match(data.get("language"), VOICE_LANGS)
    if lang:
        ss["v_lang"] = lang


def v_process(rec):
    ss = st.session_state
    text, wl = transcribe(rec)
    if not text:
        ss["v_prompt"], ss["v_prompt_audio"] = "I could not hear anything. Please try again.", None
        return
    ss["v_pl"] = LANG_CODE.get(wl.lower(), ss.get("v_pl", "en"))
    ss["v_heard"] = text
    cur = {"state": ss.get("v_state"), "place": ss.get("v_district"), "crop": ss.get("v_crop")}
    empties = [k for k in ("state", "place", "crop") if not cur[k]]
    targets = set(empties) if empties else {"state", "place", "crop"}
    hint = empties[0] if 0 < len(empties) < 3 else None
    v_apply(extract(text, hint), targets)
    missing = [k for k, f in (("state", "v_state"), ("place", "v_district"), ("crop", "v_crop")) if not ss.get(f)]
    if missing:
        msg = PROMPTS[missing[0]].get(ss["v_pl"], PROMPTS[missing[0]]["en"])
        ss["v_prompt"], ss["v_prompt_audio"], ss["v_autoplay"] = msg, try_audio(msg), True
    else:
        ss["v_prompt"] = "I found everything. Please check the details below, change anything you like, then press Get advice."
        ss["v_prompt_audio"] = None


def v_clear():
    ss = st.session_state
    for f in VOICE_FIELDS:
        ss[f] = None
    ss["v_question"] = ""
    for f in ("v_heard", "v_prompt", "v_prompt_audio", "v_raw"):
        ss.pop(f, None)
    ss.pop("res_v", None)


# ---------- the two ways to ask ----------
tab_choose, tab_voice = st.tabs(["🗂  Choose", "🎙  Talk to me"])

with tab_choose:
    with st.container(border=True):
        st.markdown("#### 🗂 Choose your details")
        try:
            with st.spinner("Loading states (the first load can take up to a minute)..."):
                states = get_states()
        except Exception:
            states = []
            st.warning("Could not load the list of states right now. Please try again in a minute.")
        c_state = sb("🗺 State", states, "c_state", "Select your state")
        c_district = sb("📍 District / village", safe(get_districts, c_state) if c_state else [], "c_district",
                        "Select your district", disabled=not c_state)
        c_crop = sb("🌱 Crop", safe(get_crops, c_state) if c_state else [], "c_crop", "Select your crop",
                    disabled=not c_district)
        c_question = st.text_area("💬 Your question (optional)", key="c_question", height=80,
                                  placeholder="For example: Should I sell now or wait?")
        c_lang = sb("🗣 Answer language", LANGS, "c_lang", "Same as my question")
        c_go = st.button("Get advice", type="primary", use_container_width=True, key="c_go",
                         disabled=not (c_state and c_district and c_crop))
    if c_go:
        run_and_store("res_c", build_query(c_state, None, c_district, c_crop, (c_question or "").strip(), c_lang),
                      c_lang or "")
    render_results("res_c", "c")

with tab_voice:
    ss = st.session_state
    if "v_key" not in ss:
        ss["v_key"] = uid()
    with st.container(border=True):
        st.markdown("#### 🎙 Tell me by voice")
        st.write("Say your **state, district or village, crop and question**. I will fill in the form below, "
                 "so you can check it and change anything before getting advice.")
        rec = st.audio_input("Tap the mic, speak, then tap stop", key=f"v_rec_{ss['v_key']}")
        b1, b2 = st.columns([3, 2])
        send = b1.button("Understand my voice", type="primary", use_container_width=True, key=f"v_send_{ss['v_key']}")
        clear = b2.button("Clear", use_container_width=True, key=f"v_clear_{ss['v_key']}")
    if send:
        if rec is None:
            st.warning("Please record your voice first.")
        else:
            try:
                with st.spinner("Listening..."):
                    v_process(rec)
                ss["v_key"] = uid()
                need_rerun = True
            except Exception as e:
                st.error(f"Something went wrong: {e}")
                need_rerun = False
            if need_rerun:
                st.rerun()
    if clear:
        v_clear()
        ss["v_key"] = uid()
        st.rerun()

    if ss.get("v_heard"):
        with st.chat_message("user"):
            st.write(ss["v_heard"])
    if ss.get("v_prompt"):
        with st.chat_message("assistant"):
            st.write(ss["v_prompt"])
            if ss.get("v_prompt_audio"):
                st.audio(ss["v_prompt_audio"], format="audio/mp3", autoplay=ss.get("v_autoplay", False))
                ss["v_autoplay"] = False

    with st.container(border=True):
        st.markdown("#### ✏️ Check and edit")
        states_v = safe(get_states)
        cur_state = ss.get("v_state")
        districts_v = safe(get_districts, cur_state) if cur_state else []
        crops_v = safe(get_crops, cur_state) if cur_state else []
        if ss.get("v_district") and ss["v_district"] not in districts_v:
            districts_v = districts_v + [ss["v_district"]]  # a spoken name that is not in the list stays selectable
        if ss.get("v_crop") and ss["v_crop"] not in crops_v:
            crops_v = crops_v + [ss["v_crop"]]
        v_state = sb("🗺 State", states_v, "v_state", "Heard from your voice, or select")
        v_district = sb("📍 District / village", districts_v, "v_district", "Heard from your voice, or select",
                        disabled=not v_state)
        v_crop = sb("🌱 Crop", crops_v, "v_crop", "Heard from your voice, or select", disabled=not v_state)
        v_question = st.text_area("💬 Your question", key="v_question", height=80,
                                  placeholder="Your question will appear here")
        v_lang = sb("🗣 Answer language", LANGS, "v_lang", "Same as my question")
        v_go = st.button("Get advice", type="primary", use_container_width=True, key="v_go",
                         disabled=not (v_state and v_district and v_crop))
    if v_go:
        in_list = v_district in safe(get_districts, v_state)
        run_and_store("res_v", build_query(v_state, None if in_list else v_district, v_district if in_list else None,
                                           v_crop, (v_question or "").strip(), v_lang), v_lang or "")
    render_results("res_v", "v")

st.caption("Weather: Open-Meteo · Mandi prices: Agmarknet (latest reported, may be a few days old)")
