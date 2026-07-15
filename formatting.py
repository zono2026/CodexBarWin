"""Pure formatting/display-logic helpers shared by the widget UI.

Kept free of tkinter/subprocess/network dependencies so it can be unit
tested without a display or external services.
"""


WEEKLY_WINDOW_THRESHOLD_MINS = 1440  # 1 day; codex windows are either ~5h or ~7d


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
