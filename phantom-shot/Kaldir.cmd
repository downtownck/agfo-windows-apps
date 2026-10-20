@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$d=Join-Path $env:LOCALAPPDATA 'Programs\AGFO Phantom Shot'; $s=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AGFO\AGFO Phantom Shot.lnk'; Remove-Item -LiteralPath $s -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue; Write-Host 'Uygulama kaldirildi. Ayarlar ve gunlukler (LOCALAPPDATA\AGFO\PhantomShot) korundu.'"
pause
