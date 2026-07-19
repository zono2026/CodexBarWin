"""Pure formatting/display-logic helpers shared by the widget UI.

Kept free of tkinter/subprocess/network dependencies so it can be unit
tested without a display or external services.
"""


WEEKLY_WINDOW_THRESHOLD_MINS = 1440  # 1 day; codex windows are either ~5h or ~7d

# Error classification is allowlist-based: raw error strings are only ever used
# as *input* to keyword matching below, never returned or embedded in output.
# Anything that doesn't match a known keyword (including tokens, file paths, or
# unrecognized exception text) falls through to the generic fallback message,
# so unexpected/sensitive text can never reach the UI.
_FALLBACK_ERROR_MESSAGE = "利用状況を取得できませんでした"

_CLAUDE_ERROR_RULES = (
    (("credentials", "accesstoken", "401", "403"), "認証情報を確認してください"),
    (("http error",), "サーバーエラー"),
    (("request failed", "timeout", "timed out"), "通信エラー"),
    (("invalid response", "json"), "レスポンス形式エラー"),
)

_CODEX_ERROR_RULES = (
    (("command not found",), "CLIが見つかりません"),
    (("failed to start",), "起動失敗"),
    (
        ("initialize", "communication", "timeout", "timed out", "closed the connection"),
        "通信エラー",
    ),
)


def _classify_error(raw_error, rules):
    if not isinstance(raw_error, str):
        return _FALLBACK_ERROR_MESSAGE

    lowered = raw_error.lower()
    for keywords, message in rules:
        if any(keyword in lowered for keyword in keywords):
            return message
    return _FALLBACK_ERROR_MESSAGE


def _classify_claude_error(raw_error):
    return _classify_error(raw_error, _CLAUDE_ERROR_RULES)


def _classify_codex_error(raw_error):
    return _classify_error(raw_error, _CODEX_ERROR_RULES)


def _fmt_pct(value):
    if value is None:
        return "?"
    return f"{value:.0f}%"


def _codex_window_percent(codex_result, is_weekly):
    # Codex's `primary`/`secondary` fields are not reliably 5h/7d by position —
    # some accounts only populate `primary` with the weekly (7d) window and
    # leave `secondary` entirely empty. Pick by actual window_duration_mins
    # instead of assuming primary=5h, secondary=7d.
    for key in ("primary", "secondary"):
        entry = codex_result.get(key) or {}
        minutes = entry.get("window_duration_mins")
        if minutes is None:
            continue
        if (minutes >= WEEKLY_WINDOW_THRESHOLD_MINS) == is_weekly:
            return entry.get("used_percent")
    return None


def build_title(claude_result, codex_result):
    parts = []

    if claude_result and "error" not in claude_result:
        five = claude_result.get("five_hour", {}).get("utilization")
        seven = claude_result.get("seven_day", {}).get("utilization")
        suffix = " (stale)" if claude_result.get("stale") else ""
        parts.append(f"Claude 5h:{_fmt_pct(five)} 7d:{_fmt_pct(seven)}{suffix}")
    elif claude_result and claude_result.get("error") == "rate_limited":
        parts.append("Claude:RATE LIMITED")
    else:
        parts.append("Claude:N/A")

    if codex_result and "error" not in codex_result:
        five = _codex_window_percent(codex_result, is_weekly=False)
        seven = _codex_window_percent(codex_result, is_weekly=True)
        parts.append(f"Codex 5h:{_fmt_pct(five)} 7d:{_fmt_pct(seven)}")
    else:
        parts.append("Codex:N/A")

    return " / ".join(parts)


def _status_lines(label, result, classify_error, last_success_str):
    if result is None:
        status = "未取得"
    elif "error" in result:
        status = "エラー"
    else:
        status = "正常"

    lines = [f"{label}: {status}"]
    if result is not None and "error" in result:
        lines.append(f"  概要: {classify_error(result.get('error'))}")
    lines.append(f"  最終成功時刻: {last_success_str or '(なし)'}")
    return lines


def build_status_detail(claude_result, codex_result, claude_last_success_str, codex_last_success_str):
    """Build the multi-line text shown in the "状態・エラー詳細" window.

    Only pre-classified fixed messages (see _classify_claude_error /
    _classify_codex_error) and caller-supplied timestamp strings are embedded
    here — raw error text, tokens, and file paths never flow into the result.
    """
    lines = []
    lines.extend(_status_lines("Claude", claude_result, _classify_claude_error, claude_last_success_str))
    lines.append("")
    lines.extend(_status_lines("Codex", codex_result, _classify_codex_error, codex_last_success_str))
    return "\n".join(lines)
