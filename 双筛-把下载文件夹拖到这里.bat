@echo off
chcp 65001 >nul
REM ============================================================
REM  选品双筛 · 拖拽即跑
REM  用法：把 IXSPY 下载的「品类文件夹」直接拖到本图标上松手。
REM  会自动：整理文件 → 解析 → ERP图搜 → 模型精筛 → 出老板版报告，
REM  跑完自动打开报告文件夹。约 45-60 分钟(1000 商品)。
REM ============================================================
cd /d D:\ProductSourcingSystem
set EMBEDDING_REPO_DIR=D:\518

if "%~1"=="" (
  echo.
  echo   请把下载好的「品类文件夹」拖到本图标上运行。
  echo   例如把  D:\IXSPY下载数据\男女内衣及家居服  拖过来。
  echo.
  pause
  exit /b 1
)

echo.
echo   正在处理: %~1
echo   （请勿关闭本窗口，跑完会自动打开报告文件夹）
echo.

python -X utf8 -m sourcing.cli platform-export-run --src "%~1"
set CODE=%ERRORLEVEL%

echo.
if "%CODE%"=="0" (
  echo   ===== 完成 =====
) else (
  echo   ===== 出错了(退出码 %CODE%)，请把上面的提示发给技术确认 =====
)
echo   按任意键关闭窗口。
pause >nul
