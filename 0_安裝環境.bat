@echo off
REM ---------------------------------------------------------------
REM  ASCII ONLY in this file - comments included.
REM  cmd parses .bat using the system codepage, so even after
REM  "chcp 65001" a non-ASCII byte can be read as a command separator
REM  and break the line. (This actually happened.)
REM  Put all Chinese text in the Python program, never in echo/REM.
REM ---------------------------------------------------------------
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

echo ==========================================
echo   TDCC Auto Vote  -  Setup (run once)
echo ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto no_python

python -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)"
if errorlevel 1 goto old_python

python --version
echo.
echo [1/2] Installing Python packages ...
REM --prefer-binary: use a slightly older release if the newest one
REM has no prebuilt wheel, instead of compiling from source (needs MSVC).
python -m pip install --prefer-binary -r requirements.txt
if errorlevel 1 goto failed

echo.
echo [2/2] Downloading browser (about 150MB, please wait) ...
python -m playwright install chromium
if errorlevel 1 goto failed

echo.
echo ==========================================
echo   Setup OK.
echo   Next: double-click the file starting with "1_"
echo ==========================================
pause
exit /b 0

:no_python
echo.
echo [ERROR] Python was not found.
echo.
echo   1. Install Python from  https://www.python.org/downloads/
echo   2. During install, TICK  "Add python.exe to PATH"
echo   3. Close this window and run this file again
pause
exit /b 1

:old_python
echo.
echo [ERROR] Your Python is too old. This tool needs 3.9 or newer.
python --version
echo   Download a newer one:  https://www.python.org/downloads/
pause
exit /b 1

:failed
echo.
echo [ERROR] Setup failed. Copy the messages above and send them to Claude.
echo   Common causes:
echo     - no internet connection
echo     - Python installed from Microsoft Store (try the python.org one)
pause
exit /b 1
