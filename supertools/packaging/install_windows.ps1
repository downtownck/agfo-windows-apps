param([switch]$NoStart)
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$dest = 'C:\agfo-backutil\MultiSubnetScanner'
$log = Join-Path $env:TEMP 'AGFO-MultiSubnet-install.log'

function Test-IsAdministrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    Write-Host 'Uygulama C:\agfo-backutil altina kurulmak icin yonetici izni istiyor.'
    $argsList = '-NoProfile -ExecutionPolicy Bypass -File "' + $MyInvocation.MyCommand.Path + '"'
    if ($NoStart) { $argsList += ' -NoStart' }
    try {
        $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $argsList
        exit $proc.ExitCode
    } catch {
        Write-Host ('Yonetici onayi alinmadi: ' + $_.Exception.Message)
        exit 1
    }
}

try {
    Start-Transcript -Path $log -Force -ErrorAction SilentlyContinue | Out-Null
    Write-Host 'AGFO Multi-Subnet Scanner v1.6.0 - Kurulum'
    . (Join-Path $scriptDir 'python_runtime.ps1')
    $python = Find-AGFOPython
    if (-not $python) {
        Write-Host 'Calisan Python 3.10+ ve tkinter bulunamadi. Winget ile Python 3.13 kurulumu deneniyor.'
        $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
        if (-not $winget) { throw 'Python yok ve winget bulunamadi. https://www.python.org/downloads/windows/ adresinden Python kurun.' }
        # Some native tools write progress to stderr. Preserve exit-code semantics.
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $winget.Source install --exact --id Python.Python.3.13 --source winget --scope machine --silent --accept-package-agreements --accept-source-agreements
            $nativeExit = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $oldPreference
        }
        if ($nativeExit -ne 0) { throw ('Winget kurulumu basarisiz; kod: ' + $nativeExit) }
        $python = Find-AGFOPython
    }
    if (-not $python) { throw 'Python kurulu gorunuyor ama tkinter ile baslatilamiyor.' }
    Write-Host ('Python: ' + $python.Python)
    $files = @('app.pyw', 'scanner_core.py', 'agfo_updater.py', 'agfo_github_update.py', 'supertools_core.py', 'ssh_profiles.py', 'supertools_ui.py', 'modern_shell.py', 'ssh_password_vault.py', 'ssh_password_transport.py', 'ssh_workspace.py', 'assets\agfo-scanner.ico', 'assets\agfo-scanner.png')
    foreach ($entry in $files) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $entry) -PathType Leaf)) {
            throw ('Paket dosyasi eksik: ' + $entry)
        }
    }
    # Upgrade safety: back up existing installed code before overwriting it.
    if (Test-Path -LiteralPath (Join-Path $dest 'scanner_core.py') -PathType Leaf) {
        Write-Host 'Eski surumun geri donus kopyasi olusturuluyor...'
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $python.Python -B (Join-Path $projectRoot 'agfo_updater.py') --backup-existing
            $backupExit = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previous
        }
        if ($backupExit -ne 0) { throw 'Mevcut surum yedeklenemedi; kurulum guvenlik icin durduruldu.' }
    }
    New-Item -Path $dest -ItemType Directory -Force | Out-Null
    New-Item -Path (Join-Path $dest 'assets') -ItemType Directory -Force | Out-Null
    foreach ($entry in $files) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $entry) -Destination (Join-Path $dest $entry) -Force
    }
    $app = Join-Path $dest 'app.pyw'
    # Store a simple launcher for support and for portable user actions.
    $launcher = '@echo off' + "`r`n" + 'chcp 65001 >nul' + "`r`n" + 'start "" "' + $python.PythonW + '" "' + $app + '"' + "`r`n"
    [System.IO.File]::WriteAllText((Join-Path $dest 'Baslat.cmd'), $launcher, ([System.Text.UTF8Encoding]::new($false)))
    $menuDir = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\AGFO'
    New-Item -Path $menuDir -ItemType Directory -Force | Out-Null
    $linkPath = Join-Path $menuDir 'AGFO Multi-Subnet Scanner.lnk'
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($linkPath)
    $shortcut.TargetPath = $python.PythonW
    $shortcut.Arguments = '"' + $app + '"'
    $shortcut.WorkingDirectory = $dest
    $shortcut.IconLocation = (Join-Path $dest 'assets\agfo-scanner.ico') + ',0'
    $shortcut.Description = 'AGFO SuperTools: network, DNS, mail and SSH profiles'
    $shortcut.Save()
    # New product shortcut; retain the historical Multi-Subnet Scanner shortcut
    # so existing shortcuts and automation keep functioning after the upgrade.
    $superLink = Join-Path $menuDir 'AGFO SuperTools.lnk'
    $super = (New-Object -ComObject WScript.Shell).CreateShortcut($superLink)
    $super.TargetPath = $python.PythonW
    $super.Arguments = '"' + $app + '"'
    $super.WorkingDirectory = $dest
    $super.IconLocation = (Join-Path $dest 'assets\agfo-scanner.ico') + ',0'
    $super.Description = 'AGFO SuperTools: DNS, mail, ag kesfi ve SSH'
    $super.Save()
    Write-Host ('Kurulum tamam: ' + $dest)
    Write-Host ('Baslat menusu: ' + $linkPath)
    if (-not $NoStart) {
        Start-Process -FilePath $python.PythonW -ArgumentList ('"' + $app + '"') -WorkingDirectory $dest
    }
    Write-Host ('Kurulum logu: ' + $log)
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    exit 0
} catch {
    Write-Host ('KURULUM HATASI: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Log: ' + $log)
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    exit 1
}
