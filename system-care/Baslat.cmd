@echo off
chcp 65001 >nul
if exist "%~dp0AGFO System Care.exe" ( start "" "%~dp0AGFO System Care.exe" & exit /b )
where py >nul 2>nul
if not errorlevel 1 ( start "" pyw -3 "%~dp0app.pyw" & exit /b )
start "" pythonw "%~dp0app.pyw"
