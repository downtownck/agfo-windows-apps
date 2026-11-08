# AGFO Subscription Manager - bu bilgisayarda derleme ve (istege bagli) kurulum. Yonetici gerekmez.
# EXE bu bilgisayarda uretildigi icin "internetten indirildi" isareti tasimaz (SmartScreen uyarisi yok).
# Kullanim:  Derle-ve-Kur.cmd   (ya da: powershell -File packaging\build_local.ps1 [-Install])
# ASCII-only: eski Windows PowerShell kodlama sorunlarindan kacinmak icin.
param([switch]$Install)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'python_runtime.ps1')

$appName = 'AGFO-Subscription-Manager'
$cache = Join-Path $env:LOCALAPPDATA 'AGFO\SubscriptionManager\build'
$venv = Join-Path $cache 'venv'
$dist = Join-Path $root 'dist'
$log = Join-Path $cache 'last-build.txt'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
Set-Content -LiteralPath $log -Value ('AGFO Subscription Manager yerel derleme ' + (Get-Date -Format s)) -Encoding UTF8

# Yerel komut calistirici: stderr'e yazilan UYARILAR betigi durdurmaz; basari yalnizca cikis koduyla belirlenir.
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
    if (-not $py) { throw 'Python 3.10+ (tkinter ile) bulunamadi. https://www.python.org/downloads/windows/ adresinden kurup tekrar deneyin.' }
    Write-Host ('Python: ' + $py.Python)

    # Ayri derleme ortami (kullanicinin Python kurulumunu kirletmez).
    $vpy = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $vpy)) {
        Write-Host 'Derleme ortami hazirlaniyor (yalnizca ilk seferde)...'
        if ((Invoke-Native $py.Python @('-m', 'venv', $venv)) -ne 0) { throw 'Derleme ortami (venv) olusturulamadi.' }
    }
    Write-Host 'Kutuphaneler kontrol ediliyor: PyInstaller, keyring, openpyxl ...'
    $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade',
                 'PyInstaller>=6.16,<7', 'keyring>=25,<27', 'openpyxl>=3.1,<4')
    if ((Invoke-Native $vpy $pipArgs) -ne 0) { throw 'Kutuphaneler kurulamadi. Internet baglantisini kontrol edin.' }

    Write-Host 'EXE derleniyor (1-2 dakika surebilir)...'
    $seed = Join-Path $root 'seed_subscriptions.json'
    $pyiArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', $appName,
                 '--distpath', $dist, '--workpath', (Join-Path $cache 'work'), '--specpath', (Join-Path $cache 'spec'),
                 '--paths', $root, '--add-data', ($seed + ';.'),
                 '--hidden-import', 'subscription_app', '--hidden-import', 'subscription_core',
                 '--hidden-import', 'subscription_update', '--hidden-import', 'agfo_github_update',
                 '--hidden-import', 'store', '--hidden-import', 'catalog', '--hidden-import', 'mailscan',
                 '--hidden-import', 'bankscan', '--hidden-import', 'keyring.backends.Windows',
                 '--collect-submodules', 'keyring',
                 (Join-Path $root 'app.pyw'))
    if ((Invoke-Native $vpy $pyiArgs) -ne 0) { throw 'PyInstaller derlemesi basarisiz.' }
    $exe = Join-Path $dist ($appName + '.exe')
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Derleme bitti fakat EXE bulunamadi.' }
    Write-Host ('EXE hazir: ' + $exe) -ForegroundColor Green

    if ($Install) {
        $dir = Join-Path $env:LOCALAPPDATA 'Programs\AGFO-Subscription-Manager'
        $target = Join-Path $dir ($appName + '.exe')
        # Calisan eski surum varsa kapat (dosya kilitli kalmasin).
        Get-Process -Name $appName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 800
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Copy-Item -LiteralPath $exe -Destination $target -Force
        Unblock-File -LiteralPath $target -ErrorAction SilentlyContinue
        $sh = New-Object -ComObject WScript.Shell
        $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO'
        New-Item -ItemType Directory -Force -Path $menu | Out-Null
        foreach ($lnkPath in @((Join-Path $menu 'AGFO Subscription Manager.lnk'), (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Subscription Manager.lnk'))) {
            $l = $sh.CreateShortcut($lnkPath)
            $l.TargetPath = $target
            $l.WorkingDirectory = $dir
            $l.IconLocation = $target + ',0'
            $l.Description = 'AGFO Subscription Manager'
            $l.Save()
        }
        Write-Host ('Kuruldu: ' + $target) -ForegroundColor Green
        Write-Host 'Kisayollar: Baslat menusu > AGFO ve Masaustu.'
        Start-Process -FilePath $target -WorkingDirectory $dir
    }
    exit 0
} catch {
    Write-Host ('HATA: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Ayrinti: ' + $log)
    exit 1
}
