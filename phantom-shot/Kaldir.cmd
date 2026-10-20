@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$d=Join-Path $env:LOCALAPPDATA 'Programs\AGFO-Phantom-Shot'; $m=Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO\AGFO Phantom Shot.lnk'; $k=Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Phantom Shot.lnk'; Get-Process -Name 'AGFO-Phantom-Shot' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500; Remove-Item -LiteralPath $m,$k -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue; Write-Host 'Uygulama kaldirildi. Ayarlar ve gunlukler (LOCALAPPDATA\AGFO\PhantomShot) korundu.'"
pause
