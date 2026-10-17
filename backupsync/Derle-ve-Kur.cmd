@echo off
setlocal
cd /d "%~dp0"
echo AGFO BackupSync v2.3.3 - Windows kurulum dosyasi derleniyor...
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_windows.ps1" -Install
if errorlevel 1 (
  echo.
  echo Derleme veya kurulum baslatma hatasi. .build-logs\last-build.txt kaydina bakin.
  pause
  exit /b 1
)
echo.
echo Kurucu tamamlandi. Tekrar kurmak icin dist\AGFO-BackupSync-Setup.exe dosyasini kullanabilirsiniz.
pause
