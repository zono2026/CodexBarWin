"""Persist and load user-configurable settings for CodexBarWin."""

import json
import os
import re

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEFAULT_POLL_INTERVAL_MINUTES = 5
ALLOWED_POLL_INTERVALS_MINUTES = (1, 5, 15)
DEFAULT_BACKGROUND_COLOR = "#1e1e1e"
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _defaults():
    return {
        "poll_interval_minutes": DEFAULT_POLL_INTERVAL_MINUTES,
        "background_color": DEFAULT_BACKGROUND_COLOR,
    }


def _is_valid_hex_color(value):
    return isinstance(value, str) and bool(_HEX_COLOR_RE.match(value))


def load_config(config_path=DEFAULT_CONFIG_PATH):
    defaults = _defaults()

    if not os.path.exists(config_path):
        save_config(defaults, config_path=config_path)
        return defaults

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return defaults

    if not isinstance(data, dict):
        return defaults

    merged = {**defaults, **data}
    if merged["poll_interval_minutes"] not in ALLOWED_POLL_INTERVALS_MINUTES:
        merged["poll_interval_minutes"] = DEFAULT_POLL_INTERVAL_MINUTES
    if not _is_valid_hex_color(merged["background_color"]):
        merged["background_color"] = DEFAULT_BACKGROUND_COLOR

    return merged


def save_config(data, config_path=DEFAULT_CONFIG_PATH):
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def set_poll_interval(minutes, config_path=DEFAULT_CONFIG_PATH):
    if minutes not in ALLOWED_POLL_INTERVALS_MINUTES:
        raise ValueError(f"poll_interval_minutes must be one of {ALLOWED_POLL_INTERVALS_MINUTES}")

    current = load_config(config_path=config_path)
    current["poll_interval_minutes"] = minutes
    save_config(current, config_path=config_path)
    return current


def set_background_color(hex_color, config_path=DEFAULT_CONFIG_PATH):
    if not _is_valid_hex_color(hex_color):
        raise ValueError("background_color must be a '#rrggbb' hex string")

    current = load_config(config_path=config_path)
    current["background_color"] = hex_color
    save_config(current, config_path=config_path)
    return current
