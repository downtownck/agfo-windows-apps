@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\install_windows.ps1"
if errorlevel 1 (
 echo.
 echo Kurulum basarisiz. Ayrintilar: %%TEMP%%\AGFO-MultiSubnet-install.log
 pause
)
endlocal
