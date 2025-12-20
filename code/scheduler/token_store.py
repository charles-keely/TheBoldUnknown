import json
import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenRecord:
    access_token: str
    token_type: str | None = None
    obtained_at: int | None = None  # unix seconds
    expires_at: int | None = None  # unix seconds
    expires_in: int | None = None  # seconds
    graph_api_version: str | None = None
    source: str | None = None

    def is_expired(self, *, now: int | None = None) -> bool:
        now = int(now or time.time())
        if self.expires_at is None:
            # If unknown, treat as non-expired (best effort), but callers may choose to be strict.
            return False
        return now >= int(self.expires_at)


def _atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def load_token_record(path: str) -> TokenRecord | None:
    if not path:
        return None
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f) or {}
    token = data.get("access_token")
    if not token or not isinstance(token, str):
        return None
    return TokenRecord(
        access_token=token,
        token_type=data.get("token_type"),
        obtained_at=data.get("obtained_at"),
        expires_at=data.get("expires_at"),
        expires_in=data.get("expires_in"),
        graph_api_version=data.get("graph_api_version"),
        source=data.get("source"),
    )


def save_token_record(path: str, rec: TokenRecord) -> None:
    if not path:
        raise ValueError("Token store path is empty")
    payload = {
        "access_token": rec.access_token,
        "token_type": rec.token_type,
        "obtained_at": rec.obtained_at,
        "expires_at": rec.expires_at,
        "expires_in": rec.expires_in,
        "graph_api_version": rec.graph_api_version,
        "source": rec.source,
    }
    _atomic_write_json(path, payload)


def get_access_token_from_env() -> str | None:
    return (
        os.getenv("IG_ACCESS_TOKEN")
        or os.getenv("INSTAGRAM_ACCESS_TOKEN")
        or os.getenv("IG_USER_ACCESS_TOKEN")
        or os.getenv("INSTAGRAM_USER_ACCESS_TOKEN")
    )


def get_access_token(*, token_store_path: str | None) -> str:
    """
    Resolve an access token from:
    1) env vars (preferred for local dev / overrides)
    2) token store json file (recommended for unattended scheduler runs)
    """
    env = get_access_token_from_env()
    if env and env.strip():
        return env.strip()
    rec = load_token_record(token_store_path or "")
    if rec and rec.access_token and rec.access_token.strip():
        if rec.is_expired():
            raise ValueError(f"Stored IG access token is expired (token_store={token_store_path})")
        return rec.access_token.strip()
    raise ValueError(
        "IG access token is not set. Set IG_ACCESS_TOKEN (env) or create a token store via `scheduler refresh-token`."
    )


