@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$d=Join-Path $env:LOCALAPPDATA 'Programs\AGFO-Mic-Monitor'; $m=Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO\AGFO Mic Monitor.lnk'; $k=Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Mic Monitor.lnk'; Get-Process -Name 'AGFO-Mic-Monitor' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500; Remove-Item -LiteralPath $m,$k -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue; Write-Host 'Uygulama kaldirildi. Ayarlar ve gunlukler (LOCALAPPDATA\AGFO\MicMonitor) korundu.'"
pause
