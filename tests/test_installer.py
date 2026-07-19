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


def run_script(script_name, *arguments, env=None):
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
        env=env,
    )


# WScript.Shell's CreateShortcut() marshals shortcut properties through the
# process's ANSI codepage ("Language for non-Unicode programs"). On an
# English-locale host that codepage cannot represent Japanese characters, so
# reading a shortcut this way is not a reliable way to verify install.ps1's
# Unicode-safe output. This helper reads the .lnk file through the same
# wide-character IShellLinkW/IPersistFile COM interfaces install.ps1 uses to
# write it, so verification is not itself subject to the ANSI codepage bug
# it is trying to catch.
_SHORTCUT_READER_TYPE_DEFINITION = """
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace CodexBarWinTest
{
    [ComImport]
    [Guid("00021401-0000-0000-C000-000000000046")]
    internal class ShellLinkCoClass
    {
    }

    [ComImport]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    [Guid("000214F9-0000-0000-C000-000000000046")]
    internal interface IShellLinkW
    {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cchMaxPath, IntPtr pfd, uint fFlags);
        void GetIDList(out IntPtr ppidl);
        void SetIDList(IntPtr pidl);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cchMaxName);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cchMaxPath);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cchMaxPath);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
        void GetHotkey(out short pwHotkey);
        void SetHotkey(short wHotkey);
        void GetShowCmd(out int piShowCmd);
        void SetShowCmd(int iShowCmd);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cchIconPath, out int piIcon);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
        void Resolve(IntPtr hwnd, uint fFlags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
    }

    public class ShortcutInfo
    {
        public string TargetPath { get; set; }
        public string Arguments { get; set; }
        public string WorkingDirectory { get; set; }
    }

    public static class UnicodeShortcutReader
    {
        public static ShortcutInfo Read(string shortcutPath)
        {
            ShellLinkCoClass raw = new ShellLinkCoClass();
            try
            {
                IPersistFile persistFile = (IPersistFile)raw;
                persistFile.Load(shortcutPath, 0);

                IShellLinkW link = (IShellLinkW)raw;
                StringBuilder targetBuilder = new StringBuilder(2048);
                link.GetPath(targetBuilder, targetBuilder.Capacity, IntPtr.Zero, 0);

                StringBuilder argumentsBuilder = new StringBuilder(2048);
                link.GetArguments(argumentsBuilder, argumentsBuilder.Capacity);

                StringBuilder workingDirectoryBuilder = new StringBuilder(2048);
                link.GetWorkingDirectory(workingDirectoryBuilder, workingDirectoryBuilder.Capacity);

                ShortcutInfo info = new ShortcutInfo();
                info.TargetPath = targetBuilder.ToString();
                info.Arguments = argumentsBuilder.ToString();
                info.WorkingDirectory = workingDirectoryBuilder.ToString();
                return info;
            }
            finally
            {
                Marshal.FinalReleaseComObject(raw);
            }
        }
    }
}
"""


def read_shortcut(shortcut_path):
    command = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
        "Add-Type -TypeDefinition @'\n"
        + _SHORTCUT_READER_TYPE_DEFINITION.strip("\n")
        + "\n'@ -Language CSharp\n"
        f"$info = [CodexBarWinTest.UnicodeShortcutReader]::Read('{shortcut_path}')\n"
        "$info | ConvertTo-Json -Compress\n"
    )
    completed = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
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


