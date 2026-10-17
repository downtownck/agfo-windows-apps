@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_exe.ps1"
echo.
echo Derleme sonucunu yukarida kontrol edin.
pause
endlocal
