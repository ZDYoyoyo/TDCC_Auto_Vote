@echo off
REM  ASCII ONLY - see the "0_" file for why. Chinese text comes from Python.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

python -m tdcc_vote.explore %*
if errorlevel 1 (
  echo.
  echo [ERROR] Failed to run.
  echo   If this is your first time, run the file starting with "0_" first.
)
pause
