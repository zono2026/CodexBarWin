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
    "startup.py"
)

function Find-PythonExe {
    $candidates = @()
    if ($PythonExe) {
        $candidates += $PythonExe
    }
    else {
        $command = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += $command.Source
        }
        $candidates += Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "Python\pythoncore-*\python.exe") -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            ForEach-Object { $_.FullName }
        $candidates += Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\python.exe") -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            ForEach-Object { $_.FullName }
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        $pythonw = Join-Path (Split-Path -Parent $candidate) "pythonw.exe"
        if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
            continue
        }
        & $candidate -c "import tkinter" *> $null
        if ($LASTEXITCODE -eq 0) {
            return [pscustomobject]@{ Python = $candidate; Pythonw = $pythonw }
        }
    }

    throw "No usable Python with tkinter and pythonw.exe was found. Install standard Python 3 for Windows with Tcl/Tk support."
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

    if (-not $NoLaunch) {
        Start-Process -FilePath $python.Pythonw -ArgumentList ('"' + $mainScript + '"') -WorkingDirectory $InstallDir
    }

    Write-Output "INSTALL_OK=$InstallDir"
}
catch {
    [Console]::Error.WriteLine("Installation failed: " + $_.Exception.Message)
    exit 1
}
