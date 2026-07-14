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


def test_collect_utilizations_combines_both_sources():
    values = formatting.collect_utilizations(CLAUDE_OK, CODEX_OK)
    assert values == [12.0, 24.0, 12, 24]


def test_collect_utilizations_skips_errored_sources():
    values = formatting.collect_utilizations(CLAUDE_ERROR, CODEX_OK)
    assert values == [12, 24]


def test_collect_utilizations_empty_when_both_errored():
    assert formatting.collect_utilizations(CLAUDE_ERROR, CODEX_ERROR) == []


def test_icon_color_for_gray_when_no_data():
    assert formatting.icon_color_for([]) == (128, 128, 128)


def test_icon_color_for_green_when_low():
    assert formatting.icon_color_for([10, 20]) == (40, 160, 80)


def test_icon_color_for_yellow_when_medium():
    assert formatting.icon_color_for([60]) == (230, 180, 30)


def test_icon_color_for_red_when_high():
    assert formatting.icon_color_for([95]) == (220, 50, 47)


def test_build_title_includes_both_services():
    title = formatting.build_title(CLAUDE_OK, CODEX_OK)
    assert "Claude" in title
    assert "Codex" in title
    assert "12%" in title


def test_build_title_shows_na_on_error():
    title = formatting.build_title(CLAUDE_ERROR, CODEX_OK)
    assert "Claude:N/A" in title


def test_build_menu_lines_success_has_four_lines():
    lines = formatting.build_menu_lines(CLAUDE_OK, CODEX_OK)
    assert len(lines) == 4
    assert any("Claude 5h" in line for line in lines)
    assert any("Codex primary" in line for line in lines)


def test_build_menu_lines_shows_error_message():
    lines = formatting.build_menu_lines(CLAUDE_ERROR, CODEX_ERROR)
    assert any("credentials file not found" in line for line in lines)
    assert any("codex app-server" in line for line in lines)
