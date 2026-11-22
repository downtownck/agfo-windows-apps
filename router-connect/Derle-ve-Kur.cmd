@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo AGFO Router Connect - building and installing on this computer...
echo (The first run downloads the build tools; it can take a few minutes.)
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_local.ps1" -Install
if errorlevel 1 (
  echo.
  echo Build or install failed. Details: %LOCALAPPDATA%\AGFO\RouterConnect\build\last-build.txt
  pause
  exit /b 1
)
echo.
echo Done. The app is open; shortcuts: Start menu ^> AGFO and Desktop "AGFO Router Connect".
echo Your router list is kept in %APPDATA%\AGFO\RouterConnect
if /i "%~1"=="/update" (
  timeout /t 5 >nul
  exit /b 0
)
pause
