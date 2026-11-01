"""Live-data tools for the agri advisory agent. No mock data: every function calls a real API.
If an API fails or returns nothing, we return an explicit error so the agent says so instead of guessing."""
import os
import requests

TIMEOUT = 15
MANDI_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"  # Data.gov.in: daily mandi prices (Agmarknet)


def geocode(place: str) -> dict:
    """Turn a place name in India into latitude/longitude using Open-Meteo geocoding."""
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": place, "count": 1, "country_code": "IN"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        res = r.json().get("results")
        if not res:
            return {"error": f"Could not find a location named '{place}'."}
        x = res[0]
        return {"name": x["name"], "state": x.get("admin1"), "latitude": x["latitude"],
                "longitude": x["longitude"], "source": "Open-Meteo Geocoding API"}
    except Exception as e:
        return {"error": f"Geocoding failed: {e}"}


def get_weather(latitude: float, longitude: float) -> dict:
    """7-day live forecast (rain, temperature) from Open-Meteo."""
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude, "longitude": longitude, "timezone": "auto", "forecast_days": 7,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        d = r.json()["daily"]
        days = [
            {"date": d["time"][i], "max_c": d["temperature_2m_max"][i], "min_c": d["temperature_2m_min"][i],
             "rain_mm": d["precipitation_sum"][i], "rain_prob_pct": d["precipitation_probability_max"][i]}
            for i in range(len(d["time"]))
        ]
        return {"forecast": days, "source": "Open-Meteo Forecast API"}
    except Exception as e:
        return {"error": f"Weather fetch failed: {e}"}


def _pick(rec: dict, *names):
    """Field names in the Data.gov.in feed vary in case, so try several."""
    for n in names:
        if n in rec:
            return rec[n]
    return None


def get_mandi_prices(commodity: str, state: str = "", district: str = "") -> dict:
    """Latest mandi prices (Rs/quintal) for a crop from Data.gov.in. Needs DATA_GOV_API_KEY."""
    key = os.getenv("DATA_GOV_API_KEY")
    if not key:
        return {"error": "DATA_GOV_API_KEY is not set, so mandi prices are unavailable."}
    try:
        r = requests.get(
            f"https://api.data.gov.in/resource/{MANDI_RESOURCE}",
            params={"api-key": key, "format": "json", "limit": 500,
                    "filters[commodity]": commodity.strip().title()},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        records = r.json().get("records", [])
        rows = []
        for rec in records:
            st = str(_pick(rec, "state", "State") or "")
            di = str(_pick(rec, "district", "District") or "")
            if state and state.lower() not in st.lower():
                continue
            if district and district.lower() not in di.lower():
                continue
            rows.append({
                "market": _pick(rec, "market", "Market"), "district": di, "state": st,
                "date": _pick(rec, "arrival_date", "Arrival_Date"),
                "min": _pick(rec, "min_price", "Min_Price"),
                "max": _pick(rec, "max_price", "Max_Price"),
                "modal": _pick(rec, "modal_price", "Modal_Price"),
            })
        if not rows:
            return {"error": f"No recent mandi records found for {commodity} "
                             f"(state='{state}', district='{district}'). Try a wider area or another crop."}
        return {"prices_rs_per_quintal": rows[:15], "source": "Data.gov.in / Agmarknet daily mandi prices"}
    except Exception as e:
        return {"error": f"Mandi price fetch failed: {e}"}


# Tool schemas in OpenAI function-calling format (works with Gemini and Groq OpenAI-compatible endpoints)
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "geocode", "description": "Find latitude/longitude of a village, town or district in India.",
        "parameters": {"type": "object", "properties": {"place": {"type": "string"}}, "required": ["place"]}}},
    {"type": "function", "function": {
        "name": "get_weather", "description": "Get the live 7-day weather forecast for coordinates.",
        "parameters": {"type": "object", "properties": {
            "latitude": {"type": "number"}, "longitude": {"type": "number"}},
            "required": ["latitude", "longitude"]}}},
    {"type": "function", "function": {
        "name": "get_mandi_prices",
        "description": "Get latest mandi (market) prices in Rs/quintal for a crop, optionally filtered by state/district.",
        "parameters": {"type": "object", "properties": {
            "commodity": {"type": "string", "description": "English crop name, e.g. Tomato, Onion, Wheat"},
            "state": {"type": "string"}, "district": {"type": "string"}},
            "required": ["commodity"]}}},
]

TOOL_FUNCS = {"geocode": geocode, "get_weather": get_weather, "get_mandi_prices": get_mandi_prices}
