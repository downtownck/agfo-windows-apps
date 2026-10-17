@echo off
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0AGFO-Guvenli-Baslat.ps1" -ValidateOnly
if errorlevel 1 echo HATA: %%LOCALAPPDATA%%\AGFO-BackupSync\logs\startup-last.txt
pause
