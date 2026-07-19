[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "CodexBarWin"),
    [string]$StartupDir = (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"),
    [switch]$RemoveConfig
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

try {
    $InstallDir = [IO.Path]::GetFullPath($InstallDir)
    $StartupDir = [IO.Path]::GetFullPath($StartupDir)
    $mainScript = Join-Path $InstallDir "main.py"
    $shortcutPath = Join-Path $StartupDir "CodexBarWin.lnk"

    try {
        $processes = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $_.Name -eq "pythonw.exe" -and
                $_.CommandLine -and
                $_.CommandLine.IndexOf($mainScript, [StringComparison]::OrdinalIgnoreCase) -ge 0
            }
        foreach ($process in $processes) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-Output "PROCESS_STOP=WARN:unable_to_query"
    }

    $shortcutRemoved = $false
    if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcutMain = $shortcut.Arguments.Trim().Trim('"')
        if ([string]::Equals($shortcutMain, $mainScript, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $shortcutPath -Force
            $shortcutRemoved = $true
        }
    }
    Write-Output "SHORTCUT_REMOVED=$shortcutRemoved"

    foreach ($file in $RuntimeFiles) {
        $path = Join-Path $InstallDir $file
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path -Force
        }
    }

    $configPath = Join-Path $InstallDir "config.json"
    if ($RemoveConfig) {
        if (Test-Path -LiteralPath $configPath -PathType Leaf) {
            Remove-Item -LiteralPath $configPath -Force
        }
        Write-Output "CONFIG_REMOVED=True"
    }
    else {
        Write-Output "CONFIG_PRESERVED=True"
    }

    if (Test-Path -LiteralPath $InstallDir -PathType Container) {
        $remaining = @(Get-ChildItem -LiteralPath $InstallDir -Force)
        if ($remaining.Count -eq 0) {
            Remove-Item -LiteralPath $InstallDir -Force
        }
    }

    Write-Output "UNINSTALL_OK=$InstallDir"
}
catch {
    [Console]::Error.WriteLine("Uninstallation failed: " + $_.Exception.Message)
    exit 1
}
