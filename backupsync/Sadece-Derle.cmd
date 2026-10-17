@echo off
setlocal
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_windows.ps1"
if errorlevel 1 (
  echo.
  echo HATA - .build-logs\last-build.txt dosyasina bakin.
  pause
  exit /b 1
)
echo.
echo Hazir: dist\AGFO-BackupSync-Setup.exe
pause