def test_install_rejects_python_when_pythonw_tkinter_check_fails(tmp_path):
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        pytest.skip("test runner Python has no pythonw.exe")

    shadow_modules = tmp_path / "shadow-modules"
    shadow_modules.mkdir()
    (shadow_modules / "tkinter.py").write_text(
        "import pathlib, sys\n"
        "if pathlib.Path(sys.executable).name.casefold() == 'pythonw.exe':\n"
        "    raise ImportError('pythonw tkinter failure')\n"
        "TkVersion = 8.6\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(shadow_modules)

    completed = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        tmp_path / "installed",
        "-StartupDir",
        tmp_path / "startup",
        "-PythonExe",
        sys.executable,
        "-NoLaunch",
        env=env,
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


def test_auto_discovery_skips_windowsapps_alias_and_uses_next_path_python(tmp_path):
    valid_python = Path(sys.executable)
    valid_pythonw = valid_python.with_name("pythonw.exe")
    if not valid_pythonw.is_file():
        pytest.skip("test runner Python has no pythonw.exe")

    fake_local_app_data = tmp_path / "local-app-data"
    windows_apps = fake_local_app_data / "Microsoft" / "WindowsApps"
    windows_apps.mkdir(parents=True)
    where = Path(os.environ["SystemRoot"]) / "System32" / "where.exe"
    shutil.copy2(where, windows_apps / "python.exe")
    shutil.copy2(where, windows_apps / "pythonw.exe")

    install_dir = tmp_path / "installed"
    startup_dir = tmp_path / "startup"
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(fake_local_app_data)
    env["PATH"] = (
        str(windows_apps)
        + os.pathsep
        + str(valid_python.parent)
        + os.pathsep
        + env.get("PATH", "")
    )

    completed = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-NoLaunch",
        env=env,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    shortcut = read_shortcut(startup_dir / "CodexBarWin.lnk")
    assert shortcut["TargetPath"].casefold() == str(valid_pythonw).casefold()


def test_auto_discovery_skips_candidate_without_pythonw(tmp_path):
    valid_python = Path(sys.executable)
    valid_pythonw = valid_python.with_name("pythonw.exe")
    if not valid_pythonw.is_file():
        pytest.skip("test runner Python has no pythonw.exe")

    fake_local_app_data = tmp_path / "local-app-data"
    incomplete_python_dir = fake_local_app_data / "Python" / "pythoncore-99.0-64"
    incomplete_python_dir.mkdir(parents=True)
    incomplete_python = incomplete_python_dir / "python.exe"
    shutil.copy2(valid_python, incomplete_python)
    assert not incomplete_python.with_name("pythonw.exe").exists()

    install_dir = tmp_path / "installed"
    startup_dir = tmp_path / "startup"
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(fake_local_app_data)
    env["PATH"] = str(valid_python.parent) + os.pathsep + env.get("PATH", "")

    completed = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-NoLaunch",
        env=env,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    shortcut = read_shortcut(startup_dir / "CodexBarWin.lnk")
    assert shortcut["TargetPath"].casefold() == str(valid_pythonw).casefold()
    assert shortcut["TargetPath"].casefold() != str(
        incomplete_python.with_name("pythonw.exe")
    ).casefold()


def test_auto_discovery_skips_candidate_with_unusable_pythonw(tmp_path):
    valid_python = Path(sys.executable)
    valid_pythonw = valid_python.with_name("pythonw.exe")
    if not valid_pythonw.is_file():
        pytest.skip("test runner Python has no pythonw.exe")

    fake_local_app_data = tmp_path / "local-app-data"
    broken_python_dir = fake_local_app_data / "Python" / "pythoncore-99.0-64"
    broken_python_dir.mkdir(parents=True)
    shutil.copy2(valid_python, broken_python_dir / "python.exe")
    where = Path(os.environ["SystemRoot"]) / "System32" / "where.exe"
    shutil.copy2(where, broken_python_dir / "pythonw.exe")

    install_dir = tmp_path / "installed"
    startup_dir = tmp_path / "startup"
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(fake_local_app_data)
    env["PATH"] = str(valid_python.parent) + os.pathsep + env.get("PATH", "")

    completed = run_script(
        "install.ps1",
        "-SourceDir",
        ROOT,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-NoLaunch",
        env=env,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    shortcut = read_shortcut(startup_dir / "CodexBarWin.lnk")
    assert shortcut["TargetPath"].casefold() == str(valid_pythonw).casefold()


def test_install_supports_spaces_and_non_ascii_characters_in_paths(tmp_path):
    source_dir = tmp_path / "source 日本語"
    install_dir = tmp_path / "installed 日本語"
    startup_dir = tmp_path / "startup 日本語"
    source_dir.mkdir()
    for name in (*RUNTIME_FILES, "uninstall.ps1"):
        shutil.copy2(ROOT / name, source_dir / name)

    completed = run_script(
        "install.ps1",
        "-SourceDir",
        source_dir,
        "-InstallDir",
        install_dir,
        "-StartupDir",
        startup_dir,
        "-PythonExe",
        sys.executable,
        "-NoLaunch",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    shortcut = read_shortcut(startup_dir / "CodexBarWin.lnk")
    assert shortcut["Arguments"] == f'"{install_dir / "main.py"}"'
    assert shortcut["WorkingDirectory"].casefold() == str(install_dir).casefold()


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
