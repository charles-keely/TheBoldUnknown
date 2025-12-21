"""
Small in-process image cache for thumbnail bytes + ETags.

Why:
- Thumbnails are stored as base64 in Postgres JSON.
- Decoding + DB read on every request is slow.
- Adding ETag enables browser 304 responses.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class CachedImage:
    etag: str
    mime_type: str
    bytes_data: bytes
    cached_at: float


class LRUImageCache:
    def __init__(self, *, max_items: int = 256, ttl_seconds: int = 3600):
        self.max_items = int(max_items)
        self.ttl_seconds = int(ttl_seconds)
        self._store: OrderedDict[str, CachedImage] = OrderedDict()

    def get(self, key: str) -> CachedImage | None:
        now = time.time()
        item = self._store.get(key)
        if not item:
            return None
        if self.ttl_seconds > 0 and (now - item.cached_at) > self.ttl_seconds:
            # expired
            try:
                del self._store[key]
            except Exception:
                pass
            return None
        # mark as recently used
        self._store.move_to_end(key, last=True)
        return item

    def set(self, key: str, item: CachedImage) -> None:
        self._store[key] = item
        self._store.move_to_end(key, last=True)
        while len(self._store) > self.max_items:
            self._store.popitem(last=False)


def compute_etag_from_base64(b64: str) -> str:
    """
    Compute a strong ETag from the base64 payload.
    """
    h = hashlib.sha256(b64.encode("utf-8")).hexdigest()
    return f"\"{h}\""


def compute_etag_from_bytes(data: bytes) -> str:
    """
    Compute a strong ETag from raw bytes.
    """
    h = hashlib.sha256(data).hexdigest()
    return f"\"{h}\""


