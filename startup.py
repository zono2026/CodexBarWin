"""Register/unregister CodexBarWin in the Windows Startup folder.

Creates a `.lnk` shortcut in the per-user Startup folder so the widget
launches automatically at logon. The shortcut is created via PowerShell's
WScript.Shell COM object so no extra Python dependency (pywin32) is needed.
"""

import os
import subprocess
import sys

SHORTCUT_NAME = "CodexBarWin.lnk"

_CREATE_NO_WINDOW = 0x08000000

# Shortcut fields are passed through environment variables rather than being
# interpolated into the command string, so paths containing spaces, quotes or
# other PowerShell-special characters cannot break (or inject into) the script.
_POWERSHELL_SCRIPT = (
    "$ws = New-Object -ComObject WScript.Shell; "
    "$sc = $ws.CreateShortcut($env:CODEXBAR_LNK); "
    "$sc.TargetPath = $env:CODEXBAR_TARGET; "
    "$sc.Arguments = $env:CODEXBAR_ARGS; "
    "$sc.WorkingDirectory = $env:CODEXBAR_WORKDIR; "
    "$sc.Save()"
)


def default_startup_dir():
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )


def _pythonw_path():
    # pythonw.exe runs without a console window; plain python.exe would leave
    # a console open for the whole widget lifetime. Fall back to sys.executable
    # for unusual installs that ship no pythonw.exe.
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(candidate):
        return candidate
    return sys.executable


def _main_script_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")


def shortcut_path(startup_dir=None):
    if startup_dir is None:
        startup_dir = default_startup_dir()
    return os.path.join(startup_dir, SHORTCUT_NAME)


def is_registered(startup_dir=None):
    return os.path.exists(shortcut_path(startup_dir))


def _default_run(command, env):
    completed = subprocess.run(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW,
    )
    return completed.returncode == 0


def register(startup_dir=None, run=None):
    """Create the Startup shortcut. Returns True on success, never raises."""
    if os.name != "nt":
        return False
    if run is None:
        run = _default_run

    main_script = _main_script_path()
    env = {
        **os.environ,
        "CODEXBAR_LNK": shortcut_path(startup_dir),
        "CODEXBAR_TARGET": _pythonw_path(),
        "CODEXBAR_ARGS": f'"{main_script}"',
        "CODEXBAR_WORKDIR": os.path.dirname(main_script),
    }
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        _POWERSHELL_SCRIPT,
    ]

    try:
        return bool(run(command, env))
    except Exception:
        return False


def unregister(startup_dir=None):
    """Remove the Startup shortcut. Returns True if absent afterwards, never raises."""
    if os.name != "nt":
        return False

    path = shortcut_path(startup_dir)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True
