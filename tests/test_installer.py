import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parent.parent
POWERSHELL = shutil.which("powershell") or "powershell"
RUNTIME_FILES = (
    "main.py",
    "claude_polling.py",
    "claude_usage.py",
    "codex_usage.py",
    "config.py",
    "formatting.py",
    "startup.py",
)


def run_script(script_name, *arguments):
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / script_name),
            *map(str, arguments),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        errors="replace",
    )


def read_shortcut(shortcut_path):
    command = (
        "$ws=New-Object -ComObject WScript.Shell;"
        f"$sc=$ws.CreateShortcut('{shortcut_path}');"
        "[pscustomobject]@{TargetPath=$sc.TargetPath;Arguments=$sc.Arguments;"
        "WorkingDirectory=$sc.WorkingDirectory}|ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    )
    return json.loads(completed.stdout)


def test_install_copies_runtime_preserves_config_and_creates_fixed_shortcut(tmp_path):
    install_dir = tmp_path / "installed"
    startup_dir = tmp_path / "startup"
    install_dir.mkdir()
    startup_dir.mkdir()
    config_path = install_dir / "config.json"
    config_path.write_text('{"background_color":"#123456"}', encoding="utf-8")

    completed = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-PythonExe",
        sys.executable,
        "-NoLaunch",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert all((install_dir / name).is_file() for name in RUNTIME_FILES)
    assert (install_dir / "uninstall.ps1").is_file()
    assert config_path.read_text(encoding="utf-8") == '{"background_color":"#123456"}'

    shortcut = read_shortcut(startup_dir / "CodexBarWin.lnk")
    expected_pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
    assert shortcut["TargetPath"].casefold() == expected_pythonw.casefold()
    assert shortcut["Arguments"] == f'"{install_dir / "main.py"}"'
    assert shortcut["WorkingDirectory"].casefold() == str(install_dir).casefold()


def test_install_rejects_python_without_tkinter(tmp_path):
    fake_python = tmp_path / "python.exe"
    fake_pythonw = tmp_path / "pythonw.exe"
    where = Path(os.environ["SystemRoot"]) / "System32" / "where.exe"
    shutil.copy2(where, fake_python)
    shutil.copy2(where, fake_pythonw)

    completed = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        tmp_path / "installed",
        "-StartupDir",
        tmp_path / "startup",
        "-PythonExe",
        fake_python,
        "-NoLaunch",
    )

    assert completed.returncode != 0
    assert "tkinter" in (completed.stdout + completed.stderr).lower()
    assert not (tmp_path / "installed" / "main.py").exists()


def test_install_reports_diagnostics_and_is_idempotent(tmp_path):
    install_dir = tmp_path / "installed"
    startup_dir = tmp_path / "startup"

    first = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-PythonExe",
        sys.executable,
        "-NoLaunch",
    )
    assert first.returncode == 0, first.stdout + first.stderr

    config_path = install_dir / "config.json"
    config_path.write_text('{"poll_interval_minutes":15}', encoding="utf-8")
    second = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-PythonExe",
        sys.executable,
        "-NoLaunch",
    )

    assert second.returncode == 0, second.stdout + second.stderr
    assert config_path.read_text(encoding="utf-8") == '{"poll_interval_minutes":15}'
    for status in (
        "PYTHON_OK=",
        "TKINTER_OK=",
        "PYTHONW_OK=",
        "CODEX_CLI=",
        "CODEX_AUTH=",
        "CLAUDE_AUTH=",
        "INSTALLED_FILES=7",
        "STARTUP_OK=",
    ):
        assert status in second.stdout


def test_auto_discovery_prefers_direct_user_python_over_windowsapps_alias(tmp_path):
    direct_python = Path(sys.executable)
    local_app_data = Path(os.environ["LOCALAPPDATA"])
    supported_roots = (
        local_app_data / "Python",
        local_app_data / "Programs" / "Python",
    )
    if not any(root in direct_python.parents for root in supported_roots):
        pytest.skip("test runner is not using a direct per-user Python installation")
    if not direct_python.with_name("pythonw.exe").is_file():
        pytest.skip("test runner Python has no pythonw.exe")

    install_dir = tmp_path / "installed"
    startup_dir = tmp_path / "startup"
    completed = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-NoLaunch",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    shortcut = read_shortcut(startup_dir / "CodexBarWin.lnk")
    assert shortcut["TargetPath"].casefold() == str(
        direct_python.with_name("pythonw.exe")
    ).casefold()


def install_for_uninstall_test(tmp_path):
    install_dir = tmp_path / "installed"
    startup_dir = tmp_path / "startup"
    completed = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-PythonExe",
        sys.executable,
        "-NoLaunch",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return install_dir, startup_dir


def test_uninstall_removes_runtime_and_matching_shortcut_but_preserves_config(tmp_path):
    install_dir, startup_dir = install_for_uninstall_test(tmp_path)
    config_path = install_dir / "config.json"
    config_path.write_text('{"background_color":"#abcdef"}', encoding="utf-8")

    completed = run_script(
        "uninstall.ps1",
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not (startup_dir / "CodexBarWin.lnk").exists()
    assert all(not (install_dir / name).exists() for name in RUNTIME_FILES)
    assert config_path.read_text(encoding="utf-8") == '{"background_color":"#abcdef"}'


def test_uninstall_remove_config_deletes_install_directory(tmp_path):
    install_dir, startup_dir = install_for_uninstall_test(tmp_path)
    (install_dir / "config.json").write_text("{}", encoding="utf-8")

    completed = run_script(
        "uninstall.ps1",
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-RemoveConfig",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not install_dir.exists()


def test_uninstall_keeps_unrelated_shortcut_with_same_name(tmp_path):
    install_dir = tmp_path / "installed"
    startup_dir = tmp_path / "startup"
    install_dir.mkdir()
    startup_dir.mkdir()
    shortcut_path = startup_dir / "CodexBarWin.lnk"
    command = (
        "$ws=New-Object -ComObject WScript.Shell;"
        f"$sc=$ws.CreateShortcut('{shortcut_path}');"
        "$sc.TargetPath=$env:ComSpec;"
        "$sc.Arguments='/c exit 0';"
        f"$sc.WorkingDirectory='{tmp_path}';"
        "$sc.Save()"
    )
    subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
    )

    completed = run_script(
        "uninstall.ps1",
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert shortcut_path.exists()


def test_readme_documents_public_install_update_and_uninstall():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for required_text in (
        "install.ps1",
        "%LOCALAPPDATA%\\CodexBarWin",
        "PowerShell",
        "tkinter",
        "Codex CLI",
        "再インストール",
        "config.json",
        "uninstall.ps1",
        "-RemoveConfig",
        "非公開API",
    ):
        assert required_text in readme
