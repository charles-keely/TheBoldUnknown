import json
import time
import urllib.parse
import urllib.request
import urllib.error

from .config import config
from .token_store import get_access_token


class InstagramGraphError(RuntimeError):
    pass


def _graph_post(path: str, params: dict) -> dict:
    access_token = get_access_token(token_store_path=config.IG_TOKEN_STORE_PATH)
    base = f"https://graph.facebook.com/{config.GRAPH_API_VERSION}"
    url = f"{base}{path}"

    body = urllib.parse.urlencode({**params, "access_token": access_token}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise InstagramGraphError(f"Graph API POST failed: {e.code} {e.reason} - {raw[:500]}") from e


def _graph_get(path: str, params: dict) -> dict:
    access_token = get_access_token(token_store_path=config.IG_TOKEN_STORE_PATH)
    base = f"https://graph.facebook.com/{config.GRAPH_API_VERSION}"
    q = urllib.parse.urlencode({**params, "access_token": access_token})
    url = f"{base}{path}?{q}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise InstagramGraphError(f"Graph API GET failed: {e.code} {e.reason} - {raw[:500]}") from e


def create_carousel_item(*, ig_user_id: str, image_url: str) -> str:
    resp = _graph_post(
        f"/{ig_user_id}/media",
        {
            "image_url": image_url,
            "is_carousel_item": "true",
        },
    )
    cid = resp.get("id")
    if not cid:
        raise InstagramGraphError(f"Unexpected create_carousel_item response: {resp}")
    return str(cid)


def wait_container_ready(*, container_id: str, timeout_s: int = 180, poll_s: float = 3.0) -> None:
    """
    Poll container status until FINISHED (or timeout).
    """
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        resp = _graph_get(f"/{container_id}", {"fields": "status_code"})
        last = resp.get("status_code")
        if last == "FINISHED":
            return
        if last in ("ERROR", "EXPIRED"):
            raise InstagramGraphError(f"Container {container_id} status={last} resp={resp}")
        time.sleep(poll_s)
    raise InstagramGraphError(f"Timed out waiting for container {container_id} (last status={last})")


def create_carousel_container(*, ig_user_id: str, children: list[str], caption: str) -> str:
    resp = _graph_post(
        f"/{ig_user_id}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption or "",
        },
    )
    cid = resp.get("id")
    if not cid:
        raise InstagramGraphError(f"Unexpected create_carousel_container response: {resp}")
    return str(cid)


def publish_media(*, ig_user_id: str, creation_id: str) -> str:
    resp = _graph_post(
        f"/{ig_user_id}/media_publish",
        {
            "creation_id": creation_id,
        },
    )
    mid = resp.get("id")
    if not mid:
        raise InstagramGraphError(f"Unexpected publish_media response: {resp}")
    return str(mid)


def validate_ig_user_access(*, ig_user_id: str) -> None:
    """
    Best-effort preflight check that the current access token is valid and can access the IG user.

    This is intentionally lightweight and is used to fail fast before expensive work
    (rendering + uploading assets) when the token is expired/misconfigured.
    """
    resp = _graph_get(f"/{ig_user_id}", {"fields": "id"})
    if str(resp.get("id") or "") != str(ig_user_id):
        raise InstagramGraphError(f"Token validation failed for IG user {ig_user_id}: {resp}")


