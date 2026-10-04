from fastapi import FastAPI

from app.api import chat

app = FastAPI(
    title="LangGraph + FastAPI Example",
    description="A LangGraph agent with a real tool, served over HTTP and SSE.",
)

app.include_router(chat.router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
