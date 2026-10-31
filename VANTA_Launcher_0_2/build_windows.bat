@echo off
setlocal
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean --onefile --windowed --name VANTA-Launcher vanta_launcher.py
echo.
echo Build complete: dist\VANTA-Launcher.exe
pause
