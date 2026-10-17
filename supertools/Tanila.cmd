@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\diagnose.ps1"
echo.
echo Tanilama sonu. Pencere kapanmasin diye herhangi bir tusa basin.
pause >nul
endlocal
