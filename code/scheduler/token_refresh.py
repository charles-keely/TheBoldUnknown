import json
import time
import urllib.parse
import urllib.request
import urllib.error


class TokenRefreshError(RuntimeError):
    pass


def exchange_for_long_lived_token(
    *,
    graph_api_version: str,
    app_id: str,
    app_secret: str,
    fb_exchange_token: str,
) -> dict:
    """
    Exchange a (short-lived or long-lived) Facebook/Instagram user access token for a long-lived token.

    Endpoint:
      GET https://graph.facebook.com/{version}/oauth/access_token
        ?grant_type=fb_exchange_token
        &client_id=...
        &client_secret=...
        &fb_exchange_token=...

    Returns JSON like:
      { "access_token": "...", "token_type": "bearer", "expires_in": 5184000 }
    """
    if not (graph_api_version and app_id and app_secret and fb_exchange_token):
        raise ValueError("Missing required args for token exchange")

    base = f"https://graph.facebook.com/{graph_api_version}/oauth/access_token"
    q = urllib.parse.urlencode(
        {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": fb_exchange_token,
        }
    )
    url = f"{base}?{q}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise TokenRefreshError(f"Token exchange failed: {e.code} {e.reason} - {raw[:500]}") from e


def compute_expires_at(*, expires_in: int | None, now: int | None = None) -> int | None:
    if expires_in is None:
        return None
    now = int(now or time.time())
    return now + int(expires_in)



