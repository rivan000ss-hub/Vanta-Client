@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Installing build dependencies...
py -m pip install --upgrade pip
if errorlevel 1 goto :error
py -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/4] Locating Tcl/Tk libraries...
for /f "delims=" %%i in ('py -c "from pathlib import Path; import sys; p=Path(sys.base_prefix)/'tcl'; print(next(x.parent for x in p.glob('tcl*/init.tcl')))"') do set "VANTA_TCL_DIR=%%i"
for /f "delims=" %%i in ('py -c "from pathlib import Path; import sys; p=Path(sys.base_prefix)/'tcl'; print(next(x.parent for x in p.glob('tk*/tk.tcl')))"') do set "VANTA_TK_DIR=%%i"
if not defined VANTA_TCL_DIR (
  echo ERROR: Tcl init.tcl was not found. Reinstall Python with Tcl/Tk support.
  goto :error
)
if not defined VANTA_TK_DIR (
  echo ERROR: Tk tk.tcl was not found. Reinstall Python with Tcl/Tk support.
  goto :error
)

echo Tcl: %VANTA_TCL_DIR%
echo Tk:  %VANTA_TK_DIR%

echo [3/4] Checking Python syntax...
py -m py_compile vanta_launcher.py
if errorlevel 1 goto :error

echo [4/4] Building Windows EXE...
py -m PyInstaller --noconfirm --clean --onefile --windowed --name VANTA-Launcher --add-data "%VANTA_TCL_DIR%;_tcl_data" --add-data "%VANTA_TK_DIR%;_tk_data" vanta_launcher.py
if errorlevel 1 goto :error

echo.
echo Build complete: dist\VANTA-Launcher.exe
echo Running packaged GUI startup test...
dist\VANTA-Launcher.exe --self-test
if errorlevel 1 goto :error

echo VANTA GUI startup self-test passed.
pause
exit /b 0

:error
echo.
echo BUILD OR SELF-TEST FAILED.
pause
exit /b 1
