# CodexBarWin Public Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe, repeatable per-user installation and uninstallation so downloaded source paths and temporary Python runtimes are never persisted in Windows Startup.

**Architecture:** `install.ps1` validates a tkinter-capable Python installation, reports optional CLI/auth readiness, copies only runtime files to `%LOCALAPPDATA%\CodexBarWin`, and creates a fixed per-user Startup shortcut. `uninstall.ps1` removes only the matching installed instance and preserves `config.json` unless explicitly asked to delete settings. Pytest integration tests execute both scripts against temporary directories with launch disabled.

**Tech Stack:** PowerShell 5.1+, WScript.Shell COM, Python 3, tkinter, pytest

---

### Task 1: Installer integration tests

**Files:**
- Create: `tests/test_installer.py`
- Create: `install.ps1`

- [ ] **Step 1: Add failing installer tests**

Add subprocess helpers that invoke `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`. Test that installation copies the seven runtime modules, preserves an existing `config.json`, creates `CodexBarWin.lnk` using the supplied tkinter-capable Python's sibling `pythonw.exe`, and rejects a supplied executable that cannot import tkinter.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_installer.py -q`.

Expected: failure because `install.ps1` does not exist.

- [ ] **Step 3: Implement the minimum installer**

Create an advanced PowerShell script with testable `SourceDir`, `InstallDir`, `StartupDir`, `PythonExe`, and `NoLaunch` parameters. Validate Python with `import tkinter`, require sibling `pythonw.exe`, copy the runtime allow-list, preserve settings, and create the shortcut through `WScript.Shell`.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/test_installer.py -q`, then the full suite.

Expected: installer tests pass and no prior tests regress.

### Task 2: Diagnostics and idempotent updates

**Files:**
- Modify: `tests/test_installer.py`
- Modify: `install.ps1`

- [ ] **Step 1: Add failing diagnostics tests**

Require machine-readable status lines for Python/tkinter, pythonw, Codex CLI, Codex authentication, Claude credentials, installed files, and Startup registration. Re-run installation into the same directory and assert success without replacing `config.json`.

- [ ] **Step 2: Verify RED**

Run the targeted tests and confirm failure because diagnostic status lines are absent.

- [ ] **Step 3: Implement diagnostics**

Treat Python/tkinter/pythonw failures as blocking. Treat Codex CLI/authentication and Claude credential absence as warnings so the widget can still install and display `N/A`. Never print credential contents.

- [ ] **Step 4: Verify GREEN**

Run targeted and full tests.

Expected: all tests pass.

### Task 3: Safe uninstaller

**Files:**
- Modify: `tests/test_installer.py`
- Create: `uninstall.ps1`

- [ ] **Step 1: Add failing uninstall tests**

Install into temporary paths, run the uninstaller, and assert that the matching shortcut and runtime files are removed while `config.json` remains. Add a second test using `-RemoveConfig` and assert that the installation directory is removed. Add a safety test proving an unrelated shortcut with the same filename is retained.

- [ ] **Step 2: Verify RED**

Run targeted tests.

Expected: failure because `uninstall.ps1` does not exist.

- [ ] **Step 3: Implement the minimum safe uninstaller**

Stop only Python processes whose command line contains the fixed installed `main.py`. Delete the Startup shortcut only when its arguments reference that path. Delete only the runtime allow-list by default; delete settings and the now-empty directory only with `-RemoveConfig`.

- [ ] **Step 4: Verify GREEN**

Run targeted and full tests.

Expected: all tests pass.

### Task 4: Public documentation

**Files:**
- Modify: `README.md`
- Modify: `tests/test_installer.py`

- [ ] **Step 1: Add a failing documentation test**

Require README sections for recommended installation, prerequisites, fixed installation path, update/reinstall behavior, uninstallation with settings preservation/removal, PowerShell execution guidance, diagnostics, and known API limitations.

- [ ] **Step 2: Verify RED**

Run the documentation test and confirm it fails on the existing manual-only setup.

- [ ] **Step 3: Update README**

Document `install.ps1` as the recommended path, keep direct source execution as a developer option, and document `uninstall.ps1` with and without `-RemoveConfig`.

- [ ] **Step 4: Verify GREEN and full suite**

Run all tests and `git diff --check`.

Expected: all tests pass and no whitespace errors remain.
