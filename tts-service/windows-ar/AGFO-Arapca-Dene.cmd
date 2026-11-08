@echo off
chcp 65001 >nul
if not exist "%~dp0AGFO-Arapca-Dene.ps1" (
  echo HATA: AGFO-Arapca-Dene.ps1 bu klasorde yok. ZIP dosyasinin tamamini ayni klasore cikarin.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AGFO-Arapca-Dene.ps1" %*
echo.
pause
