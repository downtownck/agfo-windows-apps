@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_local.ps1"
if errorlevel 1 (
  echo.
  echo HATA - %LOCALAPPDATA%\AGFO\PhantomShot\build\last-build.txt dosyasina bakin.
  pause
  exit /b 1
)
echo.
echo Hazir: dist\AGFO-Phantom-Shot.exe
pause
