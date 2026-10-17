# Build a Windows-native installer with Python/PyInstaller and optionally run it.
# Double-click Derle-ve-Kur.cmd, no manual terminal setup required.
[CmdletBinding()]
param([switch]$Install)
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $root
# Build caches must never be shared through cloud drives or copied to another PC.
# Keep only finished setup binaries (dist) next to the downloaded source.
$buildCache = Join-Path $env:LOCALAPPDATA 'AGFO-BackupSync\build-cache'
$dist = Join-Path $buildCache 'dist'
$publishDist = Join-Path $root 'dist'
$venv = Join-Path $buildCache 'venv'
$stage = Join-Path $buildCache 'payload'
$work = Join-Path $buildCache 'work'
$spec = Join-Path $buildCache 'spec'
$icon = Join-Path $root 'assets\agfo-backupsync.ico'
$trayPng = Join-Path $root 'assets\agfo-tray.png'
$logdir = Join-Path $root '.build-logs'
[void][System.IO.Directory]::CreateDirectory($logdir)
$log = Join-Path $logdir 'last-build.txt'
try { Start-Transcript -Path $log -Force | Out-Null } catch { }

function Test-PythonExecutable([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        $result = @(& $Executable -c 'import sys; print(sys.executable)' 2>$null)
        return ($LASTEXITCODE -eq 0 -and $result.Count -gt 0)
    } catch { return $false }
}
function Find-WindowsPython {
    # Probe working interpreters directly before calling a possibly broken py.exe launcher.
    $candidates = @()
    foreach ($base in @((Join-Path $env:LOCALAPPDATA 'Programs\Python'), $env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not $base -or -not (Test-Path -LiteralPath $base)) { continue }
        $candidates += @(Get-ChildItem -LiteralPath $base -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'python.exe' })
    }
    foreach ($p in $candidates) {
        if (Test-PythonExecutable $p) { return [string]$p }
    }
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand -and (Test-PythonExecutable $pythonCommand.Source)) {
        return [string]$pythonCommand.Source
    }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        foreach ($ver in @('-3.14', '-3.13', '-3.12', '-3')) {
            try {
                $result = @(& py.exe $ver -c 'import sys;print(sys.executable)' 2>$null)
                if ($LASTEXITCODE -eq 0 -and $result.Count -gt 0 -and (Test-PythonExecutable ([string]$result[-1]))) {
                    return [string]$result[-1]
                }
            } catch { }
        }
    }
    return ''
}
function Assert-Exit([string]$Label) {
    if ($LASTEXITCODE -ne 0) { throw ($Label + ' failed with exit code ' + $LASTEXITCODE) }
}
try {
    Write-Host 'AGFO BackupSync v2.3.3 - Windows Python derleyici' -ForegroundColor Cyan
    $python = Find-WindowsPython
    if (-not $python) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            throw 'Python ve winget bulunamadi. Windows App Installer kurulmali.'
        }
        Write-Host 'Calisan Python bulunamadi. winget ile Python 3.12 kuruluyor...' -ForegroundColor Yellow
        & winget.exe install --id Python.Python.3.12 --exact --source winget --scope user --silent --accept-source-agreements --accept-package-agreements
        Assert-Exit 'Python winget kurulumu'
        $python = Find-WindowsPython
        if (-not $python) { throw 'Python kuruldu ancak bu oturumda yolu bulunamadi. Oturumu acip tekrar Derle-ve-Kur.cmd dosyasini calistirin.' }
    }
    Write-Host ('Python: ' + $python)
    Write-Host 'PowerShell dosyalari Windows parser ile dogrulaniyor...'
    foreach ($file in @(Get-ChildItem -LiteralPath (Join-Path $root 'payload') -Filter '*.ps1' -File)) {
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
        if ($errors -and $errors.Count) {
            throw ($file.Name + ' / satir ' + $errors[0].Extent.StartLineNumber + ': ' + $errors[0].Message)
        }
    }
    Write-Host 'PowerShell ayrisma testi: BASARILI' -ForegroundColor Green
    & (Join-Path $root 'payload\AGFO-BackupSync-Test.ps1')
    Write-Host 'Python ag kesfi ve kurulum kaynak testleri calistiriliyor...'
    & $python -m unittest discover -s (Join-Path $root 'tests') -v
    Assert-Exit 'Python regresyon testleri'
    # Run isolated build-environment checks in Python. This avoids brittle
    # assumptions about pyvenv.cfg layout and tests pip separately from Python.
    # All diagnostic output is visible in the transcript.
    Write-Host 'Python sanal ortami hazirlaniyor ve pip ayrica kontrol ediliyor...'
    & $python (Join-Path $root 'packaging\prepare_build_env.py') --venv $venv
    Assert-Exit 'Python sanal ortam hazirligi'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    Write-Host ('Derleme ortami: ' + $venv)
    Write-Host 'PyInstaller / pystray / Pillow kutuphaneleri kontrol ediliyor...'
    & $venvPython -m pip install --disable-pip-version-check 'PyInstaller>=6.12,<7' 'pystray>=0.19,<1' 'Pillow>=11,<13'
    Assert-Exit 'Python pip kutuphaneleri'
    foreach ($dir in @($dist, $stage, $work, $spec)) { [void][System.IO.Directory]::CreateDirectory($dir) }
    Write-Host '1/2: Bildirim alani uygulamasi derleniyor...'
    & $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name AGFO-BackupSync --distpath $dist --workpath $work --specpath $spec `
        --icon $icon --paths (Join-Path $root 'src') `
        --hidden-import pystray._win32 --hidden-import agfo_network --hidden-import agfo_drives `
        --hidden-import agfo_selfupdate --hidden-import agfo_github_update --hidden-import agfo_installer --add-data ($trayPng + ';assets') `
        (Join-Path $root 'src\agfo_tray.py')
    Assert-Exit 'Tray EXE derlemesi'
    $trayExe = Join-Path $dist 'AGFO-BackupSync.exe'
    if (-not (Test-Path -LiteralPath $trayExe)) { throw 'Derlenen tray exe bulunamadi.' }
    # Create a clean stage; never bundle previous build files.
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    [void][System.IO.Directory]::CreateDirectory($stage)
    Copy-Item -Path (Join-Path $root 'payload\*') -Destination $stage -Force
    Copy-Item -LiteralPath $trayExe -Destination $stage -Force
    $hashes = [ordered]@{}
    foreach ($file in @(Get-ChildItem -LiteralPath $stage -File | Sort-Object Name)) {
        $hashes[$file.Name] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $manifest = [ordered]@{ version = '2.3.3'; files = $hashes }
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText((Join-Path $stage 'manifest.json'), ($manifest | ConvertTo-Json -Depth 8), $utf8)
    Write-Host '2/2: Yukleyici EXE derleniyor (yonetici onayli)...'
    & $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin `
        --name AGFO-BackupSync-Setup --distpath $dist --workpath $work --specpath $spec `
        --icon $icon --add-data ($stage + ';payload') `
        (Join-Path $root 'src\agfo_installer.py')
    Assert-Exit 'Setup EXE derlemesi'
    $setupExe = Join-Path $dist 'AGFO-BackupSync-Setup.exe'
    if (-not (Test-Path -LiteralPath $setupExe)) { throw 'Setup exe bulunamadi.' }
    # Publish only finished executables to the shared project folder.
    [void][System.IO.Directory]::CreateDirectory($publishDist)
    Copy-Item -LiteralPath $trayExe -Destination (Join-Path $publishDist 'AGFO-BackupSync.exe') -Force
    Copy-Item -LiteralPath $setupExe -Destination (Join-Path $publishDist 'AGFO-BackupSync-Setup.exe') -Force
    Write-Host ('OLUSTURULDU: ' + (Join-Path $publishDist 'AGFO-BackupSync-Setup.exe')) -ForegroundColor Green
    if ($Install) {
        Write-Host 'Kurucu aciliyor. C:\agfo-backutil icin Windows UAC onayi isteyebilir.'
        Start-Process -FilePath $setupExe -Wait
    }
    Write-Host ('Derleme logu: ' + $log)
    exit 0
} catch {
    Write-Host ('HATA: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Derleme logu: ' + $log) -ForegroundColor Yellow
    exit 1
} finally {
    try { Stop-Transcript | Out-Null } catch { }
}
