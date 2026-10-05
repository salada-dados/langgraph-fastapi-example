from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Export .env into os.environ so provider SDKs find their API keys
# (e.g. ANTHROPIC_API_KEY, OPENAI_API_KEY) on their own.
load_dotenv()


class Settings(BaseSettings):
    """App configuration, read from environment variables (and `.env`)."""

    # "provider:model" string understood by LangChain's init_chat_model.
    # Swap providers without touching code, e.g. "openai:gpt-5".
    LLM_MODEL: str = "anthropic:claude-sonnet-5-5"
    # Optional: some models (e.g. recent Claude models) only accept their default.
    LLM_TEMPERATURE: float | None = None

    # Timeout (seconds) for outbound HTTP calls made by tools.
    REQUEST_TIMEOUT: float = 10.0

    # Upper bound on user input: every character costs tokens.
    MAX_MESSAGE_LENGTH: int = 4000

    # Max LangGraph steps per request, so a misbehaving LLM can't loop forever.
    # Each agent → tools round trip takes 2 steps: 10 allows up to 4 tool rounds
    # plus the final answer. Hitting the limit fails the request.
    AGENT_RECURSION_LIMIT: int = Field(default=10, ge=1)


settings = Settings()
