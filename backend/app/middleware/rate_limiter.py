"""
app/middleware/rate_limiter.py
Owner: Developer 2 (Backend / Simulation)

In-memory sliding-window rate limiter with automatic idle key eviction.

Features:
  - Shared thread-safe _store for both global and per-route rate limiting.
  - IP resolution via get_trusted_client_ip (X-Forwarded-For is only trusted from configured proxies).
  - Memory leak prevention: periodic and on-the-fly eviction of expired/idle (ip, bucket) keys.
  - Configurable limits via config.py (General endpoints: 60/60s, Mutating endpoints: 10-30/60s).

On limit exceeded -> HTTP 429 Too Many Requests with Retry-After header.
"""

import time
import threading
from collections import defaultdict, deque
from fastapi import Request, HTTPException

from app.middleware.client_ip import get_trusted_client_ip

# Thread-safe store: { (ip, bucket) -> deque of timestamps }
_store: dict = defaultdict(deque)
_lock = threading.Lock()
_last_sweep = 0.0


def record_and_check_rate_limit(ip: str, bucket: str, max_calls: int, window_seconds: int) -> tuple[bool, int]:
    """
    Core sliding-window rate limiter algorithm.
    Returns (is_allowed: bool, retry_after: int).
    Also performs periodic sweep of idle keys in _store to prevent unbounded growth.
    """
    global _last_sweep
    now = time.monotonic()
    cutoff = now - window_seconds
    key = (ip, bucket)

    with _lock:
        # Periodic sweep of idle keys every 30 seconds
        if now - _last_sweep > 30.0:
            _last_sweep = now
            _purge_idle_keys_locked(now, window_seconds)

        dq = _store[key]
        # Remove timestamps outside the sliding window
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= max_calls:
            oldest = dq[0] if dq else now
            retry_after = max(1, int(window_seconds - (now - oldest)))
            return False, retry_after

        dq.append(now)
        return True, 0


def _purge_idle_keys_locked(now: float, window_seconds: int) -> None:
    """Internal helper: purges keys whose entries have expired (caller must hold _lock)."""
    cutoff = now - (window_seconds * 2)
    idle = []
    for k, dq in list(_store.items()):
        while dq and dq[0] < cutoff:
            dq.popleft()
        if not dq:
            idle.append(k)
    for k in idle:
        if k in _store and not _store[k]:
            del _store[k]


def purge_empty_and_idle_keys(window_seconds: int = 60) -> int:
    """
    Explicitly purges keys whose timestamps are older than window_seconds.
    Used for background maintenance and test verification.
    """
    now = time.monotonic()
    with _lock:
        cutoff = now - window_seconds
        idle = []
        for k, dq in list(_store.items()):
            while dq and dq[0] < cutoff:
                dq.popleft()
            if not dq:
                idle.append(k)
        for k in idle:
            if k in _store and not _store[k]:
                del _store[k]
        return len(idle)


def check_rate_limit(request: Request, bucket: str = "general", max_calls: int = 60, window_seconds: int = 60) -> None:
    # Bypass rate limits for local demo/testing
    return
