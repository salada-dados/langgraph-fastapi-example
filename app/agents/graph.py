from functools import lru_cache

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agents.state import AgentState
from app.core.config import settings

SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "Use the get_weather tool whenever the user asks about current weather."
)


# --- Tool -------------------------------------------------------------------

@tool
async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
            geo = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1},
            )
            geo.raise_for_status()
            results = geo.json().get("results")
            if not results:
                return f"Could not find a city called '{city}'."
            place = results[0]

            forecast = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,wind_speed_10m",
                },
            )
            forecast.raise_for_status()
            current = forecast.json()["current"]
    except httpx.HTTPError as exc:
        # Return the failure as text so the LLM can tell the user, instead of crashing the graph.
        return f"Weather service unavailable: {exc}"

    return (
        f"{place['name']}, {place.get('country', '')}: "
        f"{current['temperature_2m']}°C, wind {current['wind_speed_10m']} km/h."
    )


TOOLS = [get_weather]


# --- LLM --------------------------------------------------------------------

@lru_cache
def get_llm():
    # Created lazily so the app can import (and the graph compile) without an API key.
    kwargs = {}
    if settings.LLM_TEMPERATURE is not None:
        kwargs["temperature"] = settings.LLM_TEMPERATURE
    llm = init_chat_model(settings.LLM_MODEL, **kwargs)
    return llm.bind_tools(TOOLS)


# --- Graph ------------------------------------------------------------------

async def agent(state: AgentState) -> dict:
    response = await get_llm().ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
    return {"messages": [response]}


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(TOOLS))

    builder.add_edge(START, "agent")
    # If the LLM asked for a tool, go to "tools"; otherwise finish.
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    # No checkpointer: each request is independent (no memory between calls).
    return builder.compile()


graph = build_graph()
