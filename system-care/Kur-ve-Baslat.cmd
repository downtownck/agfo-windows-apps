@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0packaging\install_windows.ps1"
if errorlevel 1 (
 echo Kurulum basarisiz. Windows paketini (AGFO-System-Care-...-Windows.zip) kullanin ya da Python 3 kurun.
 pause
)
