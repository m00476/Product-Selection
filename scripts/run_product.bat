@echo off
REM ============================================================
REM  选品一条龙 - 供 Windows 计划任务调用
REM  用法：把 PRODUCT 改成你的品类 slug，类目名写在 .env 的
REM        ALIEXPRESS_CATEGORY_NAME(避免中文在 bat 里的编码问题)。
REM  退出码：0=成功，1=失败(计划任务可据此判断/告警)。
REM  日志：D:\518\output\logs\<PRODUCT>\run_<时间戳>.log
REM ============================================================
chcp 65001 >nul
cd /d D:\ProductSourcingSystem

set PRODUCT=garden_tools

python -m sourcing.cli run-product --source ixspy --product-type %PRODUCT% --headless
exit /b %ERRORLEVEL%
