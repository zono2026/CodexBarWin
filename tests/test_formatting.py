import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import formatting


CLAUDE_OK = {
    "five_hour": {"utilization": 12.0, "resets_at": "2026-07-14T09:19:59.969453+00:00"},
    "seven_day": {"utilization": 24.0, "resets_at": "2026-07-19T05:59:59.969484+00:00"},
}
CODEX_OK = {
    "primary": {"used_percent": 12, "window_duration_mins": 300, "resets_at": 1784020800},
    "secondary": {"used_percent": 24, "window_duration_mins": 10080, "resets_at": 1784440800},
}
CLAUDE_ERROR = {"error": "credentials file not found"}
CODEX_ERROR = {"error": "failed to start codex app-server (FileNotFoundError)"}


def test_build_title_includes_both_services_with_5h_and_7d_windows():
    title = formatting.build_title(CLAUDE_OK, CODEX_OK)
    assert "Claude 5h:12%" in title
    assert "7d:24%" in title
    assert "Codex 5h:12%" in title
    assert title.count("7d:24%") == 2  # both Claude and Codex show their 7d value


def test_build_title_shows_na_on_error():
    title = formatting.build_title(CLAUDE_ERROR, CODEX_OK)
    assert "Claude:N/A" in title


def test_build_title_shows_na_for_codex_on_error():
    title = formatting.build_title(CLAUDE_OK, CODEX_ERROR)
    assert "Codex:N/A" in title


def test_build_title_shows_rate_limited_instead_of_na():
    result = {"error": "rate_limited", "retry_after_seconds": 1343}

    title = formatting.build_title(result, CODEX_OK)

    assert "Claude:RATE LIMITED" in title
    assert "Claude:N/A" not in title


def test_build_title_marks_cached_claude_usage_as_stale():
    result = {**CLAUDE_OK, "stale": True, "rate_limited": True, "retry_after_seconds": 1200}

    title = formatting.build_title(result, CODEX_OK)

    assert "Claude 5h:12% 7d:24% (stale)" in title


def test_build_title_labels_codex_windows_by_actual_duration_not_position():
    # Regression: some Codex accounts only have the weekly (7d) window populated
    # in `primary`, with `secondary` entirely absent (used_percent/duration both
    # None) — the label must follow window_duration_mins, not assume
    # primary=5h/secondary=7d by position.
    codex_result = {
        "primary": {"used_percent": 95, "window_duration_mins": 10080, "resets_at": 1784440800},
        "secondary": {"used_percent": None, "window_duration_mins": None, "resets_at": None},
    }
    title = formatting.build_title(CLAUDE_OK, codex_result)
    assert "Codex 5h:? 7d:95%" in title
