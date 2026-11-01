import pandas as pd
import streamlit as st
from agent import run_agent
 
st.set_page_config(page_title="Kisan Advisor", page_icon="🌾", layout="centered")
 
st.markdown(
    """
    <style>
    .hero {background: linear-gradient(135deg, #2e7d32 0%, #66bb6a 100%); padding: 28px 24px;
           border-radius: 16px; color: white; margin-bottom: 18px;}
    .hero h1 {margin: 0; font-size: 2.1rem; color: white;}
    .hero p {margin: 6px 0 0 0; font-size: 1.02rem; opacity: 0.95;}
    .chip {display: inline-block; background: rgba(255,255,255,0.2); border-radius: 20px;
           padding: 3px 12px; margin: 10px 6px 0 0; font-size: 0.82rem;}
    div.stButton > button[kind="primary"] {background-color: #2e7d32; border: none; font-weight: 600;}
    </style>
    <div class="hero">
      <h1>🌾 Kisan Advisor</h1>
      <p>Live weather + live mandi prices + AI reasoning, in your language.</p>
      <span class="chip">🌦 Open-Meteo</span><span class="chip">🧺 Agmarknet mandi prices</span>
      <span class="chip">🤖 AI agent</span>
    </div>
    """,
    unsafe_allow_html=True,
)
 
CROPS = ["Onion", "Tomato", "Potato", "Wheat", "Rice", "Other"]
LANGS = ["Same as my question", "English", "Hindi", "Marathi", "Tamil", "Telugu", "Kannada", "Bengali"]
EXAMPLES = {
    "🧅 Sell onions in Nashik?": ("Nashik", "Onion", "Should I sell my onions this week or wait?"),
    "🍅 Tomatoes in Pune?": ("Pune", "Tomato", "Is it a good time to harvest and sell tomatoes?"),
}
 
st.session_state.setdefault("place", "Nashik")
st.session_state.setdefault("crop_pick", "Onion")
st.session_state.setdefault("question", "Should I sell my crop this week or wait?")
 
st.caption("Quick examples")
cols = st.columns(len(EXAMPLES))
for col, (label, (p, c, q)) in zip(cols, EXAMPLES.items()):
    if col.button(label, use_container_width=True):
        st.session_state.place, st.session_state.crop_pick, st.session_state.question = p, c, q
 
c1, c2 = st.columns(2)
place = c1.text_input("📍 Village / town / district", key="place")
crop_pick = c2.selectbox("🌱 Crop", CROPS, key="crop_pick")
other = ""
if crop_pick == "Other":
    other = st.text_input("Type your crop (English name, e.g. Garlic)")
crop = other.strip() if crop_pick == "Other" else crop_pick
 
question = st.text_area("💬 Your question (any language)", key="question", height=90)
lang = st.selectbox("🗣 Reply language", LANGS)
 
go = st.button("Get advice", type="primary", use_container_width=True)
 
 
def find(trace, tool):
    for t in reversed(trace):
        if t["tool"] == tool and isinstance(t["result"], dict) and "error" not in t["result"]:
            return t["result"]
    return None
 
 
if go:
    if not place.strip() or not crop:
        st.warning("Please enter a place and a crop.")
        st.stop()
    q = f"Location: {place}. Crop: {crop}. Question: {question}"
    if lang != "Same as my question":
        q += f" Reply in {lang}."
    trace = []
    with st.spinner("Fetching live weather and mandi prices, then thinking..."):
        try:
            answer = run_agent(q, trace)
        except Exception as e:
            answer = f"Something went wrong while contacting the AI service: {e}"
 
    tab_advice, tab_weather, tab_price, tab_steps = st.tabs(
        ["🧑‍🌾 Advice", "🌦 Weather", "🧺 Mandi prices", "🔍 Agent steps"]
    )
 
    with tab_advice:
        st.markdown(answer)
 
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
            st.caption("Source: Open-Meteo Forecast API (live)")
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
            st.caption(f"Price date: {p['latest_data_date']} · Source: {p.get('source', 'Agmarknet')}")
        else:
            st.info("No mandi price data was available for this crop and place. "
                    "The agent will say so in its advice.")
 
    with tab_steps:
        st.caption("Every tool the AI agent called, with the raw result.")
        for i, t in enumerate(trace, 1):
            with st.expander(f"Step {i}: {t['tool']}", expanded=False):
                st.write("Arguments:", t["args"])
                st.json(t["result"])
        if not trace:
            st.info("The agent answered without calling any tools.")
 
st.divider()
st.caption("Kisan Advisor · Forge Gen AI Buildathon · Prices are the latest reported to Agmarknet and may be a few days old.")
