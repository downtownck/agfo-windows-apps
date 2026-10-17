@echo off
rem AGFO AI Editor - verify against GitHub and unblock (see Trust-AgfoAiEditor.ps1)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Trust-AgfoAiEditor.ps1" %*
echo.
pause
