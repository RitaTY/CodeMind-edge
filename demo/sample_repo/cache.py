"""
cache.py — In-memory cache with TTL (Time-To-Live) expiry.

Used to avoid redundant database queries for frequently read data.
Backed by a thread-safe dict with lazy eviction.
"""

import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_cache : dict[str, dict] = {}
_lock  = threading.RLock()


def get_cached(key: str) -> Optional[Any]:
    """
    Retrieve a value from cache.

    Returns None if the key doesn't exist or has expired.
    Expired entries are lazily deleted on access.
    """
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None

        if entry["expires_at"] < time.monotonic():
            del _cache[key]
            logger.debug("Cache miss (expired): %s", key)
            return None

        logger.debug("Cache hit: %s", key)
        return entry["value"]


def set_cached(key: str, value: Any, ttl: float = 60.0) -> None:
    """
    Store a value in cache with a TTL (seconds).

    Args:
        key   — cache key
        value — serialisable value to cache
        ttl   — time-to-live in seconds (default 60s)
    """
    with _lock:
        _cache[key] = {
            "value":      value,
            "expires_at": time.monotonic() + ttl,
            "created_at": time.monotonic(),
        }
        logger.debug("Cached %s (ttl=%.0fs)", key, ttl)


def invalidate(key: str) -> bool:
    """
    Remove a specific key from the cache immediately.

    Returns True if the key existed, False otherwise.
    """
    with _lock:
        existed = key in _cache
        _cache.pop(key, None)
        if existed:
            logger.debug("Cache invalidated: %s", key)
        return existed


def invalidate_prefix(prefix: str) -> int:
    """
    Remove all cache keys that start with *prefix*.

    Returns the number of keys removed.
    """
    with _lock:
        to_remove = [k for k in _cache if k.startswith(prefix)]
        for k in to_remove:
            del _cache[k]
        if to_remove:
            logger.debug("Invalidated %d keys with prefix '%s'", len(to_remove), prefix)
        return len(to_remove)


def flush_all() -> int:
    """Clear the entire cache. Returns number of entries removed."""
    with _lock:
        count = len(_cache)
        _cache.clear()
        logger.info("Cache flushed (%d entries removed)", count)
        return count


def evict_expired() -> int:
    """
    Remove all expired entries.
    Can be called periodically by a background thread.
    Returns number of evicted entries.
    """
    now = time.monotonic()
    with _lock:
        expired = [k for k, v in _cache.items() if v["expires_at"] < now]
        for k in expired:
            del _cache[k]
        if expired:
            logger.debug("Evicted %d expired cache entries", len(expired))
        return len(expired)


def stats() -> dict:
    """Return cache statistics."""
    now = time.monotonic()
    with _lock:
        total   = len(_cache)
        alive   = sum(1 for v in _cache.values() if v["expires_at"] >= now)
        expired = total - alive
    return {"total": total, "alive": alive, "expired": expired}
