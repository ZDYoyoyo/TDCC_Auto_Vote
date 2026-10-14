@echo off
REM  ASCII ONLY - see the "0_" file for why. Chinese text comes from Python.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

echo ==========================================
echo   REAL VOTING  (--confirm)
echo   The program presses the confirm button itself.
echo   If the site blocks it, it asks YOU to press it.
echo   Add --manual-submit to always press it yourself.
echo ==========================================
echo.

python -m tdcc_vote.run_all --confirm %*
if errorlevel 1 (
  echo.
  echo [NOTE] Finished with failures. Read the summary above and
  echo   check those stocks manually on the TDCC website.
)
pause
