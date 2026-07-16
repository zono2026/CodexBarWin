# CodexBarWin Stable Startup Design

## Goal

Make CodexBarWin survive Codex cache refreshes and cleanup of date-based work folders.

## Selected approach

Install the application files in the fixed per-user directory
`C:\Users\OSKCLT4740\AppData\Local\CodexBarWin` and launch them with the
existing per-user Python 3.14 installation at
`C:\Users\OSKCLT4740\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe`.

This is preferred over packaging a standalone executable because it is a
smaller change and keeps the existing Python workflow easy to update. Keeping
the Codex cache paths is rejected because those paths are not stable.

## Files and state

Copy the runtime application files (`main.py`, its local Python modules, and
the existing `config.json`) into the fixed directory. Do not copy repository
metadata, tests, caches, or temporary files.

Preserving `config.json` keeps the current polling interval and background
color. Future configuration writes occur beside the installed application.

## Startup registration

Replace the per-user Startup shortcut `CodexBarWin.lnk` with these fields:

- Target: the fixed Python 3.14 `pythonw.exe`
- Arguments: the fixed installation's `main.py`
- Working directory: the fixed CodexBarWin directory

The shortcut must not reference `.cache\codex-runtimes` or a dated
`Documents\Codex` directory.

## Verification

1. Confirm Python 3.14 imports `tkinter`.
2. Confirm every required runtime module exists in the fixed directory.
3. Stop the current temporary-path instance.
4. Launch through the Startup shortcut.
5. Confirm the new `pythonw.exe` process remains running and its command line
   references the fixed `main.py`.
6. Re-read the shortcut and confirm all three fields use stable paths.

The visible success condition is the CodexBarWin widget at the lower-right of
the screen; CodexBarWin does not provide a tray icon.

## Rollback

If launch verification fails, restore the previous shortcut fields and leave
the copied fixed-directory files in place for diagnosis. Do not delete the
source worktree or Codex cache as part of this change.
