"""CodexBarWin: Windows system-tray usage monitor for Claude Code and Codex CLI."""

import concurrent.futures
import threading

import pystray
from PIL import Image, ImageDraw

import claude_usage
import codex_usage
import config
import formatting

APP_NAME = "CodexBarWin"
ICON_SIZE = 64
# codex_usage.fetch_usage performs up to 2 sequential timeout-bounded reads
# (initialize, then rateLimits), so its worst case is 2x its own timeout, not
# 1x. claude_usage.fetch_usage does a single HTTP round-trip capped at its own
# timeout. Both now run in parallel (see _poll_once), so a single poll cycle's
# worst case is the MAX of the two legs, plus a margin for taskkill/subprocess
# teardown overhead in codex_usage._terminate.
_POLL_CYCLE_WORST_CASE_SECONDS = max(
    claude_usage.REQUEST_TIMEOUT_SECONDS,
    codex_usage.DEFAULT_TIMEOUT_SECONDS * 2,
)
POLL_THREAD_JOIN_TIMEOUT_SECONDS = _POLL_CYCLE_WORST_CASE_SECONDS + 10

_state_lock = threading.Lock()
_state = {"claude": None, "codex": None}
_stop_event = threading.Event()
_force_refresh_event = threading.Event()
_poll_thread = None


def _draw_icon(color):
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = 8
    draw.ellipse((margin, margin, ICON_SIZE - margin, ICON_SIZE - margin), fill=color)
    return image


def _get_state():
    with _state_lock:
        return _state["claude"], _state["codex"]


def _set_state(claude_result, codex_result):
    with _state_lock:
        _state["claude"] = claude_result
        _state["codex"] = codex_result


def _refresh_icon(icon):
    claude_result, codex_result = _get_state()
    values = formatting.collect_utilizations(claude_result, codex_result)
    icon.icon = _draw_icon(formatting.icon_color_for(values))
    icon.title = formatting.build_title(claude_result, codex_result)[:127]
    icon.update_menu()


def _safe_fetch(fetch_fn):
    # Both claude_usage.fetch_usage and codex_usage.fetch_usage already catch
    # their own expected failure modes and return {"error": ...}, but this is a
    # last-resort guard: an uncaught exception here would otherwise propagate
    # through _poll_once and permanently kill the daemon _poll_loop thread,
    # silently freezing the tray icon forever with no visible error.
    try:
        return fetch_fn()
    except Exception as e:
        return {"error": f"unexpected error ({type(e).__name__})"}


def _poll_once(icon):
    # Run both fetches concurrently: each is an independent I/O call (HTTP
    # request / subprocess round-trip), so running them sequentially would make
    # a single poll cycle take up to the SUM of both timeouts instead of the MAX.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claude_future = executor.submit(_safe_fetch, claude_usage.fetch_usage)
        codex_future = executor.submit(_safe_fetch, codex_usage.fetch_usage)
        claude_result = claude_future.result()
        codex_result = codex_future.result()
    _set_state(claude_result, codex_result)
    _refresh_icon(icon)


def _poll_loop(icon):
    while not _stop_event.is_set():
        _poll_once(icon)
        interval_minutes = config.load_config()["poll_interval_minutes"]
        _force_refresh_event.wait(timeout=interval_minutes * 60)
        _force_refresh_event.clear()


def _on_refresh_now(icon, item):
    _force_refresh_event.set()


def _on_exit(icon, item):
    _stop_event.set()
    _force_refresh_event.set()
    # Wait for any in-flight poll cycle to actually finish (including
    # codex_usage.fetch_usage()'s `finally: _terminate(process)`) before letting
    # icon.stop() allow the process to exit — otherwise a codex app-server
    # subprocess spawned mid-poll could be orphaned.
    if _poll_thread is not None:
        _poll_thread.join(timeout=POLL_THREAD_JOIN_TIMEOUT_SECONDS)
    icon.stop()


def _make_set_interval_handler(minutes):
    def handler(icon, item):
        config.set_poll_interval(minutes)
        _force_refresh_event.set()

    return handler


def _interval_menu_items():
    # Read the current interval once per menu build and close over that single
    # value, instead of each item's `checked` callback independently re-reading
    # and re-parsing config.json (icon.update_menu() runs on every poll cycle,
    # so that would mean 3x redundant disk reads per cycle for the same value).
    current_interval = config.load_config()["poll_interval_minutes"]
    items = []
    for minutes in config.ALLOWED_POLL_INTERVALS_MINUTES:
        items.append(
            pystray.MenuItem(
                f"{minutes}分",
                _make_set_interval_handler(minutes),
                checked=lambda item, m=minutes, current=current_interval: current == m,
                radio=True,
            )
        )
    return items


def _build_menu_items():
    claude_result, codex_result = _get_state()
    for line in formatting.build_menu_lines(claude_result, codex_result):
        yield pystray.MenuItem(line, None, enabled=False)
    yield pystray.Menu.SEPARATOR
    yield pystray.MenuItem("ポーリング間隔", pystray.Menu(*_interval_menu_items()))
    yield pystray.MenuItem("今すぐ更新", _on_refresh_now)
    yield pystray.MenuItem("終了", _on_exit)


def main():
    global _poll_thread

    icon = pystray.Icon(
        APP_NAME,
        _draw_icon(formatting.ICON_COLOR_GRAY),
        APP_NAME,
        menu=pystray.Menu(_build_menu_items),
    )

    def setup(icon):
        global _poll_thread
        icon.visible = True
        _poll_thread = threading.Thread(target=_poll_loop, args=(icon,), daemon=True)
        _poll_thread.start()

    icon.run(setup=setup)


if __name__ == "__main__":
    main()
