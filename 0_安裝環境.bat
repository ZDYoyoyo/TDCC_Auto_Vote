@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   TDCC 自動投票工具 - 第一次使用請先跑這個
echo ============================================
echo.

echo [1/2] 安裝 Python 套件...
python -m pip install -r requirements.txt
if errorlevel 1 goto err

echo.
echo [2/2] 下載瀏覽器（第一次會下載約 150MB，請耐心等）...
python -m playwright install chromium
if errorlevel 1 goto err

echo.
echo 安裝完成。接下來請跑「1_偵查頁面結構.bat」。
pause
exit /b 0

:err
echo.
echo 安裝失敗。請確認：
echo   1. 已安裝 Python 3.10 以上版本
echo   2. 安裝 Python 時有勾選「Add Python to PATH」
echo   3. 電腦可以連上網路
pause
exit /b 1
