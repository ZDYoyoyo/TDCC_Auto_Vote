@echo off
REM  ASCII ONLY - see the "0_" file for why. Chinese text comes from Python.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

echo ==========================================
echo   RECEIPTS ONLY - no voting
echo   Takes a screenshot of the query page for
echo   every stock that is already voted.
echo ==========================================
echo.

python -m tdcc_vote.run_all --receipts-only %*
if errorlevel 1 (
  echo.
  echo [NOTE] Some screenshots failed. Read the summary above.
)
pause
