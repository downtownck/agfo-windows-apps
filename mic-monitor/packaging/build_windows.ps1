# AGFO Mic Monitor - Windows derleme (GitHub Actions ya da Python 3.12 kurulu bir PC).
# Uretir: dist\AGFO-Mic-Monitor.exe (tek dosya; calistirmak/kurmak icin yonetici gerekmez).
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $root
$python = (Get-Command python.exe -ErrorAction Stop).Source
Write-Host ('Python: ' + $python)

& $python -m pip install --disable-pip-version-check --quiet 'PyInstaller>=6.12,<7' 'sounddevice>=0.5.2,<0.6' 'numpy>=1.26,<3'
if ($LASTEXITCODE) { throw 'pip install failed' }

function Write-Annotation([string]$title, [string]$text) {
    $n = 0
    for ($k = 0; $k -lt $text.Length -and $n -lt 8; $k += 3500) {
        $n++
        $c = $text.Substring($k, [Math]::Min(3500, $text.Length - $k))
        $msg = $c.Replace('%', '%25').Replace("`r", '').Replace("`n", '%0A')
        Write-Host ('::error title=' + $title + ' ' + $n + '::' + $msg)
    }
}

# Birim testleri (ortak modul + cekirdek + guncelleyici saf fonksiyonlar).
$env:PYTHONIOENCODING = 'utf-8'
& $python -I (Join-Path $root 'tests\test_core.py') $root; if ($LASTEXITCODE) { throw 'test_core failed' }
& $python -I (Join-Path $root 'tests\test_update.py') $root; if ($LASTEXITCODE) { throw 'test_update failed' }
& $python -I (Join-Path $root 'tests\test_engine.py') $root; if ($LASTEXITCODE) { throw 'test_engine failed' }
& $python -I (Join-Path $root 'tests\test_gui.py') $root; if ($LASTEXITCODE) { throw 'test_gui failed' }

$work = Join-Path $env:RUNNER_TEMP 'agfo-micmon-build'
if (-not $env:RUNNER_TEMP) { $work = Join-Path $env:TEMP 'agfo-micmon-build' }
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name AGFO-Mic-Monitor `
    --distpath (Join-Path $root 'dist') --workpath (Join-Path $work 'work') --specpath (Join-Path $work 'spec') `
    --icon (Join-Path $root 'assets\agfo-micmon.ico') --paths (Join-Path $root '.') `
    --add-data ((Join-Path $root 'assets\agfo-micmon.ico') + ';assets') `
    --hidden-import mic_core --hidden-import mic_engine --hidden-import mic_update --hidden-import agfo_github_update `
    --collect-all _sounddevice_data --hidden-import sounddevice --hidden-import _cffi_backend `
    (Join-Path $root 'app.pyw')
if ($LASTEXITCODE) { throw 'PyInstaller failed' }

$exe = Join-Path $root 'dist\AGFO-Mic-Monitor.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'EXE not found' }

# Derlenmis EXE oz-testi: PortAudio (WASAPI) yuklenir, RAW ozel mod ayari olusturulur, cihazlar listelenir,
# GUI kurulur (--windowed oldugu icin sonuc rapor dosyasindan ve cikis kodundan dogrulanir).
$rep = Join-Path $work 'smoke.txt'
$p = Start-Process -FilePath $exe -ArgumentList @('--smoke', ('"' + $rep + '"')) -PassThru
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'smoke timeout' }
$txt = if (Test-Path -LiteralPath $rep) { Get-Content -LiteralPath $rep -Raw } else { '' }
Write-Host $txt
if ($p.ExitCode -ne 0 -or $txt -notmatch 'AGFO MIC MONITOR SMOKE OK') { Write-Annotation 'smoke' ('exit ' + $p.ExitCode + ' ' + $txt); throw ('smoke failed, exit ' + $p.ExitCode) }
if ($txt -notmatch 'wasapi raw settings: ok') { throw 'WASAPI RAW settings not verified' }
Write-Host ('BUILT: ' + $exe) -ForegroundColor Green
