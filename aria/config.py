import os
from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    pass


class Config:
    # LLM provider — "anthropic" or "openai" (auto-detected if not set)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")

    # Anthropic (Claude)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # OpenAI (GPT)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Apollo.io
    APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "")

    # Gmail
    GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")
    GMAIL_OAUTH_CREDENTIALS: str = os.getenv("GMAIL_OAUTH_CREDENTIALS", "")

    # Airtable
    AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
    AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")

    # Approval system
    APPROVAL_SECRET: str = os.getenv("APPROVAL_SECRET", "")
    RAILWAY_WEBHOOK_URL: str = os.getenv("RAILWAY_WEBHOOK_URL", "")

    # Human
    HUMAN_EMAIL: str = os.getenv("HUMAN_EMAIL", "")
    CAL_COM_LINK: str = os.getenv("CAL_COM_LINK", "")

    # Cal.com
    CAL_COM_WEBHOOK_SECRET: str = os.getenv("CAL_COM_WEBHOOK_SECRET", "")

    # Safety controls
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"
    MAX_PROSPECTS_PER_DAY: int = int(os.getenv("MAX_PROSPECTS_PER_DAY", "10"))

    # Required vars for full pipeline run
    REQUIRED_FOR_PIPELINE = [
        "ANTHROPIC_API_KEY",  # or OPENAI_API_KEY — one must be set
        "APOLLO_API_KEY",
        "GMAIL_ADDRESS",
        "GMAIL_APP_PASSWORD",
        "AIRTABLE_API_KEY",
        "AIRTABLE_BASE_ID",
        "APPROVAL_SECRET",
        "HUMAN_EMAIL",
        "CAL_COM_LINK",
    ]

    @classmethod
    def validate(cls) -> None:
        """Validate all required env vars are set. Raise ConfigError if not."""
        missing = []
        for var in cls.REQUIRED_FOR_PIPELINE:
            if not getattr(cls, var):
                missing.append(var)
        if missing:
            raise ConfigError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Copy .env.example to .env and fill in the values."
            )

    @classmethod
    def validate_soft(cls) -> list[str]:
        """Return list of missing vars without raising — for dry runs."""
        missing = []
        for var in cls.REQUIRED_FOR_PIPELINE:
            if not getattr(cls, var):
                missing.append(var)
        return missing
