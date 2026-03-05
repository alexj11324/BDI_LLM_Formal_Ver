#!/usr/bin/env python3
"""
API Budget Manager for BDI-LLM
===============================

Provides rate limiting, caching, and budget tracking for LLM API calls.

Key Features:
- Request rate limiting (requests/minute tracking)
- Exponential backoff on 429/504 errors
- Response caching by prompt hash
- Early exit detection for hopeless repair cases
- Budget enforcement (max calls per instance)

Author: BDI-LLM Performance Team
Date: 2026-02-28
"""

import hashlib
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from functools import wraps
from typing import Any

from .repair_cache import RepairCache, get_repair_cache  # noqa: F401

logger = logging.getLogger(__name__)


def get_budget_config():
    """Get BudgetConfig from environment variables via Config class."""
    try:
        from .config import Config
        return BudgetConfig(
            max_requests_per_minute=Config.API_BUDGET_MAX_RPM,
            max_requests_per_hour=Config.API_BUDGET_MAX_RPH,
            max_calls_per_instance=Config.API_BUDGET_MAX_CALLS_PER_INSTANCE,
            cache_enabled=Config.API_BUDGET_CACHE_ENABLED,
            early_exit_enabled=Config.API_BUDGET_EARLY_EXIT_ENABLED,
        )
    except Exception:
        # Fallback to defaults if Config not available
        return BudgetConfig()


@dataclass
class APICallRecord:
    """Record of a single API call"""
    timestamp: float
    endpoint: str
    prompt_hash: str
    success: bool
    status_code: int | None = None
    latency_ms: float = 0.0
    tokens_used: int = 0


@dataclass
class BudgetConfig:
    """Configuration for API budget management"""
    # Rate limiting
    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 1000

    # Backoff configuration
    initial_backoff_ms: int = 1000
    max_backoff_ms: int = 60000
    backoff_multiplier: float = 2.0
    retry_on_429: bool = True
    retry_on_504: bool = True

    # Budget limits
    max_calls_per_instance: int = 5  # Initial + structural + 3 VAL repairs
    max_total_calls: int | None = None  # None = unlimited

    # Caching
    cache_enabled: bool = True
    cache_max_size: int = 10000

    # Early exit
    early_exit_enabled: bool = True
    early_exit_after_failures: int = 2


