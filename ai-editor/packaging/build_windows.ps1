# AGFO AI Editor - Windows build (GitHub Actions or a local PC with Python 3.12).
# Produces dist\AGFO-AI-Editor.exe (single file, no admin rights needed to run or install).
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $root
$python = (Get-Command python.exe -ErrorAction Stop).Source
Write-Host ('Python: ' + $python)
& $python -m pip install --disable-pip-version-check --quiet 'PyInstaller>=6.12,<7' 'Pillow>=11,<13' 'pypdf>=6,<7' 'pypdfium2>=4.30,<6' 'cryptography>=42,<47' 'fonttools>=4.50,<5' 'lxml>=5.2,<7'
if ($LASTEXITCODE) { throw 'pip install failed' }
function Write-Annotation([string]$title, [string]$text) {
    # GitHub annotations are readable through the REST API even when raw logs are not.
    $n = 0
    for ($k = 0; $k -lt $text.Length -and $n -lt 8; $k += 3500) {
        $n++
        $c = $text.Substring($k, [Math]::Min(3500, $text.Length - $k))
        $msg = $c.Replace('%', '%25').Replace("`r", '').Replace("`n", '%0A')
        Write-Host ('::error title=' + $title + ' ' + $n + '::' + $msg)
    }
}
$testLog = Join-Path $env:TEMP 'agfo-editor-tests.txt'
$env:PYTHONIOENCODING = 'utf-8'
$tp = Start-Process -FilePath $python -ArgumentList @('-m', 'unittest', 'discover', '-s', ('"' + (Join-Path $root 'tests') + '"'), '-v') `
    -RedirectStandardError $testLog -RedirectStandardOutput ($testLog + '.out') -NoNewWindow -PassThru -Wait
$testExit = $tp.ExitCode
Get-Content -LiteralPath $testLog -Encoding UTF8 | Write-Host
if ($testExit) {
    $all = Get-Content -LiteralPath $testLog -Raw -Encoding UTF8
    $k = $all.IndexOf('======')
    if ($k -lt 0) { $k = [Math]::Max(0, $all.Length - 6000) }
    Write-Annotation 'unit tests' $all.Substring($k)
    throw 'unit tests failed'
}
$work = Join-Path $env:RUNNER_TEMP 'agfo-editor-build'
if (-not $env:RUNNER_TEMP) { $work = Join-Path $env:TEMP 'agfo-editor-build' }
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name AGFO-AI-Editor `
    --distpath (Join-Path $root 'dist') --workpath (Join-Path $work 'work') --specpath (Join-Path $work 'spec') `
    --icon (Join-Path $root 'assets\agfo-ai-editor.ico') --paths (Join-Path $root 'src') `
    --add-data ((Join-Path $root 'assets\agfo-ai-editor.ico') + ';assets') `
    --add-data ((Join-Path $root 'src\brcgs_data') + ';brcgs_data') `
    --hidden-import agfo_brcgs --hidden-import agfo_brcgs.data --hidden-import agfo_brcgs.boxes --hidden-import agfo_brcgs.docx_engine --hidden-import agfo_brcgs.store --hidden-import agfo_brcgs.guide --hidden-import agfo_brcgs.coverage --hidden-import agfo_brcgs.xlsx_reader --hidden-import agfo_brcgs_view --hidden-import agfo_brcgs.findings --hidden-import agfo_brcgs.i18n --hidden-import agfo_docrender --hidden-import agfo_wordview --hidden-import lxml.etree `
    --hidden-import agfo_editor_core --hidden-import agfo_ai_client --hidden-import agfo_secrets `
    --hidden-import agfo_editor_update --hidden-import agfo_github_update --hidden-import agfo_sources --hidden-import agfo_pdf --hidden-import agfo_pdf_view --hidden-import agfo_pdf_edit `
    --hidden-import agfo_richdoc --hidden-import agfo_richtext --hidden-import agfo_doctranslate --hidden-import agfo_compare --hidden-import agfo_pdf_layout --hidden-import agfo_trlive --hidden-import agfo_speech --hidden-import agfo_readaloud --hidden-import agfo_localtts --hidden-import agfo_spell `
    --collect-submodules pypdf --collect-submodules cryptography --collect-submodules fontTools.subset --collect-submodules fontTools.ttLib --hidden-import pypdf._crypt_providers._cryptography --collect-all pypdfium2 --collect-all pypdfium2_raw --hidden-import PIL.ImageTk `
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
if (-not $r.ok) { Write-Annotation 'self-test' ($r | ConvertTo-Json -Compress -Depth 6); throw 'self-test failed' }
Write-Host ('BUILT: ' + $exe) -ForegroundColor Green
