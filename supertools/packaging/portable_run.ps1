$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir 'python_runtime.ps1')
$python = Find-AGFOPython
if (-not $python) {
    Write-Host 'Python 3.10+ bulunamadi. Kur-ve-Baslat.cmd ile uygulamayi kurabilirsiniz.'
    exit 2
}
$app = Join-Path $projectRoot 'app.pyw'
if (-not (Test-Path -LiteralPath $app)) { Write-Host 'app.pyw eksik'; exit 3 }
Start-Process -FilePath $python.PythonW -ArgumentList ('"' + $app + '"') -WorkingDirectory $projectRoot
exit 0
