import asyncio

import httpx
import pytest

from app.agents.tools import TOOLS, WEATHER_UNAVAILABLE, get_weather
from tests.conftest import GEO_LISBON, lisbon_weather


def run_tool(city: str) -> str:
    return asyncio.run(get_weather.ainvoke({"city": city}))


def test_tool_is_registered():
    assert [t.name for t in TOOLS] == ["get_weather"]
    assert set(get_weather.args) == {"city"}


def test_returns_current_weather(open_meteo):
    requests = open_meteo(lisbon_weather)

    assert run_tool("Lisbon") == "Lisbon, Portugal: 18.5°C, wind 12.3 km/h."
    assert len(requests) == 2


@pytest.mark.parametrize("body", [{"results": []}, {}])
def test_city_not_found_is_a_normal_answer(open_meteo, body):
    open_meteo(lambda request: httpx.Response(200, json=body))

    assert run_tool("Atlantis") == "Could not find a city called 'Atlantis'."


def raise_connect_error(request):
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        raise_connect_error,
        lambda request: httpx.Response(500, text="Internal Server Error"),
    ],
    ids=["network-error", "http-500"],
)
def test_network_and_http_errors_return_a_safe_message(open_meteo, handler):
    open_meteo(handler)

    assert run_tool("Lisbon") == WEATHER_UNAVAILABLE


def forecast_returns(**response_kwargs):
    def handler(request):
        if request.url.host.startswith("geocoding"):
            return httpx.Response(200, json=GEO_LISBON)
        return httpx.Response(200, **response_kwargs)

    return handler


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(200, text="<html>not json</html>"),
        lambda request: httpx.Response(200, json={"results": [{"name": "Lisbon"}]}),
        lambda request: httpx.Response(200, json=["unexpected", "list"]),
        forecast_returns(json={"error": True, "reason": "bad request"}),
        forecast_returns(json={"current": {"temperature_2m": 18.5}}),
    ],
    ids=["invalid-json", "place-without-coordinates", "wrong-json-type", "missing-current", "missing-field"],
)
def test_malformed_responses_return_a_safe_message(open_meteo, handler):
    open_meteo(handler)

    assert run_tool("Lisbon") == WEATHER_UNAVAILABLE
