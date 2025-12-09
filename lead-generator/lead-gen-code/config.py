import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Database
    POSTGRES_HOST = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "6543")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

    # APIs
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # LLM Models & Settings (tunable via environment)
    # Defaults are chosen to balance cost, quality, and determinism
    OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    OPENAI_VIRALITY_MODEL = os.getenv("OPENAI_VIRALITY_MODEL", "gpt-5-mini")
    OPENAI_BRAND_MODEL = os.getenv("OPENAI_BRAND_MODEL", "gpt-5")
    OPENAI_SEARCH_QUERY_MODEL = os.getenv("OPENAI_SEARCH_QUERY_MODEL", "gpt-5-mini")

    # Temperatures: lower = more deterministic, higher = more creative
    # Virality/brand checks should be stable; search queries can be slightly more exploratory.
    OPENAI_VIRALITY_TEMPERATURE = float(os.getenv("OPENAI_VIRALITY_TEMPERATURE", "0.2"))
    OPENAI_BRAND_TEMPERATURE = float(os.getenv("OPENAI_BRAND_TEMPERATURE", "0.2"))
    OPENAI_SEARCH_QUERY_TEMPERATURE = float(os.getenv("OPENAI_SEARCH_QUERY_TEMPERATURE", "0.6"))

    # Validation
    @classmethod
    def validate(cls):
        missing = []
        if not cls.POSTGRES_HOST: missing.append("POSTGRES_HOST")
        if not cls.POSTGRES_USER: missing.append("POSTGRES_USER")
        if not cls.POSTGRES_PASSWORD: missing.append("POSTGRES_PASSWORD")
        if not cls.PERPLEXITY_API_KEY: missing.append("PERPLEXITY_API_KEY")
        if not cls.OPENAI_API_KEY: missing.append("OPENAI_API_KEY")
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
