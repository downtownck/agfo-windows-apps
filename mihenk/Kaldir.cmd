@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$d=Join-Path $env:LOCALAPPDATA 'Programs\AGFO-Mihenk'; $m=Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO\AGFO Mihenk.lnk'; $k=Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Mihenk.lnk'; $s=Join-Path ([Environment]::GetFolderPath('Startup')) 'AGFO Mihenk.lnk'; Get-Process -Name 'AGFO-Mihenk' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500; Remove-Item -LiteralPath $m,$k,$s -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue; Write-Host 'App removed. Your records (APPDATA\AGFO\Mihenk) were kept.'"
pause
