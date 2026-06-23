"""
JARVIS Response Cache — TTL-based in-memory caching
────────────────────────────────────────────────────
Prevents redundant API calls for frequent queries like weather, news, cricket.

Usage:
    from utils.cache import cached

    class APIMaster:
        @cached(ttl=300)                    # cache 5 minutes
        def get_hyderabad_weather(self): ...

        @cached(ttl=60, key="live_cricket") # custom cache key
        def check_live_cricket(self): ...

Features:
  - Thread-safe (RLock)
  - Automatic expiry — stale entries cleaned lazily + periodic sweep
  - Negative caching skipped — errors are never cached
  - Logging of HIT / MISS / EXPIRED
  - Cache stats via jarvis_cache.stats()
  - Manual invalidation via jarvis_cache.invalidate(key)
"""

import time
import threading
import functools
from typing import Any


class TTLCache:
    """Thread-safe dictionary-backed TTL cache."""

    def __init__(self, sweep_interval: int = 60):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock  = threading.RLock()
        self._hits  = 0
        self._misses = 0
        # Periodic background sweep to clean expired entries
        self._sweeper = threading.Thread(
            target=self._sweep_loop,
            args=(sweep_interval,),
            daemon=True,
            name="CacheSweeper"
        )
        self._sweeper.start()

    # ── Core operations ───────────────────────────────────────────────────────

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expires_at = entry
            if time.monotonic() < expires_at:
                self._hits += 1
                return value
            # Expired — remove lazily
            del self._store[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl: int = 300):
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    def invalidate(self, key: str):
        """Manually remove a specific cache entry."""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str):
        """Remove all entries whose key starts with the given prefix."""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]

    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._store.clear()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> str:
        with self._lock:
            now = time.monotonic()
            valid   = sum(1 for _, (_, exp) in self._store.items() if exp > now)
            expired = len(self._store) - valid
            total   = self._hits + self._misses
            hit_rate = f"{100*self._hits/total:.0f}%" if total else "N/A"
            return (
                f"🗃️ Cache: {valid} live / {expired} stale / "
                f"{total} lookups / hit-rate {hit_rate}"
            )

    # ── Background sweep ──────────────────────────────────────────────────────

    def _sweep_loop(self, interval: int):
        while True:
            time.sleep(interval)
            with self._lock:
                now = time.monotonic()
                expired = [k for k, (_, exp) in self._store.items() if exp <= now]
                for k in expired:
                    del self._store[k]


# ── Module-level singleton ────────────────────────────────────────────────────
jarvis_cache = TTLCache(sweep_interval=60)


# ── Decorator ─────────────────────────────────────────────────────────────────

def cached(ttl: int = 300, key: str = None, skip_errors: bool = True):
    """
    Decorator that caches method return values with a TTL.

    Args:
        ttl:          Seconds before the cached value expires.
        key:          Fixed cache key (use this for zero-argument methods).
                      If None, a key is auto-built from qualname + args + kwargs.
        skip_errors:  If True (default), error responses are NOT cached so the
                      next call retries the real API.

    Example:
        @cached(ttl=300)
        def get_weather(self): ...

        @cached(ttl=60, key="cricket_live")
        def check_live_cricket(self): ...
    """
    # Error phrases that should never be cached
    _ERROR_PREFIXES = (
        "error", "fail", "unable", "could not", "unavailable",
        "not found", "timed out", "no key", "not configured",
    )

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self_obj, *args, **kwargs):
            # Build cache key
            if key:
                cache_key = key
            else:
                arg_str = ":".join(str(a) for a in args)
                kwarg_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = f"{func.__qualname__}|{arg_str}|{kwarg_str}"

            # Check cache
            cached_val = jarvis_cache.get(cache_key)
            if cached_val is not None:
                logger = getattr(self_obj, "logger", None)
                if logger:
                    logger.info(f"⚡ Cache HIT [{func.__name__}] → serving from cache")
                return cached_val

            # Call real function
            result = func(self_obj, *args, **kwargs)

            # Store unless it's an error response
            if result:
                result_lower = str(result).lower()[:40]
                is_error = skip_errors and any(
                    result_lower.startswith(p) for p in _ERROR_PREFIXES
                )
                if not is_error:
                    jarvis_cache.set(cache_key, result, ttl)

            return result

        # Attach helper to force-refresh this specific cache entry
        def invalidate(self_obj=None, *args, **kwargs):
            if key:
                jarvis_cache.invalidate(key)
            else:
                jarvis_cache.invalidate_prefix(func.__qualname__)

        wrapper.invalidate_cache = invalidate
        return wrapper
    return decorator
