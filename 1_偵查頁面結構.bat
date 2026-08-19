@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

echo ============================================
echo   偵查集保網站的頁面結構
echo ============================================
echo.
echo   會跳出一個瀏覽器視窗，請你自己登入。
echo   登入後在瀏覽器點到要分析的頁面，
echo   再回到這個黑色視窗按 Enter 抓取。
echo.

python -m tdcc_vote.explore %*
if errorlevel 1 (
  echo.
  echo 執行失敗。若是第一次使用，請先跑「0_安裝環境.bat」。
)
pause
