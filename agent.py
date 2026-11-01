"""Manual tool-calling agent loop. Works with any OpenAI-compatible endpoint (Gemini, Groq, ...)."""
import json
import os
from openai import OpenAI
from tools import TOOL_SCHEMAS, TOOL_FUNCS

SYSTEM_PROMPT = """You are a farm advisory assistant for Indian farmers.
Rules:
1. To answer, call tools to get LIVE data: geocode the place, then get_weather, and get_mandi_prices for the crop.
2. Use ONLY numbers returned by tools. Never invent prices, temperatures or rainfall.
3. If a tool returns an error or no data, say so plainly and give advice only from the data you do have.
4. Give concrete, crop-level actions for the next 7 days (irrigate/hold, spray/avoid spraying, harvest timing, sell now vs wait).
5. End with a 'Sources' line naming each tool/API you used, with data dates where available.
6. Reply in the same language the farmer used. Keep it short and simple."""

MAX_STEPS = 6


def make_client():
    return OpenAI(api_key=os.environ["LLM_API_KEY"],
                  base_url=os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"))


def run_agent(question: str, trace: list | None = None) -> str:
    """Run the agent. `trace` (a list) is filled with tool calls so the UI can show the reasoning steps."""
    client = make_client()
    model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    for _ in range(MAX_STEPS):
        resp = client.chat.completions.create(model=model, messages=messages, tools=TOOL_SCHEMAS)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or "No answer produced."
        messages.append(msg)
        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                result = TOOL_FUNCS[name](**args) if name in TOOL_FUNCS else {"error": f"Unknown tool {name}"}
            except Exception as e:  # self-correction: the model sees the error and can retry
                args, result = {}, {"error": f"Tool call failed: {e}"}
            if trace is not None:
                trace.append({"tool": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:6000]})
    return "I could not finish within the step limit. Please try a simpler question."
