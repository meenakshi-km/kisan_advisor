"""Live-data tools for the agri advisory agent. No mock data: every function calls a real API.
If an API fails or returns nothing, we return an explicit error so the agent says so instead of guessing."""
import os
import requests

TIMEOUT = 15
MANDI_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"  # Data.gov.in: daily mandi prices (Agmarknet)
MANDI_API = "https://mandi-api.onrender.com/v1/prices"
DATAGOV_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

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


def _summarize(rows, district=""):
    """rows: list of dicts with state, district, market, arrival_date, min_price, max_price, modal_price."""
    rows = [r for r in rows if r.get("modal_price") is not None and r.get("arrival_date")]
    if not rows:
        return None
    latest = max(r["arrival_date"] for r in rows)
    day = [r for r in rows if r["arrival_date"] == latest]
    note = ""
    if district:
        local = [r for r in day if district.lower() in str(r.get("district", "")).lower()]
        if local:
            day = local
        else:
            note = f"No records for district '{district}' on {latest}; showing the wider state."
    day.sort(key=lambda r: r["modal_price"], reverse=True)
    modal = [r["modal_price"] for r in day]
    out = {
        "latest_data_date": latest,
        "markets_reporting": len(day),
        "avg_modal_price_rs_per_quintal": round(sum(modal) / len(modal)),
        "highest_modal": {"market": day[0]["market"].strip(), "district": day[0]["district"], "price": day[0]["modal_price"]},
        "lowest_modal": {"market": day[-1]["market"].strip(), "district": day[-1]["district"], "price": day[-1]["modal_price"]},
        "markets": [
            {"market": r["market"].strip(), "district": r["district"], "min": r["min_price"],
             "max": r["max_price"], "modal": r["modal_price"]}
            for r in day[:8]
        ],
    }
    if note:
        out["note"] = note
    return out
 
 
def _from_wrapper(commodity, state):
    r = requests.get(MANDI_API, params={"state": state, "commodity": commodity}, timeout=60)
    r.raise_for_status()
    return r.json().get("data", [])
 
 
def _from_datagov(commodity, state):
    key = os.getenv("DATA_GOV_API_KEY")
    if not key:
        raise RuntimeError("DATA_GOV_API_KEY not set")
    r = requests.get(DATAGOV_URL, params={"api-key": key, "format": "json", "limit": 500,
                                          "filters[commodity]": commodity}, timeout=30)
    r.raise_for_status()
    rows = []
    for x in r.json().get("records", []):
        if state and state.lower() not in str(x.get("state") or x.get("State") or "").lower():
            continue
        rows.append({"state": x.get("state") or x.get("State"), "district": x.get("district") or x.get("District") or "",
                     "market": x.get("market") or x.get("Market") or "", "arrival_date": x.get("arrival_date") or x.get("Arrival_Date"),
                     "min_price": x.get("min_price") or x.get("Min_Price"), "max_price": x.get("max_price") or x.get("Max_Price"),
                     "modal_price": x.get("modal_price") or x.get("Modal_Price")})
    return rows
 
 
def get_mandi_prices(commodity: str, state: str = "", district: str = "") -> dict:
    """Latest mandi prices (Rs/quintal). Tries the keyless wrapper first, then Data.gov.in."""
    commodity = commodity.strip().title()
    errors = []
    for name, fn in (("Mandi Price API (Agmarknet data)", _from_wrapper), ("Data.gov.in Agmarknet", _from_datagov)):
        try:
            result = _summarize(fn(commodity, state.strip().title()), district.strip())
            if result:
                result["source"] = name
                return result
            errors.append(f"{name}: no records")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
    return {"error": f"No mandi prices available for {commodity} in '{state}'. Tried: {'; '.join(errors)}."}

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
