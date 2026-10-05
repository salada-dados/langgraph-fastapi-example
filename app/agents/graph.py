from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agents.state import AgentState
from app.agents.tools import TOOLS
from app.core.config import settings

SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "Use the get_weather tool whenever the user asks about current weather."
)


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
