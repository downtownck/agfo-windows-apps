@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$d=Join-Path $env:LOCALAPPDATA 'Programs\AGFO-Subscription-Manager'; $m=Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO\AGFO Subscription Manager.lnk'; $k=Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Subscription Manager.lnk'; Get-Process -Name 'AGFO-Subscription-Manager' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500; Remove-Item -LiteralPath $m,$k -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue; Write-Host 'App removed. Your subscription list (APPDATA\AGFO\SubscriptionManager) was kept.'"
pause
