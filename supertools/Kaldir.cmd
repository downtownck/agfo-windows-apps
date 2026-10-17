@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\uninstall_windows.ps1"
echo.
pause
endlocal
