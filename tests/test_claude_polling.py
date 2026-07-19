import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_polling import ClaudeUsagePoller


SUCCESS = {
    "five_hour": {"utilization": 12.0, "resets_at": None},
    "seven_day": {"utilization": 24.0, "resets_at": None},
}


def test_poller_enforces_minimum_interval_without_second_request():
    calls = []
    now = [1000.0]
    poller = ClaudeUsagePoller(
        fetch_fn=lambda: calls.append(True) or SUCCESS,
        time_source=lambda: now[0],
        minimum_interval_seconds=300,
    )

    assert poller.fetch() == SUCCESS
    now[0] += 60
    result = poller.fetch()

    assert len(calls) == 1
    assert result["stale"] is True
    assert result["retry_after_seconds"] == 240


def test_poller_honors_server_retry_after():
    results = [
        {"error": "rate_limited", "retry_after_seconds": 1343},
        SUCCESS,
    ]
    now = [1000.0]
    poller = ClaudeUsagePoller(fetch_fn=lambda: results.pop(0), time_source=lambda: now[0])

    limited = poller.fetch()
    now[0] += 100
    still_limited = poller.fetch()
    now[0] += 1243
    recovered = poller.fetch()

    assert limited == {"error": "rate_limited", "retry_after_seconds": 1343}
    assert still_limited == {"error": "rate_limited", "retry_after_seconds": 1243}
    assert recovered == SUCCESS
    assert results == []


def test_poller_returns_stale_success_during_rate_limit():
    results = [SUCCESS, {"error": "rate_limited", "retry_after_seconds": 1800}]
    now = [1000.0]
    poller = ClaudeUsagePoller(
        fetch_fn=lambda: results.pop(0),
        time_source=lambda: now[0],
        minimum_interval_seconds=0,
    )

    assert poller.fetch() == SUCCESS
    limited = poller.fetch()

    assert limited["five_hour"] == SUCCESS["five_hour"]
    assert limited["seven_day"] == SUCCESS["seven_day"]
    assert limited["stale"] is True
    assert limited["rate_limited"] is True
    assert limited["retry_after_seconds"] == 1800


def test_non_rate_limit_error_is_not_cached_as_success():
    poller = ClaudeUsagePoller(
        fetch_fn=lambda: {"error": "http error 401"},
        time_source=lambda: 1000.0,
    )

    assert poller.fetch() == {"error": "http error 401"}


def test_poller_enforces_minimum_interval_after_non_rate_limit_error():
    results = [{"error": "http error 401"}, SUCCESS]
    now = [1000.0]
    poller = ClaudeUsagePoller(
        fetch_fn=lambda: results.pop(0),
        time_source=lambda: now[0],
        minimum_interval_seconds=300,
    )

    assert poller.fetch() == {"error": "http error 401"}
    now[0] += 60
    deferred = poller.fetch()

    assert deferred == {"error": "waiting", "retry_after_seconds": 240}
    assert results == [SUCCESS]

    now[0] += 240
    assert poller.fetch() == SUCCESS
    assert results == []
