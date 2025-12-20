import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _load_env() -> None:
    """
    Load env vars in the same style as other modules:
    - scheduler/.env (optional)
    - repo root .env (optional)
    - process env
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    load_dotenv(os.path.join(here, ".env"))
    load_dotenv(os.path.join(repo_root, ".env"))
    load_dotenv()


_load_env()


@dataclass(frozen=True)
class Config:
    # DB
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    POSTGRES_CONNECT_TIMEOUT: int = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))
    POSTGRES_STATEMENT_TIMEOUT_MS: int = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "15000"))

    # Supabase Storage (for making rendered slides reachable by Instagram)
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_ROLE_KEY: str | None = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_KEY")
    )
    SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "story-assets")
    SUPABASE_STORAGE_PUBLIC: bool = os.getenv("SUPABASE_STORAGE_PUBLIC", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )

    # Instagram Graph API
    GRAPH_API_VERSION: str = os.getenv("GRAPH_API_VERSION", "v19.0")
    IG_USER_ID: str | None = os.getenv("IG_USER_ID") or os.getenv("INSTAGRAM_USER_ID")
    IG_ACCESS_TOKEN: str | None = (
        os.getenv("IG_ACCESS_TOKEN")
        or os.getenv("INSTAGRAM_ACCESS_TOKEN")
        or os.getenv("IG_USER_ACCESS_TOKEN")
        or os.getenv("INSTAGRAM_USER_ACCESS_TOKEN")
    )

    # Runner behavior
    DEFAULT_PICK_STRATEGY: str = os.getenv("SCHEDULER_PICK_STRATEGY", "finalized_first")  # finalized_first|latest_any


config = Config()


