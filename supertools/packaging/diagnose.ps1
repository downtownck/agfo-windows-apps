$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir 'python_runtime.ps1')
$python = Find-AGFOPython
if (-not $python) { Write-Host 'Python/tkinter bulunamadi. Kur-ve-Baslat.cmd ile kurmayi deneyin.'; exit 2 }
Write-Host ('AGFO Scanner tanilama, Python: ' + $python.Python)
& $python.Python -B (Join-Path $root 'app.pyw')
if ($LASTEXITCODE -ne 0) { Write-Host ('GUI kapandi, Python cikis kodu: ' + $LASTEXITCODE); exit $LASTEXITCODE }
