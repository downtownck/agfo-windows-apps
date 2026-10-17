@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0packaging\install_windows.ps1"
if errorlevel 1 (
 echo Kurulum basarisiz. Python 3 ve tkinter kurulumunu kontrol edin.
 pause
)
