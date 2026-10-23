@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo AGFO Phantom Shot - bu bilgisayarda derleniyor ve kuruluyor...
echo (Ilk seferde gerekli kutuphaneler indirilir; birkac dakika surebilir.)
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_local.ps1" -Install
if errorlevel 1 (
  echo.
  echo Derleme veya kurulum hatasi. Ayrinti: %LOCALAPPDATA%\AGFO\PhantomShot\build\last-build.txt
  pause
  exit /b 1
)
echo.
echo Tamam. Uygulama acildi; Baslat menusu ve masaustunde "AGFO Phantom Shot" kisayolu var.
pause
