import json
from itertools import count

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.core.config import settings
from app.main import app
from tests.conftest import lisbon_weather

client = TestClient(app)

GENERIC_ERROR = "The agent failed to produce an answer."

FINAL_ANSWER = "It is 18.5°C in Lisbon right now."


def weather_tool_call() -> AIMessage:
    # A new message each time: the graph state assigns ids to messages in place,
    # and a reused object would replace (not append to) the earlier one.
    return AIMessage(
        content="",
        tool_calls=[{"name": "get_weather", "args": {"city": "Lisbon"}, "id": "call_1"}],
    )


def fake_model(messages):
    # disable_streaming keeps tool_calls intact: the fake model's streaming drops them.
    return GenericFakeChatModel(messages=iter(messages), disable_streaming=True)


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


# --- Input validation -------------------------------------------------------

@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
def test_empty_message_is_rejected(path):
    assert client.post(path, json={"message": ""}).status_code == 422


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
def test_message_over_max_length_is_rejected(path):
    message = "x" * (settings.MAX_MESSAGE_LENGTH + 1)
    assert client.post(path, json={"message": message}).status_code == 422


# --- Agent loop through the API (fake LLM, fake Open-Meteo) -----------------

def test_chat_runs_the_tool_and_answers(fake_llm, open_meteo):
    requests = open_meteo(lisbon_weather)
    fake_llm(fake_model([weather_tool_call(), FINAL_ANSWER]))

    response = client.post("/chat", json={"message": "Weather in Lisbon?"})

    assert response.status_code == 200
    assert response.json() == {"answer": FINAL_ANSWER}
    assert len(requests) == 2  # geocoding + forecast: the tool really ran


def test_chat_answers_without_tool(fake_llm):
    fake_llm(fake_model([AIMessage(content="LangGraph is a library for agents.")]))

    response = client.post("/chat", json={"message": "What is LangGraph?"})

    assert response.json() == {"answer": "LangGraph is a library for agents."}


def test_stream_emits_tool_tokens_and_done(fake_llm, open_meteo):
    open_meteo(lisbon_weather)
    fake_llm(fake_model([weather_tool_call(), FINAL_ANSWER]))

    response = client.post("/chat/stream", json={"message": "Weather in Lisbon?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert ("tool", {"name": "get_weather"}) in events
    assert "".join(data["content"] for name, data in events if name == "token") == FINAL_ANSWER
    assert events[-1] == ("done", {})


def test_stream_emits_one_token_per_chunk(fake_llm):
    # With streaming enabled the fake model splits its answer into several chunks.
    fake_llm(GenericFakeChatModel(messages=iter(["Hello from the agent"])))

    events = parse_sse(client.post("/chat/stream", json={"message": "Hi"}).text)

    tokens = [data["content"] for name, data in events if name == "token"]
    assert len(tokens) > 1
    assert "".join(tokens) == "Hello from the agent"
    assert events[-1] == ("done", {})


# --- Failures ----------------------------------------------------------------

class BrokenModel(GenericFakeChatModel):
    async def _agenerate(self, *args, **kwargs):
        raise RuntimeError("internal detail that must not reach the client")


def test_chat_hides_llm_errors_behind_502(fake_llm):
    fake_llm(BrokenModel(messages=iter([]), disable_streaming=True))

    response = client.post("/chat", json={"message": "Hi"})

    assert response.status_code == 502
    assert response.json() == {"detail": GENERIC_ERROR}


def test_stream_reports_llm_errors_in_band(fake_llm):
    fake_llm(BrokenModel(messages=iter([]), disable_streaming=True))

    response = client.post("/chat/stream", json={"message": "Hi"})

    assert response.status_code == 200  # headers were already sent
    assert parse_sse(response.text)[-1] == ("error", {"detail": GENERIC_ERROR})


def endless_tool_calls():
    # A misbehaving model that asks for the tool forever and never answers.
    replies = (weather_tool_call() for _ in count())
    return GenericFakeChatModel(messages=replies, disable_streaming=True)


def test_chat_stops_runaway_loop_at_recursion_limit(fake_llm, open_meteo):
    requests = open_meteo(lisbon_weather)
    fake_llm(endless_tool_calls())

    response = client.post("/chat", json={"message": "Weather in Lisbon?"})

    assert response.status_code == 502
    assert response.json() == {"detail": GENERIC_ERROR}
    # Each tool run makes 2 HTTP calls and every agent → tools round takes 2 steps,
    # so the configured limit (not LangGraph's default of 25) bounds the tool runs.
    assert len(requests) // 2 == settings.AGENT_RECURSION_LIMIT // 2


def test_stream_stops_runaway_loop_at_recursion_limit(fake_llm, open_meteo):
    open_meteo(lisbon_weather)
    fake_llm(endless_tool_calls())

    response = client.post("/chat/stream", json={"message": "Weather in Lisbon?"})

    events = parse_sse(response.text)
    assert events[-1] == ("error", {"detail": GENERIC_ERROR})
    assert sum(name == "tool" for name, _ in events) == settings.AGENT_RECURSION_LIMIT // 2
