# CodexBarWin Stable Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install CodexBarWin at stable per-user paths and make its Startup shortcut independent of Codex caches and dated work folders.

**Architecture:** Copy only runtime files into `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin`. Launch the fixed `main.py` with the existing per-user Python 3.14 `pythonw.exe` through a per-user Startup shortcut.

**Tech Stack:** Python 3.14, tkinter, PowerShell, Windows WScript.Shell shortcut COM API

---

### Task 1: Validate stable prerequisites

**Files:**
- Read: `C:\Users\OSKCLT4740\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- Read: `C:\Users\OSKCLT4740\Documents\Codex\2026-07-15\mjfaccin-codex-text-link-https-www\work\CodexBarWin\*.py`

- [ ] **Step 1: Verify Python and tkinter**

Run the fixed Python executable with `import tkinter` and print `tkinter.TkVersion`.

Expected: exit code 0 and Tk version 8.6.

- [ ] **Step 2: Verify all runtime source files exist**

Check `main.py`, `claude_polling.py`, `claude_usage.py`, `codex_usage.py`, `config.py`, `formatting.py`, and `startup.py`.

Expected: all seven paths exist.

### Task 2: Install runtime files

**Files:**
- Create: `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\main.py`
- Create: `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\claude_polling.py`
- Create: `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\claude_usage.py`
- Create: `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\codex_usage.py`
- Create: `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\config.py`
- Create: `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\formatting.py`
- Create: `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\startup.py`
- Create or preserve: `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\config.json`

- [ ] **Step 1: Create the fixed installation directory**

Create the directory if it does not already exist. Do not remove existing files.

- [ ] **Step 2: Copy runtime modules**

Copy the seven required Python files from the worktree, overwriting older installed copies.

- [ ] **Step 3: Preserve configuration**

If the fixed directory has no `config.json`, copy the source worktree's current `config.json`. If it already exists, leave it unchanged.

- [ ] **Step 4: Compile-check the installed application**

Run Python 3.14 `-m py_compile` against all seven installed modules.

Expected: exit code 0.

### Task 3: Replace Startup registration

**Files:**
- Modify: `C:\Users\OSKCLT4740\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\CodexBarWin.lnk`

- [ ] **Step 1: Read and retain the current shortcut fields for rollback**

Read `TargetPath`, `Arguments`, and `WorkingDirectory` through `WScript.Shell` before overwriting them.

- [ ] **Step 2: Save stable shortcut fields**

Set target to `C:\Users\OSKCLT4740\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe`, arguments to the quoted fixed `main.py`, and working directory to `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin`.

- [ ] **Step 3: Re-read and validate the shortcut**

Expected: no field contains `.cache\codex-runtimes` or `Documents\Codex\2026-`.

### Task 4: Verify launch without screen operations

**Files:**
- Read: installed runtime and Startup shortcut from Tasks 2 and 3

- [ ] **Step 1: Stop only the prior CodexBarWin Python process**

Identify the process by command line containing the old dated `CodexBarWin\main.py` path, then stop only that PID.

- [ ] **Step 2: Launch the Startup shortcut programmatically**

Use `Start-Process` on `CodexBarWin.lnk`; do not capture the screen or automate clicks.

- [ ] **Step 3: Verify the stable process remains alive**

After three seconds, query process command lines and require one `pythonw.exe` process whose command line contains `C:\Users\OSKCLT4740\AppData\Local\CodexBarWin\main.py`.

Expected: one matching live process and no dependency on a Codex cache or dated work folder.

- [ ] **Step 4: Run the project tests**

Run the repository test suite using Python 3.14.

Expected: all tests pass.
