@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem Guncelleme yolunda onay yeniden sorulmaz: ilk kurulumda zaten alinmisti.
if /i "%~1"=="/update" goto build

if not exist "%~dp0DISCLAIMER.txt" goto build
cls
type "%~dp0DISCLAIMER.txt"
echo.
echo ==============================================================================
echo.
set "AGREE="
set /p "AGREE=Kabul ediyor musunuz? / Do you accept?  [E/Y = evet/yes, H/N = hayir/no]: "
if /i "%AGREE%"=="E" goto build
if /i "%AGREE%"=="Y" goto build
echo.
echo Kurulum iptal edildi. / Installation cancelled.
echo.
pause
exit /b 2

:build
echo AGFO Mihenk - building and installing on this computer...
echo (The first run downloads the build tools; it can take a few minutes.)
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_local.ps1" -Install
if errorlevel 1 (
  echo.
  echo Build or install failed. Details: %LOCALAPPDATA%\AGFO\Mihenk\build\last-build.txt
  pause
  exit /b 1
)
echo.
echo Done. The app is open; shortcuts: Start menu ^> AGFO and Desktop "AGFO Mihenk".
echo Your records are kept in %APPDATA%\AGFO\Mihenk
echo Sorumluluk reddi / Disclaimer: %~dp0DISCLAIMER.txt
if /i "%~1"=="/update" (
  timeout /t 5 >nul
  exit /b 0
)
pause
