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
    # Web Server
    HOST: str = os.getenv("SCHEDULER_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("SCHEDULER_PORT", "8000"))
    DEBUG: bool = os.getenv("SCHEDULER_DEBUG", "true").strip().lower() in ("1", "true", "yes")
    
    # Static files
    STATIC_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    TEMPLATE_DESIGN_DIR: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "template_design"
    )
    
    # DB
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    POSTGRES_CONNECT_TIMEOUT: int = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))
    POSTGRES_STATEMENT_TIMEOUT_MS: int = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "15000"))
    
    # Scheduling defaults (MST = UTC-7)
    TIMEZONE: str = os.getenv("SCHEDULER_TIMEZONE", "America/Denver")  # MST
    POSTING_TIMES: tuple = (
        (8, 30),   # 8:30 AM
        (13, 0),   # 1:00 PM
        (19, 0),   # 7:00 PM
    )

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
    # Optional: local token cache (recommended for unattended runs).
    # If IG_ACCESS_TOKEN is not set in env, the scheduler will read from this JSON file.
    IG_TOKEN_STORE_PATH: str = os.getenv(
        "SCHEDULER_IG_TOKEN_STORE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ig_token.json"),
    )

    # App credentials (required to auto-refresh long-lived tokens).
    META_APP_ID: str | None = os.getenv("META_APP_ID") or os.getenv("FB_APP_ID") or os.getenv("FACEBOOK_APP_ID")
    META_APP_SECRET: str | None = (
        os.getenv("META_APP_SECRET") or os.getenv("FB_APP_SECRET") or os.getenv("FACEBOOK_APP_SECRET")
    )
    TOKEN_REFRESH_WINDOW_DAYS: int = int(os.getenv("SCHEDULER_TOKEN_REFRESH_WINDOW_DAYS", "10"))

    # Runner behavior
    DEFAULT_PICK_STRATEGY: str = os.getenv("SCHEDULER_PICK_STRATEGY", "finalized_first")  # finalized_first|latest_any


config = Config()


