#!/usr/bin/env python3
"""
Repair Cache — Specialised cache for VAL repair attempts.

Extracted from api_budget.py to keep budget-management and repair-caching
concerns separate.

Author: BDI-LLM Performance Team
Date: 2026-03-05
"""

import threading
from collections import deque
from typing import Any


class RepairCache:
    """Specialised cache for VAL repair attempts.

    Caches repair results by ``(domain, error_signature, plan_hash)`` to avoid
    generating identical repairs for the same error pattern.
    """

    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, Any] = {}
        self._access_order: deque = deque()
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _compute_key(self, domain: str, error_signature: str, plan_hash: str) -> str:
        """Compute cache key from repair context."""
        return f"{domain}:{error_signature}:{plan_hash}"

    def get(self, domain: str, error_signature: str, plan_hash: str) -> Any | None:
        """Get cached repair result."""
        key = self._compute_key(domain, error_signature, plan_hash)

        with self._lock:
            if key in self._cache:
                self._hits += 1
                # Move to end for LRU tracking
                self._access_order.remove(key)
                self._access_order.append(key)
                return self._cache[key]

            self._misses += 1
            return None

    def put(self, domain: str, error_signature: str, plan_hash: str, result: Any) -> None:
        """Cache repair result."""
        key = self._compute_key(domain, error_signature, plan_hash)

        with self._lock:
            # Evict if full
            while len(self._cache) >= self._max_size and self._access_order:
                oldest = self._access_order.popleft()
                self._cache.pop(oldest, None)

            self._cache[key] = result
            self._access_order.append(key)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.2%}",
            }


# Global repair cache
_repair_cache: RepairCache | None = None


def get_repair_cache(max_size: int = 1000) -> RepairCache:
    """Get or create global repair cache."""
    global _repair_cache

    if _repair_cache is None:
        _repair_cache = RepairCache(max_size)

    return _repair_cache
