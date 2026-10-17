$ErrorActionPreference = 'Stop'
$target = 'C:\agfo-backutil\MultiSubnetScanner'
$linkPath = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\AGFO\AGFO Multi-Subnet Scanner.lnk'
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $scriptPath = $MyInvocation.MyCommand.Path
    try {
        $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '"') -Verb RunAs -Wait -PassThru
        exit $p.ExitCode
    } catch { Write-Host ('Yonetici izni verilmedi: ' + $_.Exception.Message); exit 1 }
}
try {
    if (Test-Path -LiteralPath $linkPath) { Remove-Item -LiteralPath $linkPath -Force }
    $newLinkPath = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\AGFO\AGFO SuperTools.lnk'
    if (Test-Path -LiteralPath $newLinkPath) { Remove-Item -LiteralPath $newLinkPath -Force }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    Write-Host 'AGFO Multi-Subnet Scanner kaldirildi.'
    Write-Host 'Diger AGFO BackupSync klasorlerine dokunulmadi.'
    Write-Host 'Kullanici tarama ayarlari LOCALAPPDATA altinda korundu.'
    exit 0
} catch {
    Write-Host ('KALDIRMA HATASI: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
