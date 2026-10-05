import logging

import httpx
from langchain_core.tools import tool

from app.core.config import settings

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# What the LLM sees when the lookup fails. Kept generic on purpose: URLs, status
# codes and exception messages stay in the server logs, not in the conversation.
WEATHER_UNAVAILABLE = "The weather service is unavailable right now. Please try again later."


@tool
async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
            geo = await client.get(GEOCODING_URL, params={"name": city, "count": 1})
            geo.raise_for_status()
            results = geo.json().get("results")
            if not results:
                return f"Could not find a city called '{city}'."
            place = results[0]

            forecast = await client.get(
                FORECAST_URL,
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,wind_speed_10m",
                },
            )
            forecast.raise_for_status()
            current = forecast.json()["current"]

            return (
                f"{place['name']}, {place.get('country', '')}: "
                f"{current['temperature_2m']}°C, wind {current['wind_speed_10m']} km/h."
            )
    except httpx.HTTPError:
        # Network errors, timeouts and 4xx/5xx responses.
        logger.exception("Open-Meteo request failed for city %r", city)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        # A 200 response we can't parse: invalid JSON or an unexpected shape.
        logger.exception("Unexpected Open-Meteo response for city %r", city)

    # Return the failure as text so the LLM can tell the user, instead of crashing the graph.
    return WEATHER_UNAVAILABLE


TOOLS = [get_weather]
