import streamlit as st
from agent import run_agent

st.set_page_config(page_title="Kisan Advisor", page_icon="🌾")
st.title("🌾 Kisan Advisor")
st.caption("Live weather + live mandi prices + AI reasoning. Ask in any language.")

place = st.text_input("Village / district", "Nashik")
crop = st.text_input("Crop (e.g. Tomato, Onion, Wheat)", "Tomato")
extra = st.text_area("Your question (any language)", "Should I harvest and sell this week?")

if st.button("Get advice", type="primary"):
    question = f"Location: {place}. Crop: {crop}. Question: {extra}"
    trace = []
    with st.spinner("Fetching live data and reasoning..."):
        try:
            answer = run_agent(question, trace)
        except Exception as e:
            answer = f"Something went wrong: {e}"
    st.subheader("Advice")
    st.write(answer)
    with st.expander("Agent steps (live tool calls)"):
        for t in trace:
            st.markdown(f"**{t['tool']}** `{t['args']}`")
            st.json(t["result"])
