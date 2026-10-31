@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0smart_organizer.pyw"
  exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0smart_organizer.pyw"
  exit /b 0
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0smart_organizer.pyw"
  exit /b %errorlevel%
)
echo Python 3.10 veya yenisi gerekli.
echo https://www.python.org/downloads/windows/
pause
exit /b 1
