"""Shared fixtures: a fake Open-Meteo API and a fake LLM, so tests never hit the network."""

import httpx
import pytest

from app.agents import graph as agent_graph
from app.agents import tools

GEO_LISBON = {"results": [{"name": "Lisbon", "country": "Portugal", "latitude": 38.7, "longitude": -9.1}]}
FORECAST_LISBON = {"current": {"temperature_2m": 18.5, "wind_speed_10m": 12.3}}

_RealAsyncClient = httpx.AsyncClient


@pytest.fixture
def open_meteo(monkeypatch):
    """Route the tool's HTTP calls to a handler: `open_meteo(handler)`.

    Returns the list of requests made, so tests can count them.
    """
    requests = []

    def install(handler):
        def recording_handler(request):
            requests.append(request)
            return handler(request)

        def client(**kwargs):
            return _RealAsyncClient(transport=httpx.MockTransport(recording_handler), **kwargs)

        monkeypatch.setattr(tools.httpx, "AsyncClient", client)
        return requests

    return install


@pytest.fixture(autouse=True)
def no_real_open_meteo(open_meteo):
    """Fail loudly if a test reaches the tool without mocking Open-Meteo first."""

    def handler(request):
        raise AssertionError(f"Unexpected real HTTP call: {request.url}")

    open_meteo(handler)


def lisbon_weather(request):
    if request.url.host.startswith("geocoding"):
        return httpx.Response(200, json=GEO_LISBON)
    return httpx.Response(200, json=FORECAST_LISBON)


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the real LLM with one that replies with the given messages, in order."""

    def install(model):
        monkeypatch.setattr(agent_graph, "get_llm", lambda: model)

    return install
