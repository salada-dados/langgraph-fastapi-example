import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from app.agents.graph import graph
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=settings.MAX_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    answer: str


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await graph.ainvoke({"messages": [HumanMessage(request.message)]})
    except Exception:
        logger.exception("Agent failed")
        raise HTTPException(status_code=502, detail="The agent failed to produce an answer.")

    return ChatResponse(answer=result["messages"][-1].text)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_agent(message: str) -> AsyncIterator[str]:
    try:
        async for chunk, metadata in graph.astream(
            {"messages": [HumanMessage(message)]},
            stream_mode="messages",
        ):
            if isinstance(chunk, ToolMessage):
                yield sse("tool", {"name": chunk.name})
            elif metadata.get("langgraph_node") == "agent" and chunk.text:
                yield sse("token", {"content": chunk.text})
        yield sse("done", {})
    except Exception:
        # Headers are already sent at this point, so we report the error in-band.
        logger.exception("Agent failed while streaming")
        yield sse("error", {"detail": "The agent failed to produce an answer."})


@router.post("/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(stream_agent(request.message), media_type="text/event-stream")
