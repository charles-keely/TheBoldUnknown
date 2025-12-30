import urllib.parse
import urllib.request
import urllib.error

from .config import config


def upload_bytes_to_supabase(*, data: bytes, content_type: str, object_path: str) -> str:
    """
    Upload bytes to Supabase Storage and return a public URL.
    Mirrors the logic used in `thumbnail_generator/nanobanana.py` but without that dependency.
    """
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("Supabase storage not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing)")
    if not config.SUPABASE_STORAGE_PUBLIC:
        raise ValueError("SUPABASE_STORAGE_PUBLIC=false is not supported yet (would require signed URLs)")

    bucket = config.SUPABASE_STORAGE_BUCKET
    encoded_path = urllib.parse.quote(object_path.lstrip("/"), safe="/-_.~")

    put_url = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{encoded_path}"
    public_url = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/{encoded_path}"

    req = urllib.request.Request(
        put_url,
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
            "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            _ = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise RuntimeError(f"Supabase upload failed: HTTP {e.code} {e.reason} - {body[:300]}") from e

    return public_url



