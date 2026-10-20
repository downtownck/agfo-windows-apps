# AGFO Phantom Shot - Windows derleme (GitHub Actions ya da Python 3.12 kurulu bir PC).
# Uretir: dist\AGFO-Phantom-Shot.exe (tek dosya; calistirmak/kurmak icin yonetici gerekmez).
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $root
$python = (Get-Command python.exe -ErrorAction Stop).Source
Write-Host ('Python: ' + $python)

& $python -m pip install --disable-pip-version-check --quiet 'PyInstaller>=6.12,<7' 'mss>=9,<11' 'pynput>=1.7,<2' 'Pillow>=11,<13' 'pystray>=0.19,<0.20'
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

$work = Join-Path $env:RUNNER_TEMP 'agfo-phantom-build'
if (-not $env:RUNNER_TEMP) { $work = Join-Path $env:TEMP 'agfo-phantom-build' }
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name AGFO-Phantom-Shot `
    --distpath (Join-Path $root 'dist') --workpath (Join-Path $work 'work') --specpath (Join-Path $work 'spec') `
    --icon (Join-Path $root 'assets\agfo-phantom.ico') --paths (Join-Path $root '.') `
    --add-data ((Join-Path $root 'assets\agfo-phantom.ico') + ';assets') `
    --hidden-import phantom_core --hidden-import phantom_update --hidden-import agfo_github_update `
    --collect-submodules pynput --collect-submodules pystray --collect-submodules mss --hidden-import PIL.Image `
    (Join-Path $root 'app.pyw')
if ($LASTEXITCODE) { throw 'PyInstaller failed' }

$exe = Join-Path $root 'dist\AGFO-Phantom-Shot.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'EXE not found' }

# Derlenmis EXE oz-testi: tum bilesenler yuklenir, GUI kurulur, mss bir kare yakalar (--windowed oldugu
# icin cikti dosyadan ve cikis kodundan dogrulanir).
$png = Join-Path $work 'smoke.png'
$p = Start-Process -FilePath $exe -ArgumentList @('--smoke', ('"' + $png + '"')) -PassThru
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'smoke timeout' }
if ($p.ExitCode -ne 0) { Write-Annotation 'smoke' ('exit ' + $p.ExitCode); throw ('smoke failed, exit ' + $p.ExitCode) }
if (-not (Test-Path -LiteralPath $png)) { throw 'smoke wrote no screenshot' }
Write-Host ('BUILT: ' + $exe) -ForegroundColor Green
