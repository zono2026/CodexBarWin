import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import startup


def test_is_registered_false_when_shortcut_missing(tmp_path):
    assert startup.is_registered(startup_dir=str(tmp_path)) is False


def test_is_registered_true_when_shortcut_exists(tmp_path):
    (tmp_path / startup.SHORTCUT_NAME).write_text("stub")

    assert startup.is_registered(startup_dir=str(tmp_path)) is True


def test_register_passes_shortcut_fields_via_env(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.os, "name", "nt")
    captured = {}

    def fake_run(command, env):
        captured["command"] = command
        captured["env"] = env
        return True

    result = startup.register(startup_dir=str(tmp_path), run=fake_run)

    assert result is True
    assert captured["command"][0] == "powershell"
    assert "-NoProfile" in captured["command"]

    env = captured["env"]
    assert env["CODEXBAR_LNK"] == str(tmp_path / startup.SHORTCUT_NAME)
    expected_main = str(Path(startup.__file__).resolve().parent / "main.py")
    assert env["CODEXBAR_ARGS"] == f'"{expected_main}"'
    assert env["CODEXBAR_WORKDIR"] == str(Path(expected_main).parent)
    # The shortcut target must be a real interpreter path so the shortcut
    # works no matter where the user's Python is installed.
    assert Path(env["CODEXBAR_TARGET"]).name in ("pythonw.exe", Path(sys.executable).name)


def test_register_returns_false_when_run_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.os, "name", "nt")

    assert startup.register(startup_dir=str(tmp_path), run=lambda command, env: False) is False


def test_register_returns_false_when_run_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.os, "name", "nt")

    def raising_run(command, env):
        raise OSError("powershell not found")

    assert startup.register(startup_dir=str(tmp_path), run=raising_run) is False


def test_register_returns_false_on_non_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.os, "name", "posix")

    assert startup.register(startup_dir=str(tmp_path), run=lambda command, env: True) is False


def test_unregister_removes_shortcut(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.os, "name", "nt")
    shortcut = tmp_path / startup.SHORTCUT_NAME
    shortcut.write_text("stub")

    assert startup.unregister(startup_dir=str(tmp_path)) is True
    assert not shortcut.exists()


def test_unregister_succeeds_when_shortcut_already_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.os, "name", "nt")

    assert startup.unregister(startup_dir=str(tmp_path)) is True
