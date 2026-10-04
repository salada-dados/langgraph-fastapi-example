from dotenv import load_dotenv
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


settings = Settings()
