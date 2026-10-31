@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install --upgrade pyinstaller pypdf
if errorlevel 1 goto :fail
py -3 -m PyInstaller --onefile --windowed --clean --noconfirm --name AGFO-Smart-Organizer --collect-all pypdf smart_organizer.pyw
if errorlevel 1 goto :fail
echo EXE hazir: dist\AGFO-Smart-Organizer.exe
pause
exit /b 0
:fail
echo EXE olusturma basarisiz. Python 3 kurulumunu kontrol edin.
pause
exit /b 1
