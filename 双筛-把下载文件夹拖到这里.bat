@echo off
chcp 65001 >nul
setlocal
cd /d D:\ProductSourcingSystem
set "EMBEDDING_REPO_DIR=D:\518"

if "%~1"=="" goto :noarg

echo.
echo Processing folder: %~1
echo Please DO NOT close this window. The report folder opens automatically when done.
echo (about 45-60 min for 1000 products)
echo.

python -X utf8 -m sourcing.cli platform-export-run --src "%~1"
set "CODE=%ERRORLEVEL%"

echo.
if "%CODE%"=="0" goto :ok
echo ===== ERROR (exit code %CODE%). Please screenshot the messages above. =====
goto :end
:ok
echo ===== DONE =====
:end
echo Press any key to close this window.
pause >nul
goto :eof

:noarg
echo.
echo  Please DRAG your downloaded category folder onto this icon.
echo  Example: D:\IXSPY downloaded data\(category folder)
echo.
echo Press any key to close.
pause >nul
