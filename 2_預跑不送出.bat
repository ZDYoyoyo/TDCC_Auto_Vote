@echo off
REM  ASCII ONLY - see the "0_" file for why. Chinese text comes from Python.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

echo ==========================================
echo   DRY RUN - nothing will be submitted
echo ==========================================
echo.

python -m tdcc_vote.run_all %*
if errorlevel 1 (
  echo.
  echo [NOTE] Finished with failures, or setup missing.
  echo   If this is your first time, run the "0_" file first.
)
pause
