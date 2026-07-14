"""CodexBarWin: always-on-top Windows widget showing Claude Code and Codex CLI usage."""

import concurrent.futures
import threading
import tkinter as tk
from tkinter import colorchooser

import claude_usage
import codex_usage
import config
import formatting

APP_NAME = "CodexBarWin"
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
WIDGET_TICK_MS = 500
WIDGET_MARGIN_RIGHT = 10
WIDGET_MARGIN_BOTTOM = 50  # leaves room above the Windows taskbar

_state_lock = threading.Lock()
_state = {"claude": None, "codex": None}
_stop_event = threading.Event()
_force_refresh_event = threading.Event()
_poll_thread = None

_root = None
_label = None
_interval_var = None
_context_menu = None
# Cached in memory so `_tick` (which runs every WIDGET_TICK_MS) doesn't have to
# re-read config.json on every tick — only updated (and persisted) when the
# user actually picks a new color via the context menu.
_current_bg_color = None


def _get_state():
    with _state_lock:
        return _state["claude"], _state["codex"]


def _set_state(claude_result, codex_result):
    with _state_lock:
        _state["claude"] = claude_result
        _state["codex"] = codex_result


def _safe_fetch(fetch_fn):
    # Both claude_usage.fetch_usage and codex_usage.fetch_usage already catch
    # their own expected failure modes and return {"error": ...}, but this is a
    # last-resort guard: an uncaught exception here would otherwise propagate
    # through _poll_once and permanently kill the daemon _poll_loop thread,
    # silently freezing the widget forever with no visible error.
    try:
        return fetch_fn()
    except Exception as e:
        return {"error": f"unexpected error ({type(e).__name__})"}


def _poll_once():
    # Run both fetches concurrently: each is an independent I/O call (HTTP
    # request / subprocess round-trip), so running them sequentially would make
    # a single poll cycle take up to the SUM of both timeouts instead of the MAX.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claude_future = executor.submit(_safe_fetch, claude_usage.fetch_usage)
        codex_future = executor.submit(_safe_fetch, codex_usage.fetch_usage)
        claude_result = claude_future.result()
        codex_result = codex_future.result()
    _set_state(claude_result, codex_result)


def _poll_loop():
    while not _stop_event.is_set():
        _poll_once()
        interval_minutes = config.load_config()["poll_interval_minutes"]
        _force_refresh_event.wait(timeout=interval_minutes * 60)
        _force_refresh_event.clear()


def _reposition_to_bottom_right():
    # The label's text length changes every poll (placeholder -> real data,
    # N/A vs full numbers, etc.), so the window must be resized AND
    # repositioned each time — otherwise it stays pinned at its initial size
    # and newer, longer text gets clipped at the original right edge.
    _root.update_idletasks()
    width = _root.winfo_reqwidth()
    height = _root.winfo_reqheight()
    x = _root.winfo_screenwidth() - width - WIDGET_MARGIN_RIGHT
    y = _root.winfo_screenheight() - height - WIDGET_MARGIN_BOTTOM
    _root.geometry(f"{width}x{height}+{x}+{y}")


def _tick():
    # Runs on the tkinter mainloop thread only (scheduled via root.after), so it
    # is the sole place that touches widget state — never call tkinter methods
    # directly from _poll_loop's background thread.
    if _stop_event.is_set():
        _root.destroy()
        return

    claude_result, codex_result = _get_state()
    if claude_result is None and codex_result is None:
        text = "読み込み中..."
    else:
        text = formatting.build_title(claude_result, codex_result)

    _label.config(text=text, fg="white", bg=_current_bg_color)
    _reposition_to_bottom_right()

    _root.after(WIDGET_TICK_MS, _tick)


def _on_refresh_now():
    _force_refresh_event.set()


def _on_exit():
    _stop_event.set()
    _force_refresh_event.set()
    # Wait for any in-flight poll cycle to actually finish (including
    # codex_usage.fetch_usage()'s `finally: _terminate(process)`) before
    # destroying the widget/ending the process — otherwise a codex app-server
    # subprocess spawned mid-poll could be orphaned. (A Job Object in
    # codex_usage.py also guarantees cleanup even if this wait is skipped, e.g.
    # via a hard kill, but this keeps the graceful-exit path clean too.)
    if _poll_thread is not None:
        _poll_thread.join(timeout=POLL_THREAD_JOIN_TIMEOUT_SECONDS)
    _root.destroy()


def _on_change_color():
    global _current_bg_color

    _, hex_color = colorchooser.askcolor(color=_current_bg_color, title="背景色を選択")
    if hex_color is None:  # user cancelled the dialog
        return

    _current_bg_color = hex_color
    config.set_background_color(hex_color)
    _root.configure(bg=hex_color)
    _label.config(bg=hex_color)


def _make_set_interval_handler(minutes):
    def handler():
        config.set_poll_interval(minutes)
        _force_refresh_event.set()

    return handler


def _build_context_menu(root):
    menu = tk.Menu(root, tearoff=0)

    interval_menu = tk.Menu(menu, tearoff=0)
    for minutes in config.ALLOWED_POLL_INTERVALS_MINUTES:
        interval_menu.add_radiobutton(
            label=f"{minutes}分",
            variable=_interval_var,
            value=minutes,
            command=_make_set_interval_handler(minutes),
        )
    menu.add_cascade(label="ポーリング間隔", menu=interval_menu)
    menu.add_command(label="背景色を変更", command=_on_change_color)
    menu.add_separator()
    menu.add_command(label="今すぐ更新", command=_on_refresh_now)
    menu.add_command(label="終了", command=_on_exit)
    return menu


def _show_context_menu(event):
    # Read the current interval once, right before the menu opens, and reflect
    # it in the radio buttons — mirrors the "read config once per menu build"
    # approach used elsewhere (avoids re-reading config.json redundantly).
    current_interval = config.load_config()["poll_interval_minutes"]
    _interval_var.set(current_interval)
    _context_menu.tk_popup(event.x_root, event.y_root)


def _create_widget():
    root = tk.Tk()
    root.title(APP_NAME)
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=_current_bg_color)

    label = tk.Label(
        root,
        text="読み込み中...",
        fg="white",
        bg=_current_bg_color,
        font=("Segoe UI", 10),
        padx=10,
        pady=4,
    )
    label.pack()

    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = root.winfo_screenwidth() - width - WIDGET_MARGIN_RIGHT
    y = root.winfo_screenheight() - height - WIDGET_MARGIN_BOTTOM
    root.geometry(f"{width}x{height}+{x}+{y}")

    label.bind("<Button-3>", _show_context_menu)
    return root, label


def main():
    global _poll_thread, _root, _label, _interval_var, _context_menu, _current_bg_color

    _current_bg_color = config.load_config()["background_color"]
    _root, _label = _create_widget()
    _interval_var = tk.IntVar(master=_root)
    _context_menu = _build_context_menu(_root)

    _poll_thread = threading.Thread(target=_poll_loop, daemon=True)
    _poll_thread.start()

    _root.after(0, _tick)
    _root.mainloop()


if __name__ == "__main__":
    main()
