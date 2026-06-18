@echo off
chcp 65001 >nul
cd /d D:\ProductSourcingSystem
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\ixspy_auto_prompt.ps1"
