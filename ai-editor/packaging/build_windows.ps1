# AGFO AI Editor - Windows build (GitHub Actions or a local PC with Python 3.12).
# Produces dist\AGFO-AI-Editor.exe (single file, no admin rights needed to run or install).
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $root
$python = (Get-Command python.exe -ErrorAction Stop).Source
Write-Host ('Python: ' + $python)
& $python -m pip install --disable-pip-version-check --quiet 'PyInstaller>=6.12,<7' 'Pillow>=11,<13' 'pypdf>=5,<7'
if ($LASTEXITCODE) { throw 'pip install failed' }
& $python -m unittest discover -s (Join-Path $root 'tests') -v
if ($LASTEXITCODE) { throw 'unit tests failed' }
$work = Join-Path $env:RUNNER_TEMP 'agfo-editor-build'
if (-not $env:RUNNER_TEMP) { $work = Join-Path $env:TEMP 'agfo-editor-build' }
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name AGFO-AI-Editor `
    --distpath (Join-Path $root 'dist') --workpath (Join-Path $work 'work') --specpath (Join-Path $work 'spec') `
    --icon (Join-Path $root 'assets\agfo-ai-editor.ico') --paths (Join-Path $root 'src') `
    --add-data ((Join-Path $root 'assets\agfo-ai-editor.ico') + ';assets') `
    --hidden-import agfo_editor_core --hidden-import agfo_ai_client --hidden-import agfo_secrets `
    --hidden-import agfo_editor_update --hidden-import agfo_github_update --hidden-import agfo_sources `
    --collect-submodules pypdf `
    (Join-Path $root 'src\agfo_ai_editor.pyw')
if ($LASTEXITCODE) { throw 'PyInstaller failed' }
$exe = Join-Path $root 'dist\AGFO-AI-Editor.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'EXE not found' }
# Frozen self-test (no GUI): modules, diff, DOCX round trip, DPAPI.
$out = Join-Path $work 'selftest.json'
$p = Start-Process -FilePath $exe -ArgumentList @('--selftest', ('"' + $out + '"')) -PassThru
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'self-test timeout' }
if (-not (Test-Path -LiteralPath $out)) { throw ('self-test wrote no result, exit ' + $p.ExitCode) }
$r = Get-Content -LiteralPath $out -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host ('Self-test: ' + ($r | ConvertTo-Json -Compress))
if (-not $r.ok) { throw 'self-test failed' }
Write-Host ('BUILT: ' + $exe) -ForegroundColor Green
