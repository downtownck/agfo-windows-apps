$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir 'python_runtime.ps1')
$python = Find-AGFOPython
if (-not $python) { Write-Host 'Python 3.10+ gerekli. Once Kur-ve-Baslat.cmd calistirin.'; exit 1 }
$localBuildRoot = Join-Path $env:LOCALAPPDATA 'AGFO-MultiSubnet-Scanner\build'
$distRoot = Join-Path $projectRoot 'dist'
$workRoot = Join-Path $localBuildRoot 'work'
$specRoot = Join-Path $localBuildRoot 'spec'
New-Item -Path $distRoot -ItemType Directory -Force | Out-Null
New-Item -Path $workRoot -ItemType Directory -Force | Out-Null
New-Item -Path $specRoot -ItemType Directory -Force | Out-Null
$log = Join-Path $localBuildRoot 'build.log'
try {
    Start-Transcript -Path $log -Force -ErrorAction SilentlyContinue | Out-Null
    Write-Host ('AGFO EXE derleme. Python: ' + $python.Python)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $python.Python -m pip --version
        $pipExit = $LASTEXITCODE
        if ($pipExit -ne 0) {
            & $python.Python -m ensurepip --upgrade
            if ($LASTEXITCODE -ne 0) { throw 'Pip kullanilamiyor.' }
        }
        & $python.Python -m pip install --user --upgrade pyinstaller
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller yuklenemedi.' }
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    # Password SSH backend must be bundled inside the standalone EXE.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $python.Python -c 'import paramiko'
        $hasParamiko = $LASTEXITCODE
        if ($hasParamiko -ne 0) {
            Write-Host 'Dahili SSH icin Paramiko yukleniyor (yalnizca bu Windows kullanicisina)...'
            & $python.Python -m pip install --user --disable-pip-version-check paramiko
            if ($LASTEXITCODE -ne 0) { throw 'Paramiko yuklenemedi; EXE derlemesi durduruldu.' }
        }
    } finally {
        $ErrorActionPreference = $previous
    }
    $iconPath = Join-Path $projectRoot 'assets\agfo-scanner.ico'
    $pngPath = Join-Path $projectRoot 'assets\agfo-scanner.png'
    $app = Join-Path $projectRoot 'app.pyw'
    $args = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
              '--name', 'AGFO-MultiSubnet-Scanner', '--icon', $iconPath,
              '--collect-all', 'paramiko',
              '--add-data', ($iconPath + ';assets'),
              '--add-data', ($pngPath + ';assets'),
              '--paths', $projectRoot, '--workpath', $workRoot, '--specpath', $specRoot,
              '--distpath', $distRoot, $app)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $python.Python @args
        $buildExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    if ($buildExit -ne 0) { throw ('PyInstaller basarisiz. Kod: ' + $buildExit) }
    $exe = Join-Path $distRoot 'AGFO-MultiSubnet-Scanner.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Derleme bitti fakat EXE bulunamadi.' }
    Write-Host ('EXE olusturuldu: ' + $exe)
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    exit 0
} catch {
    Write-Host ('DERLEME HATASI: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Log: ' + $log)
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    exit 1
}
