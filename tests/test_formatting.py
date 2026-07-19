import sys
from pathlib import Path

import pytest

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


def test_build_status_detail_shows_normal_status_and_last_success():
    detail = formatting.build_status_detail(
        CLAUDE_OK, CODEX_OK, "2026-07-19 20:00:00", "2026-07-19 20:00:05"
    )
    assert "Claude: 正常" in detail
    assert "Codex: 正常" in detail
    assert "2026-07-19 20:00:00" in detail
    assert "2026-07-19 20:00:05" in detail


def test_build_status_detail_shows_not_yet_fetched_when_result_is_none():
    detail = formatting.build_status_detail(None, None, None, None)
    assert "Claude: 未取得" in detail
    assert "Codex: 未取得" in detail
    assert detail.count("(なし)") == 2


@pytest.mark.parametrize(
    "raw_error,expected_message",
    [
        ("credentials file not found", "認証情報を確認してください"),
        ("accessToken not found in credentials file", "認証情報を確認してください"),
        ("http error 401", "認証情報を確認してください"),
        ("http error 403", "認証情報を確認してください"),
        ("http error 500", "サーバーエラー"),
        ("request failed (TimeoutError)", "通信エラー"),
        ("invalid response body", "レスポンス形式エラー"),
    ],
)
def test_build_status_detail_classifies_known_claude_errors(raw_error, expected_message):
    detail = formatting.build_status_detail({"error": raw_error}, CODEX_OK, None, None)
    assert f"概要: {expected_message}" in detail


@pytest.mark.parametrize(
    "raw_error,expected_message",
    [
        ("codex command not found (is Codex CLI installed and on PATH?)", "CLIが見つかりません"),
        ("failed to start codex app-server (FileNotFoundError)", "起動失敗"),
        ("codex app-server initialize failed: {'code': -1}", "通信エラー"),
        ("codex app-server communication failed (OSError)", "通信エラー"),
        ("timed out waiting for codex app-server response", "通信エラー"),
        ("codex app-server closed the connection unexpectedly", "通信エラー"),
    ],
)
def test_build_status_detail_classifies_known_codex_errors(raw_error, expected_message):
    detail = formatting.build_status_detail(CLAUDE_OK, {"error": raw_error}, None, None)
    assert f"概要: {expected_message}" in detail


def test_build_status_detail_falls_back_for_unknown_error():
    result = {"error": "some completely unexpected internal exception text with /secret/path"}
    detail = formatting.build_status_detail(result, CODEX_OK, None, None)
    assert "概要: 利用状況を取得できませんでした" in detail
    assert "/secret/path" not in detail


def test_build_status_detail_never_leaks_token_like_strings():
    sensitive_error = (
        "request failed (TimeoutError) token=sk-ant-oat01-abcdefghijklmnopqrstuvwxyz"
    )
    detail = formatting.build_status_detail({"error": sensitive_error}, CODEX_OK, None, None)
    assert "sk-ant-oat01" not in detail
    assert "token=" not in detail
    assert "概要: 通信エラー" in detail


def test_build_status_detail_never_leaks_file_paths():
    sensitive_error = "credentials file not found at C:\\Users\\nakat\\.claude\\.credentials.json"
    detail = formatting.build_status_detail({"error": sensitive_error}, CODEX_OK, None, None)
    assert "C:\\Users\\nakat" not in detail
    assert ".credentials.json" not in detail
    assert "概要: 認証情報を確認してください" in detail


def test_build_status_detail_never_leaks_unrecognized_exception_text():
    sensitive_error = "Traceback: raise ValueError('unexpected internal state: user_id=12345')"
    detail = formatting.build_status_detail(CLAUDE_OK, {"error": sensitive_error}, None, None)
    assert "user_id=12345" not in detail
    assert "Traceback" not in detail
    assert "ValueError" not in detail
    assert "概要: 利用状況を取得できませんでした" in detail
