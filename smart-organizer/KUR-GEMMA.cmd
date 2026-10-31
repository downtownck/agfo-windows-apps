@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0AGFO-Ollama-Gemma-Kur.ps1" %*
set "rc=%ERRORLEVEL%"
echo.
pause
exit /b %rc%