class APIBudgetManager:
    """
    Manages API call budget, rate limiting, and caching.

    Thread-safe implementation using locks.
    """

    def __init__(self, config: BudgetConfig | None = None):
        """
        Args:
            config: Budget configuration. Uses defaults if None.
        """
        self.config = config or BudgetConfig()
        self._lock = threading.RLock()

        # Request history for rate limiting
        self._request_history: deque = deque()
        self._hourly_history: deque = deque()

        # Response cache: prompt_hash -> response
        self._cache: dict[str, Any] = {}
        self._cache_access_order: deque = deque()

        # Budget tracking
        self._total_calls: int = 0
        self._calls_per_instance: dict[str, int] = {}

        # Backoff state: endpoint -> (next_retry_time, current_backoff_ms)
        self._backoff_state: dict[str, tuple[float, int]] = {}

        # Error pattern tracking for early exit
        self._error_patterns: dict[str, list[str]] = {}

    def compute_prompt_hash(self, **prompt_kwargs) -> str:
        """Compute SHA256 hash of prompt for caching"""
        # Sort keys for consistent hashing
        canonical = json.dumps(prompt_kwargs, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def check_rate_limit(self) -> tuple[bool, float | None]:
        """
        Check if request is within rate limits.

        Returns:
            (allowed, wait_seconds) - if not allowed, wait before retrying
        """
        with self._lock:
            now = time.time()
            now_minus_minute = now - 60
            now_minus_hour = now - 3600

            # Clean old entries
            while self._request_history and self._request_history[0] < now_minus_minute:
                self._request_history.popleft()
            while self._hourly_history and self._hourly_history[0] < now_minus_hour:
                self._hourly_history.popleft()

            # Check per-minute limit
            if len(self._request_history) >= self.config.max_requests_per_minute:
                wait_time = self._request_history[0] + 60 - now
                return False, max(0, wait_time)

            # Check per-hour limit
            if len(self._hourly_history) >= self.config.max_requests_per_hour:
                wait_time = self._hourly_history[0] + 3600 - now
                return False, max(0, wait_time)

            return True, None

    def record_request(self, endpoint: str = "default") -> None:
        """Record a request for rate limiting"""
        with self._lock:
            now = time.time()
            self._request_history.append(now)
            self._hourly_history.append(now)

    def check_backoff(self, endpoint: str = "default") -> tuple[bool, float]:
        """
        Check if endpoint is in backoff state.

        Returns:
            (should_wait, wait_seconds)
        """
        with self._lock:
            if endpoint not in self._backoff_state:
                return False, 0.0

            next_retry, _ = self._backoff_state[endpoint]
            now = time.time()

            if now < next_retry:
                return True, next_retry - now

            # Backoff period expired - clear state
            del self._backoff_state[endpoint]
            return False, 0.0

    def apply_backoff(self, status_code: int, endpoint: str = "default") -> None:
        """Apply backoff based on error status code"""
        if not ((status_code == 429 and self.config.retry_on_429) or
                (status_code == 504 and self.config.retry_on_504)):
            return

        with self._lock:
            now = time.time()

            if endpoint in self._backoff_state:
                _, current_backoff = self._backoff_state[endpoint]
                new_backoff = min(
                    int(current_backoff * self.config.backoff_multiplier),
                    self.config.max_backoff_ms
                )
            else:
                new_backoff = self.config.initial_backoff_ms

            next_retry = now + (new_backoff / 1000.0)
            self._backoff_state[endpoint] = (next_retry, new_backoff)

            logger.warning(
                f"Rate limit hit (HTTP {status_code}) on {endpoint}. "
                f"Backing off for {new_backoff}ms"
            )

    def get_cached_response(self, prompt_hash: str) -> Any | None:
        """Get cached response if available"""
        if not self.config.cache_enabled:
            return None

        with self._lock:
            return self._cache.get(prompt_hash)

    def cache_response(self, prompt_hash: str, response: Any) -> None:
        """Cache a response"""
        if not self.config.cache_enabled:
            return

        with self._lock:
            # Evict if cache is full (LRU eviction)
            if len(self._cache) >= self.config.cache_max_size:
                if self._cache_access_order:
                    oldest = self._cache_access_order.popleft()
                    self._cache.pop(oldest, None)

            self._cache[prompt_hash] = response
            self._cache_access_order.append(prompt_hash)

    def check_budget(self, instance_id: str = "default") -> tuple[bool, str]:
        """
        Check if call is within budget.

        Returns:
            (allowed, reason)
        """
        with self._lock:
            # Check total budget
            if self.config.max_total_calls and self._total_calls >= self.config.max_total_calls:
                return False, f"Total budget exceeded ({self.config.max_total_calls} calls)"

            # Check per-instance budget
            instance_calls = self._calls_per_instance.get(instance_id, 0)
            if instance_calls >= self.config.max_calls_per_instance:
                return (
                    False,
                    "Instance budget exceeded "
                    f"({instance_calls}/{self.config.max_calls_per_instance})",
                )

            return True, "OK"

    def record_call(self, instance_id: str = "default") -> None:
        """Record a successful API call against budget"""
        with self._lock:
            self._total_calls += 1
            self._calls_per_instance[instance_id] = self._calls_per_instance.get(instance_id, 0) + 1

    def track_error_pattern(self, instance_id: str, error_signature: str) -> bool:
        """
        Track error pattern for early exit detection.

        Args:
            instance_id: Instance identifier
            error_signature: Hashed/digested error pattern

        Returns:
            True if should exit early (pattern repeated too many times)
        """
        if not self.config.early_exit_enabled:
            return False

        with self._lock:
            if instance_id not in self._error_patterns:
                self._error_patterns[instance_id] = []

            self._error_patterns[instance_id].append(error_signature)

            # Check if same pattern repeated
            if len(self._error_patterns[instance_id]) >= self.config.early_exit_after_failures:
                recent = self._error_patterns[instance_id][-self.config.early_exit_after_failures:]
                if len(set(recent)) == 1:  # All same pattern
                    logger.warning(
                        f"Early exit triggered for {instance_id}: "
                        f"same error pattern repeated {len(recent)} times"
                    )
                    return True

            return False

    def get_stats(self) -> dict[str, Any]:
        """Get current budget statistics"""
        with self._lock:
            now = time.time()

            # Clean history for accurate count
            while self._request_history and self._request_history[0] < now - 60:
                self._request_history.popleft()

            return {
                "total_calls": self._total_calls,
                "calls_this_minute": len(self._request_history),
                "cache_size": len(self._cache),
                "instances_tracked": len(self._calls_per_instance),
                "backoff_active": len(self._backoff_state),
            }

    def reset_instance(self, instance_id: str) -> None:
        """Reset budget tracking for an instance"""
        with self._lock:
            self._calls_per_instance.pop(instance_id, None)
            self._error_patterns.pop(instance_id, None)


# Global budget manager instance
_global_budget: APIBudgetManager | None = None
_budget_lock = threading.Lock()


def get_budget_manager(config: BudgetConfig | None = None) -> APIBudgetManager:
    """Get or create global budget manager"""
    global _global_budget

    with _budget_lock:
        if _global_budget is None:
            # Use provided config or load from environment
            if config is None:
                config = get_budget_config()
            _global_budget = APIBudgetManager(config)
        return _global_budget


def rate_limited_call(max_retries: int = 3):
    """
    Decorator for rate-limited API calls with automatic backoff.

    Usage:
        @rate_limited_call(max_retries=3)
        def make_api_call(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            budget = get_budget_manager()
            endpoint = kwargs.get("endpoint", "default")

            last_error = None
            for attempt in range(max_retries + 1):
                # Check rate limit
                allowed, wait_time = budget.check_rate_limit()
                if not allowed:
                    logger.info(f"Rate limited, waiting {wait_time:.1f}s")
                    time.sleep(wait_time + 0.1)  # Add small buffer
                    continue

                # Check backoff
                in_backoff, backoff_time = budget.check_backoff(endpoint)
                if in_backoff:
                    logger.info(f"Backoff active for {endpoint}, waiting {backoff_time:.1f}s")
                    time.sleep(backoff_time + 0.1)
                    continue

                # Record request for rate limiting
                budget.record_request(endpoint)

                try:
                    # Make the actual call
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    (time.time() - start_time) * 1000

                    return result

                except Exception as e:
                    last_error = e
                    status_code = getattr(e, "status_code", None)

                    if status_code in (429, 504):
                        budget.apply_backoff(status_code, endpoint)

                    if attempt == max_retries:
                        raise

            raise last_error or Exception("Max retries exceeded")

        return wrapper
    return decorator

