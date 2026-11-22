@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_local.ps1"
if errorlevel 1 (
  echo.
  echo Build failed - see %LOCALAPPDATA%\AGFO\RouterConnect\build\last-build.txt
  pause
  exit /b 1
)
echo.
echo Ready: dist\AGFO-Router-Connect.exe
pause
