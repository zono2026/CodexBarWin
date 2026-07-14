"""Fetch Codex CLI usage/rate-limit info via the official `codex app-server` JSON-RPC API.

Spawns a fresh `codex app-server` process per poll (simpler and more robust
than maintaining a long-lived connection), performs the required
initialize/initialized handshake, then calls `account/rateLimits/read`.
"""

import ctypes
import json
import os
import queue
import shutil
import subprocess
import threading
import time

CODEX_COMMAND = ["codex", "app-server"]
CLIENT_INFO = {"name": "codexbar_win", "title": "CodexBar for Windows", "version": "0.1.0"}
DEFAULT_TIMEOUT_SECONDS = 5

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9


class CodexUsageError(Exception):
    pass


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_job_handle = None


def _get_job_handle():
    """Lazily create a Windows Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.

    Any process assigned to this job is killed automatically by the OS the
    moment this job's last handle is closed — which happens whenever THIS
    Python process ends, for any reason (normal exit, unhandled exception,
    Task Manager "End Task", Ctrl+C, OS shutdown/logoff). This is what actually
    guarantees a spawned `codex app-server` cannot be orphaned; the
    `taskkill /T` in `_RealCodexProcess.terminate()` only handles the graceful
    per-poll-cycle cleanup path.
    """
    global _job_handle
    if _job_handle is not None:
        return _job_handle
    if os.name != "nt":
        return None

    try:
        handle = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        if not handle:
            return None

        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = ctypes.windll.kernel32.SetInformationJobObject(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            ctypes.windll.kernel32.CloseHandle(handle)
            return None
    except Exception:
        return None

    _job_handle = handle
    return _job_handle


def _assign_to_job(popen):
    """Best-effort: tie popen's lifetime to this process via the Job Object."""
    job = _get_job_handle()
    if job is None:
        return
    try:
        ctypes.windll.kernel32.AssignProcessToJobObject(job, int(popen._handle))
    except Exception:
        pass


def parse_rate_limits(data):
    rate_limits = (data or {}).get("rateLimits") or {}

    def window(key):
        entry = rate_limits.get(key) or {}
        return {
            "used_percent": entry.get("usedPercent"),
            "window_duration_mins": entry.get("windowDurationMins"),
            "resets_at": entry.get("resetsAt"),
        }

    return {
        "primary": window("primary"),
        "secondary": window("secondary"),
    }


class _RealCodexProcess:
    """Adapter around subprocess.Popen that kills the whole process tree on terminate().

    On Windows, `codex` is invoked through cmd.exe (see `_default_spawn`) because npm
    installs it as a `codex.CMD` shim. Popen.terminate() only kills that cmd.exe
    wrapper, which would orphan the actual `codex.exe app-server` process running
    underneath it. `taskkill /T` kills the wrapper and all of its descendants.
    """

    def __init__(self, popen):
        self._popen = popen
        self.stdin = popen.stdin
        self.stdout = popen.stdout

    def terminate(self):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self._popen.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            self._popen.terminate()


def _default_spawn():
    # npm installs `codex` as a `codex.CMD` shim on Windows. Windows' CreateProcess
    # cannot execute .cmd files directly (only real .exe), so shell=True is required
    # here to let cmd.exe resolve and run the shim. stdin/stdout piping still works
    # through cmd.exe.
    popen = subprocess.Popen(
        " ".join(CODEX_COMMAND),
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    _assign_to_job(popen)
    return _RealCodexProcess(popen)


def _send(process, message):
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def _read_line_with_timeout(process, timeout):
    result_queue = queue.Queue(maxsize=1)

    def reader():
        try:
            result_queue.put(process.stdout.readline())
        except Exception:
            result_queue.put("")

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return None  # timed out; reader thread is left to die with the process
    return result_queue.get()


def _read_response(process, expected_id, timeout, time_source=time.monotonic):
    deadline = time_source() + timeout
    while True:
        remaining = deadline - time_source()
        if remaining <= 0:
            raise CodexUsageError("timed out waiting for codex app-server response")

        line = _read_line_with_timeout(process, remaining)
        if line is None:
            raise CodexUsageError("timed out waiting for codex app-server response")
        if line == "":
            raise CodexUsageError("codex app-server closed the connection unexpectedly")
        line = line.strip()
        if not line:
            continue

        message = json.loads(line)
        if not isinstance(message, dict):
            continue  # not a JSON-RPC object (stray scalar/array); ignore and keep waiting
        if message.get("id") == expected_id:
            return message
        # Ignore notifications / responses for other requests.


def _terminate(process):
    try:
        process.terminate()
    except Exception:
        pass


def fetch_usage(spawn=None, timeout=DEFAULT_TIMEOUT_SECONDS, time_source=time.monotonic):
    if spawn is None:
        if shutil.which("codex") is None:
            return {"error": "codex command not found (is Codex CLI installed and on PATH?)"}
        spawn = _default_spawn

    try:
        process = spawn()
    except Exception as e:
        return {"error": f"failed to start codex app-server ({type(e).__name__})"}

    try:
        _send(process, {"id": 0, "method": "initialize", "params": {"clientInfo": CLIENT_INFO}})
        init_response = _read_response(process, expected_id=0, timeout=timeout, time_source=time_source)
        if "error" in init_response:
            return {"error": f"codex app-server initialize failed: {init_response['error']}"}

        _send(process, {"method": "initialized"})

        _send(process, {"id": 1, "method": "account/rateLimits/read"})
        response = _read_response(process, expected_id=1, timeout=timeout, time_source=time_source)

        if "error" in response:
            return {"error": f"codex app-server error: {response['error']}"}

        return parse_rate_limits(response.get("result", {}))
    except (CodexUsageError, json.JSONDecodeError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"codex app-server communication failed ({type(e).__name__})"}
    finally:
        _terminate(process)
