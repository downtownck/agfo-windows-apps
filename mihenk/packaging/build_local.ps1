# AGFO Mihenk - build (and optionally install) on this computer. No administrator rights needed.
# The EXE is produced on this computer, so it carries no "downloaded from the internet" mark
# (no web-filter / SmartScreen block, unlike a prebuilt EXE download).
# Usage:  Derle-ve-Kur.cmd   (or: powershell -File packaging\build_local.ps1 [-Install])
# ASCII-only on purpose: avoids legacy Windows PowerShell encoding problems.
param([switch]$Install)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'python_runtime.ps1')

$appName = 'AGFO-Mihenk'
$cache = Join-Path $env:LOCALAPPDATA 'AGFO\Mihenk\build'
$venv = Join-Path $cache 'venv'
$dist = Join-Path $root 'dist'
$log = Join-Path $cache 'last-build.txt'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
Set-Content -LiteralPath $log -Value ('AGFO Mihenk local build ' + (Get-Date -Format s)) -Encoding UTF8

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
    $pys = @(Find-AGFOPythons)
    if (-not $pys.Count) { throw 'Python 3.10+ (with tkinter) was not found. Install it from https://www.python.org/downloads/windows/ and run this again.' }
    Write-Host ('Python candidates: ' + (($pys | ForEach-Object { "$($_.Version)" }) -join ', '))

    $exe = Join-Path $dist ($appName + '.exe')
    $ico = Join-Path $root 'assets\agfo-mihenk.ico'
    $selfTest = Join-Path $cache 'selftest.txt'
    $built = $false
    $tried = @()
    foreach ($py in $pys) {
        $tag = "$($py.Version)"
        $tried += $tag
        Write-Host ''
        Write-Host ('=== Python ' + $tag + ' (' + $py.Python + ') ===')
        # Separate build environment per Python version (does not touch the Python installation).
        $venv = Join-Path $cache ('venv-' + $tag)
        $vpy = Join-Path $venv 'Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $vpy)) {
            Write-Host 'Preparing the build environment (first run only)...'
            if ((Invoke-Native $py.Python @('-m', 'venv', $venv)) -ne 0) { Write-Host 'venv failed, trying the next Python.'; continue }
        }
        Write-Host 'Checking libraries: PyInstaller ...'
        $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', 'PyInstaller>=6.16,<7')
        if ((Invoke-Native $vpy $pipArgs) -ne 0) { Write-Host 'Could not install PyInstaller (check the internet connection), trying the next Python.'; continue }

        Write-Host 'Building the EXE (1-2 minutes)...'
        if (Test-Path -LiteralPath $exe) { Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue }
        $pyiArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', $appName,
                     '--distpath', $dist, '--workpath', (Join-Path $cache ('work-' + $tag)), '--specpath', (Join-Path $cache 'spec'),
                     '--paths', $root, '--icon', $ico,
                     '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.ttk', '--hidden-import', 'tkinter.messagebox',
                     '--hidden-import', 'tkinter.simpledialog',
                     '--hidden-import', 'mihenk_app', '--hidden-import', 'mihenk_core', '--hidden-import', 'mihenk_update',
                     '--hidden-import', 'mihenk_db', '--hidden-import', 'mihenk_store', '--hidden-import', 'mihenk_repo',
                     '--hidden-import', 'mihenk_states', '--hidden-import', 'mihenk_validate', '--hidden-import', 'mihenk_audit',
                     '--hidden-import', 'mihenk_scheduler', '--hidden-import', 'mihenk_seed', '--hidden-import', 'mihenk_theme',
                     '--hidden-import', 'mihenk_widgets', '--hidden-import', 'mihenk_dialogs', '--hidden-import', 'mihenk_screens',
                     '--hidden-import', 'mihenk_selftest', '--hidden-import', 'sqlite3',
                     '--hidden-import', 'agfo_github_update',
                     (Join-Path $root 'app.pyw'))
        if ((Invoke-Native $vpy $pyiArgs) -ne 0) { Write-Host 'PyInstaller build failed, trying the next Python.'; continue }
        if (-not (Test-Path -LiteralPath $exe)) { Write-Host 'Build finished but the EXE was not found, trying the next Python.'; continue }

        # Self-test: the EXE must really contain tkinter (a broken bundle would only fail when the user opens it).
        Write-Host 'Self-test of the new EXE...'
        if (Test-Path -LiteralPath $selfTest) { Remove-Item -LiteralPath $selfTest -Force -ErrorAction SilentlyContinue }
        $proc = Start-Process -FilePath $exe -ArgumentList @('--selftest', ('"' + $selfTest + '"')) -PassThru
        if (-not $proc.WaitForExit(120000)) { try { $proc.Kill() } catch {}; Write-Host 'Self-test timed out, trying the next Python.'; continue }
        $res = ''
        if (Test-Path -LiteralPath $selfTest) { $res = (Get-Content -LiteralPath $selfTest -Raw) }
        Add-Content -LiteralPath $log -Value ('SELFTEST Python ' + $tag + ' exit=' + $proc.ExitCode + ' ' + $res)
        if ($proc.ExitCode -eq 0 -and $res -match '^OK ') {
            Write-Host ('Self-test passed: ' + $res.Trim()) -ForegroundColor Green
            $built = $true
            break
        }
        Write-Host ('Self-test FAILED with Python ' + $tag + ': ' + $res.Trim()) -ForegroundColor Yellow
        Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
    }
    if (-not $built) { throw ('No Python produced a working EXE (tried: ' + ($tried -join ', ') + '). See the details file.') }
    Write-Host ('EXE ready: ' + $exe) -ForegroundColor Green

    if ($Install) {
        $dir = Join-Path $env:LOCALAPPDATA 'Programs\AGFO-Mihenk'
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
        foreach ($lnkPath in @((Join-Path $menu 'AGFO Mihenk.lnk'), (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Mihenk.lnk'))) {
            $l = $sh.CreateShortcut($lnkPath)
            $l.TargetPath = $target
            $l.WorkingDirectory = $dir
            $l.IconLocation = $target + ',0'
            $l.Description = 'AGFO Mihenk'
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
