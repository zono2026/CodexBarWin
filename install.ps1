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

# WScript.Shell's CreateShortcut/.Save() marshals shortcut properties through
# the process's ANSI codepage ("Language for non-Unicode programs"). On an
# English-locale host (e.g. GitHub Actions windows-latest) that codepage
# cannot represent Japanese characters, so Save() throws for any shortcut
# path, target, argument, or working directory containing them - even though
# the same code works on a Japanese-locale machine. IShellLinkW/IPersistFile
# operate on UTF-16 strings end-to-end and are unaffected by the ANSI
# codepage, so shortcut creation is done through them instead.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace CodexBarWinInstaller
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

    public static class UnicodeShortcut
    {
        public static void Save(string shortcutPath, string targetPath, string arguments, string workingDirectory, string description)
        {
            ShellLinkCoClass raw = new ShellLinkCoClass();
            try
            {
                IShellLinkW link = (IShellLinkW)raw;
                link.SetPath(targetPath);
                link.SetArguments(arguments);
                link.SetWorkingDirectory(workingDirectory);
                if (!string.IsNullOrEmpty(description))
                {
                    link.SetDescription(description);
                }

                IPersistFile persistFile = (IPersistFile)raw;
                persistFile.Save(shortcutPath, true);
            }
            finally
            {
                Marshal.FinalReleaseComObject(raw);
            }
        }
    }
}
'@ -Language CSharp

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
        $commands = Get-Command python.exe -All -ErrorAction SilentlyContinue
        if ($commands) {
            $candidates += $commands | ForEach-Object { $_.Source }
        }
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        if ($candidate.IndexOf("\Microsoft\WindowsApps\", [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            continue
        }
        $pythonw = Join-Path (Split-Path -Parent $candidate) "pythonw.exe"
        if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
            continue
        }
        $tkVersion = & $candidate -c "import tkinter; print(tkinter.TkVersion)" 2>$null
        if ($LASTEXITCODE -ne 0) {
            continue
        }
        try {
            $pythonwCheck = Start-Process -FilePath $pythonw -ArgumentList '-c "import tkinter"' -Wait -PassThru
        }
        catch {
            continue
        }
        if ($pythonwCheck.ExitCode -ne 0) {
            continue
        }
        return [pscustomobject]@{
            Python = $candidate
            Pythonw = $pythonw
            TkVersion = (($tkVersion | Select-Object -First 1) -as [string]).Trim()
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
    [CodexBarWinInstaller.UnicodeShortcut]::Save(
        $shortcutPath,
        $python.Pythonw,
        ('"' + $mainScript + '"'),
        $InstallDir,
        "CodexBarWin startup"
    )

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
