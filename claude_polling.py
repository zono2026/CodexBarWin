"""Stateful throttling and retry handling for Claude usage polling."""

import math
import time


DEFAULT_MINIMUM_INTERVAL_SECONDS = 5 * 60


class ClaudeUsagePoller:
    def __init__(
        self,
        fetch_fn,
        time_source=time.monotonic,
        minimum_interval_seconds=DEFAULT_MINIMUM_INTERVAL_SECONDS,
    ):
        self._fetch_fn = fetch_fn
        self._time_source = time_source
        self._minimum_interval_seconds = minimum_interval_seconds
        self._next_request_at = 0.0
        self._last_success = None
        self._backoff_is_rate_limit = False

    def _remaining_seconds(self, now):
        return max(0, math.ceil(self._next_request_at - now))

    def _deferred_result(self, now):
        remaining = self._remaining_seconds(now)
        if self._last_success is not None:
            return {
                **self._last_success,
                "stale": True,
                "rate_limited": self._backoff_is_rate_limit,
                "retry_after_seconds": remaining,
            }
        return {
            "error": "rate_limited" if self._backoff_is_rate_limit else "waiting",
            "retry_after_seconds": remaining,
        }

    def fetch(self):
        now = self._time_source()
        if now < self._next_request_at:
            return self._deferred_result(now)

        result = self._fetch_fn()
        self._next_request_at = now + self._minimum_interval_seconds
        self._backoff_is_rate_limit = False

        if result.get("error") == "rate_limited":
            delay = max(1, int(result["retry_after_seconds"]))
            self._next_request_at = now + max(self._minimum_interval_seconds, delay)
            self._backoff_is_rate_limit = True
            return self._deferred_result(now)

        if "error" not in result:
            self._last_success = result
        return result
