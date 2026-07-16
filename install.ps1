[CmdletBinding()]
param(
    [string]$SourceDir = $PSScriptRoot,
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "CodexBarWin"),
    [string]$StartupDir = (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"),
    [string]$PythonExe,
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RuntimeFiles = @(
    "main.py",
    "claude_polling.py",
    "claude_usage.py",
    "codex_usage.py",
    "config.py",
    "formatting.py",
    "startup.py",
    "uninstall.ps1"
)

function Find-PythonExe {
    $candidates = @()
    if ($PythonExe) {
        $candidates += $PythonExe
    }
    else {
        $candidates += Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "Python\pythoncore-*\python.exe") -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            ForEach-Object { $_.FullName }
        $candidates += Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\python.exe") -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            ForEach-Object { $_.FullName }
        $command = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += $command.Source
        }
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        $pythonw = Join-Path (Split-Path -Parent $candidate) "pythonw.exe"
        if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
            continue
        }
        $tkVersion = & $candidate -c "import tkinter; print(tkinter.TkVersion)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return [pscustomobject]@{
                Python = $candidate
                Pythonw = $pythonw
                TkVersion = (($tkVersion | Select-Object -First 1) -as [string]).Trim()
            }
        }
    }

    throw "No usable Python with tkinter and pythonw.exe was found. Install standard Python 3 for Windows with Tcl/Tk support."
}

function Write-OptionalDiagnostics {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if ($codex) {
        Write-Output "CODEX_CLI=OK:$($codex.Source)"
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $codex.Source login status *> $null
            $loginExitCode = $LASTEXITCODE
        }
        catch {
            $loginExitCode = 1
        }
        finally {
            $ErrorActionPreference = $previousPreference
        }
        if ($loginExitCode -eq 0) {
            Write-Output "CODEX_AUTH=OK"
        }
        else {
            Write-Output "CODEX_AUTH=WARN:not_authenticated"
        }
    }
    else {
        Write-Output "CODEX_CLI=WARN:not_found"
        Write-Output "CODEX_AUTH=WARN:not_checked"
    }

    $credentialsPath = Join-Path $HOME ".claude\.credentials.json"
    try {
        $credentials = Get-Content -LiteralPath $credentialsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($credentials.claudeAiOauth.accessToken) {
            Write-Output "CLAUDE_AUTH=OK"
        }
        else {
            Write-Output "CLAUDE_AUTH=WARN:token_missing"
        }
    }
    catch {
        Write-Output "CLAUDE_AUTH=WARN:credentials_unavailable"
    }
}

try {
    $SourceDir = [IO.Path]::GetFullPath($SourceDir)
    $InstallDir = [IO.Path]::GetFullPath($InstallDir)
    $StartupDir = [IO.Path]::GetFullPath($StartupDir)

    foreach ($file in $RuntimeFiles) {
        $sourcePath = Join-Path $SourceDir $file
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Required runtime file is missing: $sourcePath"
        }
    }

    $python = Find-PythonExe
    Write-Output "PYTHON_OK=$($python.Python)"
    Write-Output "TKINTER_OK=$($python.TkVersion)"
    Write-Output "PYTHONW_OK=$($python.Pythonw)"
    Write-OptionalDiagnostics

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    New-Item -ItemType Directory -Path $StartupDir -Force | Out-Null
    foreach ($file in $RuntimeFiles) {
        Copy-Item -LiteralPath (Join-Path $SourceDir $file) -Destination (Join-Path $InstallDir $file) -Force
    }

    $mainScript = Join-Path $InstallDir "main.py"
    $shortcutPath = Join-Path $StartupDir "CodexBarWin.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $python.Pythonw
    $shortcut.Arguments = '"' + $mainScript + '"'
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Description = "CodexBarWin startup"
    $shortcut.Save()

    Write-Output "INSTALLED_FILES=7"
    Write-Output "STARTUP_OK=$shortcutPath"

    if (-not $NoLaunch) {
        Start-Process -FilePath $python.Pythonw -ArgumentList ('"' + $mainScript + '"') -WorkingDirectory $InstallDir
    }

    Write-Output "INSTALL_OK=$InstallDir"
}
catch {
    [Console]::Error.WriteLine("Installation failed: " + $_.Exception.Message)
    exit 1
}
