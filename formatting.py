"""Pure formatting/display-logic helpers shared by the tray UI.

Kept free of pystray/subprocess/network dependencies so it can be unit
tested without a display or external services.
"""

from datetime import datetime, timezone

ICON_COLOR_GRAY = (128, 128, 128)
ICON_COLOR_GREEN = (40, 160, 80)
ICON_COLOR_YELLOW = (230, 180, 30)
ICON_COLOR_RED = (220, 50, 47)


def parse_claude_resets_at(iso_string):
    if not iso_string:
        return None
    try:
        return datetime.fromisoformat(iso_string)
    except ValueError:
        return None


def parse_codex_resets_at(unix_timestamp):
    if unix_timestamp is None:
        return None
    return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)


def format_local_time(dt):
    if dt is None:
        return "?"
    return dt.astimezone().strftime("%H:%M")


def _fmt_pct(value):
    if value is None:
        return "?"
    return f"{value:.0f}%"


def collect_utilizations(claude_result, codex_result):
    values = []
    if claude_result and "error" not in claude_result:
        for key in ("five_hour", "seven_day"):
            v = claude_result.get(key, {}).get("utilization")
            if v is not None:
                values.append(v)
    if codex_result and "error" not in codex_result:
        for key in ("primary", "secondary"):
            v = codex_result.get(key, {}).get("used_percent")
            if v is not None:
                values.append(v)
    return values


def icon_color_for(values):
    if not values:
        return ICON_COLOR_GRAY
    peak = max(values)
    if peak >= 80:
        return ICON_COLOR_RED
    if peak >= 50:
        return ICON_COLOR_YELLOW
    return ICON_COLOR_GREEN


def build_title(claude_result, codex_result):
    parts = []

    if claude_result and "error" not in claude_result:
        five = claude_result.get("five_hour", {}).get("utilization")
        seven = claude_result.get("seven_day", {}).get("utilization")
        parts.append(f"Claude 5h:{_fmt_pct(five)} 7d:{_fmt_pct(seven)}")
    else:
        parts.append("Claude:N/A")

    if codex_result and "error" not in codex_result:
        primary = codex_result.get("primary", {}).get("used_percent")
        parts.append(f"Codex:{_fmt_pct(primary)}")
    else:
        parts.append("Codex:N/A")

    return " / ".join(parts)


def build_menu_lines(claude_result, codex_result):
    lines = []

    if claude_result and "error" not in claude_result:
        five = claude_result.get("five_hour", {})
        seven = claude_result.get("seven_day", {})
        five_reset = format_local_time(parse_claude_resets_at(five.get("resets_at")))
        seven_reset = format_local_time(parse_claude_resets_at(seven.get("resets_at")))
        lines.append(f"Claude 5h: {_fmt_pct(five.get('utilization'))} (reset {five_reset})")
        lines.append(f"Claude 7d: {_fmt_pct(seven.get('utilization'))} (reset {seven_reset})")
    else:
        error = (claude_result or {}).get("error", "unknown error")
        lines.append(f"Claude: N/A ({error})")

    if codex_result and "error" not in codex_result:
        primary = codex_result.get("primary", {})
        secondary = codex_result.get("secondary", {})
        primary_reset = format_local_time(parse_codex_resets_at(primary.get("resets_at")))
        secondary_reset = format_local_time(parse_codex_resets_at(secondary.get("resets_at")))
        lines.append(f"Codex primary: {_fmt_pct(primary.get('used_percent'))} (reset {primary_reset})")
        lines.append(f"Codex secondary: {_fmt_pct(secondary.get('used_percent'))} (reset {secondary_reset})")
    else:
        error = (codex_result or {}).get("error", "unknown error")
        lines.append(f"Codex: N/A ({error})")

    return lines
