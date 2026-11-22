# AGFO Router Connect - build (and optionally install) on this computer. No administrator rights needed.
# The EXE is produced on this computer, so it carries no "downloaded from the internet" mark
# (no web-filter / SmartScreen block, unlike a prebuilt EXE download).
# Usage:  Derle-ve-Kur.cmd   (or: powershell -File packaging\build_local.ps1 [-Install])
# ASCII-only on purpose: avoids legacy Windows PowerShell encoding problems.
param([switch]$Install)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'python_runtime.ps1')

$appName = 'AGFO-Router-Connect'
$cache = Join-Path $env:LOCALAPPDATA 'AGFO\RouterConnect\build'
$venv = Join-Path $cache 'venv'
$dist = Join-Path $root 'dist'
$log = Join-Path $cache 'last-build.txt'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
Set-Content -LiteralPath $log -Value ('AGFO Router Connect local build ' + (Get-Date -Format s)) -Encoding UTF8

# Native command runner: warnings written to stderr do not stop the script; success is decided by the exit code only.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $line = "$_"
            Write-Host $line
            Add-Content -LiteralPath $log -Value $line
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
}

try {
    $py = Find-AGFOPython
    if (-not $py) { throw 'Python 3.10+ (with tkinter) was not found. Install it from https://www.python.org/downloads/windows/ and run this again.' }
    Write-Host ('Python: ' + $py.Python)

    # Separate build environment (does not touch the Python installation).
    $vpy = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $vpy)) {
        Write-Host 'Preparing the build environment (first run only)...'
        if ((Invoke-Native $py.Python @('-m', 'venv', $venv)) -ne 0) { throw 'Could not create the build environment (venv).' }
    }
    Write-Host 'Checking libraries: PyInstaller ...'
    $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', 'PyInstaller>=6.16,<7')
    if ((Invoke-Native $vpy $pipArgs) -ne 0) { throw 'Could not install the libraries. Check the internet connection.' }

    Write-Host 'Building the EXE (1-2 minutes)...'
    $ico = Join-Path $root 'assets\agfo-router.ico'
    $pyiArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', $appName,
                 '--distpath', $dist, '--workpath', (Join-Path $cache 'work'), '--specpath', (Join-Path $cache 'spec'),
                 '--paths', $root, '--icon', $ico,
                 '--hidden-import', 'router_app', '--hidden-import', 'router_core', '--hidden-import', 'router_update',
                 '--hidden-import', 'router_wifi', '--hidden-import', 'router_store', '--hidden-import', 'router_startup', '--hidden-import', 'router_history',
                 '--hidden-import', 'agfo_github_update',
                 (Join-Path $root 'app.pyw'))
    if ((Invoke-Native $vpy $pyiArgs) -ne 0) { throw 'PyInstaller build failed.' }
    $exe = Join-Path $dist ($appName + '.exe')
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Build finished but the EXE was not found.' }
    Write-Host ('EXE ready: ' + $exe) -ForegroundColor Green

    if ($Install) {
        $dir = Join-Path $env:LOCALAPPDATA 'Programs\AGFO-Router-Connect'
        $target = Join-Path $dir ($appName + '.exe')
        # Close a running older version so the file is not locked.
        Get-Process -Name $appName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 800
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Copy-Item -LiteralPath $exe -Destination $target -Force
        Unblock-File -LiteralPath $target -ErrorAction SilentlyContinue
        $sh = New-Object -ComObject WScript.Shell
        $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO'
        New-Item -ItemType Directory -Force -Path $menu | Out-Null
        foreach ($lnkPath in @((Join-Path $menu 'AGFO Router Connect.lnk'), (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Router Connect.lnk'))) {
            $l = $sh.CreateShortcut($lnkPath)
            $l.TargetPath = $target
            $l.WorkingDirectory = $dir
            $l.IconLocation = $target + ',0'
            $l.Description = 'AGFO Router Connect'
            $l.Save()
        }
        Write-Host ('Installed: ' + $target) -ForegroundColor Green
        Write-Host 'Shortcuts: Start menu > AGFO and Desktop.'
        Start-Process -FilePath $target -WorkingDirectory $dir
    }
    exit 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Details: ' + $log)
    exit 1
}
