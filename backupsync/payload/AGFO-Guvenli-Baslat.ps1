#requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
$sourceFolder = $PSScriptRoot
$appRoot = Join-Path $env:LOCALAPPDATA 'AGFO-BackupSync'
$appFolder = Join-Path $appRoot 'app'
$logFolder = Join-Path $appRoot 'logs'
$required = @('AGFO-BackupSync-Core.ps1', 'AGFO-BackupSync-Worker.ps1',
    'AGFO-BackupSync-GUI.ps1', 'AGFO-BackupSync-Test.ps1', 'AGFO-Guvenli-Baslat.ps1')

function Assert-PowerShellSources([string]$Folder) {
    foreach ($name in $required) {
        $path = Join-Path $Folder $name
        if (-not [System.IO.File]::Exists($path)) { throw "Eksik uygulama dosyasi: $path" }
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
        if ($null -ne $errors -and $errors.Length -gt 0) {
            $messages = @($errors | Select-Object -First 10 | ForEach-Object {
                'Satir ' + $_.Extent.StartLineNumber + ': ' + $_.Message
            })
            throw ('PowerShell kaynak kodu hatasi (' + $name + '):' + [Environment]::NewLine + ($messages -join [Environment]::NewLine))
        }
    }
}

try {
    [void][System.IO.Directory]::CreateDirectory($logFolder)
    Assert-PowerShellSources $sourceFolder
    if ($ValidateOnly) {
        Write-Host 'PowerShell AYRISTIRMA: BASARILI' -ForegroundColor Green
        & (Join-Path $sourceFolder 'AGFO-BackupSync-Test.ps1')
        if (-not $?) { throw 'Dogrulama testleri basarisiz.' }
        Write-Host 'DOGRULAMA BASARILI' -ForegroundColor Green
        exit 0
    }
    if ($Install) {
        [void][System.IO.Directory]::CreateDirectory($appFolder)
        foreach ($name in $required) {
            $from = Join-Path $sourceFolder $name
            $to = Join-Path $appFolder $name
            if (-not [string]::Equals($from, $to, [System.StringComparison]::OrdinalIgnoreCase)) {
                [System.IO.File]::Copy($from, $to, $true)
            }
        }
        Assert-PowerShellSources $appFolder
        try {
            # A desktop shortcut allows starting the installed copy without keeping the ZIP.
            $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
            if ($desktop -and [System.IO.Directory]::Exists($desktop)) {
                $shell = New-Object -ComObject WScript.Shell
                $link = $shell.CreateShortcut((Join-Path $desktop 'AGFO BackupSync.lnk'))
                $link.TargetPath = Join-Path $PSHOME 'powershell.exe'
                $link.Arguments = '-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -STA -File ' + ('"' + (Join-Path $appFolder 'AGFO-Guvenli-Baslat.ps1') + '"')
                $link.WorkingDirectory = $appFolder
                $link.Description = 'AGFO BackupSync v2 - Windows NAS backup manager'
                $link.Save()
            }
        } catch { Write-Host ('Masaustu kisayolu olusturulamadi: ' + $_.Exception.Message) }
        Write-Host ('Kurulum tamamlandi: ' + $appFolder)
    } else {
        # v2.2 compiled application must start the SAME version from C:\agfo-backutil.
        # Do not accidentally launch an older v2.0 GUI from LocalAppData.
        if ([System.IO.File]::Exists((Join-Path $sourceFolder 'AGFO-BackupSync.exe'))) {
            $appFolder = $sourceFolder
            Assert-PowerShellSources $appFolder
        } elseif ([System.IO.File]::Exists((Join-Path $appFolder 'AGFO-BackupSync-GUI.ps1'))) {
            Assert-PowerShellSources $appFolder
        } else { $appFolder = $sourceFolder }
    }
    $guiPath = Join-Path $appFolder 'AGFO-BackupSync-GUI.ps1'
    & $guiPath
} catch {
    $description = 'AGFO BackupSync v2 baslatilamadi:' + [Environment]::NewLine + [string]$_.Exception.ToString()
    try { [System.IO.File]::WriteAllText((Join-Path $logFolder 'startup-last.txt'), $description, [System.Text.Encoding]::UTF8) } catch { }
    Write-Host $description -ForegroundColor Red
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [void][System.Windows.Forms.MessageBox]::Show($description, 'AGFO BackupSync - Hata',
            [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
    } catch { }
    exit 1
}
