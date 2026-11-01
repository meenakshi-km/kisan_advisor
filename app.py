import re
 
import pandas as pd
import requests
import streamlit as st
 
from agent import run_agent
 
st.set_page_config(page_title="Kisan Advisor", page_icon="🌾", layout="centered")
 
st.markdown(
    """
    <style>
    .stApp {background-color: #eaf5e4;}
    h1, h2, h3 {color: #1b5e20;}
    div.stButton > button[kind="primary"] {background-color: #2e7d32; border: none; font-weight: 600;}
    div[data-testid="stMetric"] {background: #ffffff; border-radius: 12px; padding: 10px 14px;}
    </style>
    """,
    unsafe_allow_html=True,
)
 
st.title("🌾 Kisan Advisor")
st.write("Pick your state, crop and town to get advice based on live weather and the latest mandi prices.")
 
LANGS = ["Same as my question", "English", "Hindi", "Marathi", "Tamil", "Telugu", "Kannada", "Bengali"]
 
# --- helpers: dropdown options come from the live Mandi Price API, so every choice has data ---
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
 
 
def town_name(market, district):
    """Turn a mandi name like 'APMC Lasalgaon' or 'Lasalgaon(Niphad)' into a town name for the weather lookup."""
    if re.search(r"co-?op|society|ltd|company|producer|dist ", market, re.I):
        return district
    t = re.sub(r"\(.*?\)", "", market)
    t = re.sub(r"\bAPMC\b", "", t, flags=re.I).strip(" ,-")
    return t or district
 
 
@st.cache_data(ttl=3600, show_spinner=False)
def get_states():
    return _names(_get("/states"))
 
 
@st.cache_data(ttl=3600, show_spinner=False)
def get_crops(state):
    return _names(_get("/commodities", state=state))
 
 
@st.cache_data(ttl=1800, show_spinner=False)
def get_towns(state, crop):
    """(market, district) pairs that reported a price for this crop on the latest available date."""
    rows = [r for r in _items(_get("/prices", state=state, commodity=crop))
            if isinstance(r, dict) and r.get("market") and r.get("district") and r.get("arrival_date")]
    if not rows:
        return []
    latest = max(r["arrival_date"] for r in rows)
    return sorted({(r["market"].strip(), r["district"].strip()) for r in rows if r["arrival_date"] == latest},
                  key=lambda x: (x[1], x[0]))
# --- end helpers ---
 
try:
    with st.spinner("Loading available states (the first load can take up to a minute)..."):
        states = get_states()
except Exception:
    states = []
if not states:
    st.warning("Could not load the list of states right now. Showing a default; please try again in a minute.")
    states = ["Maharashtra"]
 
state = st.selectbox("🗺 State", states)
 
try:
    with st.spinner("Loading crops..."):
        crops = get_crops(state)
except Exception:
    crops = []
if not crops:
    st.warning("Could not load crops for this state right now.")
    crops = ["Onion"]
 
crop = st.selectbox("🌱 Crop", crops)
 
try:
    with st.spinner("Finding towns with prices for this crop..."):
        towns = get_towns(state, crop)
except Exception:
    towns = []
if not towns:
    st.info("No recent price records for this crop in this state. Try another crop.")
    st.stop()
 
labels = {f"{m} ({d})": (m, d) for m, d in towns}
town_label = st.selectbox("📍 Town / market (district)", list(labels))
market, district = labels[town_label]
 
question = st.text_area("💬 Your question (any language)", "Should I sell my crop this week or wait?", height=80)
lang = st.selectbox("🗣 Reply language", LANGS)
 
go = st.button("Get advice", type="primary", use_container_width=True)
 
 
def find(trace, tool):
    for t in reversed(trace):
        if t["tool"] == tool and isinstance(t["result"], dict) and "error" not in t["result"]:
            return t["result"]
    return None
 
 
def clean(text):
    """Drop any trailing 'Sources' line the model adds, to keep the answer short."""
    kept = [ln for ln in text.splitlines() if not ln.strip().lstrip("*#_> -").lower().startswith("sources")]
    return "\n".join(kept).strip()
 
 
if go:
    town = town_name(market, district)
    q = (f"State: {state}. District: {district}. Town for the weather forecast: {town}. "
         f"Nearest mandi: {market}. Crop: {crop}. Question: {question} "
         f"(Use the district for mandi prices. If the town cannot be geocoded, use the district name instead.)")
    if lang != "Same as my question":
        q += f" Reply in {lang}."
    trace = []
    with st.spinner("Fetching live weather and mandi prices, then thinking..."):
        try:
            answer = run_agent(q, trace)
        except Exception as e:
            answer = f"Something went wrong while contacting the AI service: {e}"
 
    tab_advice, tab_weather, tab_price = st.tabs(["🧑‍🌾 Advice", "🌦 Weather", "🧺 Mandi prices"])
 
    with tab_advice:
        st.markdown(clean(answer))
 
    with tab_weather:
        w = find(trace, "get_weather")
        if w and w.get("forecast"):
            df = pd.DataFrame(w["forecast"]).set_index("date")
            today = df.iloc[0]
            m1, m2, m3 = st.columns(3)
            m1.metric("Today max", f"{today['max_c']} °C")
            m2.metric("Today min", f"{today['min_c']} °C")
            m3.metric("Rain chance", f"{today['rain_prob_pct']} %")
            st.caption("Temperature (°C), next 7 days")
            st.line_chart(df[["max_c", "min_c"]])
            st.caption("Expected rain (mm)")
            st.bar_chart(df["rain_mm"])
        else:
            st.info("No weather data was fetched for this question.")
 
    with tab_price:
        p = find(trace, "get_mandi_prices")
        if p and p.get("markets"):
            a, b, c = st.columns(3)
            a.metric("Average (Rs/quintal)", p["avg_modal_price_rs_per_quintal"])
            b.metric("Highest", p["highest_modal"]["price"], p["highest_modal"]["market"], delta_color="off")
            c.metric("Lowest", p["lowest_modal"]["price"], p["lowest_modal"]["market"], delta_color="off")
            mdf = pd.DataFrame(p["markets"]).rename(
                columns={"market": "Market", "district": "District", "min": "Min", "max": "Max", "modal": "Modal"}
            )
            st.dataframe(mdf, hide_index=True, use_container_width=True)
            st.bar_chart(mdf.set_index("Market")["Modal"])
            st.caption(f"Prices as of {p['latest_data_date']} (Rs per quintal)")
        else:
            st.info("No mandi price data was available for this choice.")
 
st.caption("Weather: Open-Meteo · Mandi prices: Agmarknet (latest reported, may be a few days old)")
 
