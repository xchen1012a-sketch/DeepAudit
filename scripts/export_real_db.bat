@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 自动切换到项目根目录
cd /d "%~dp0.."

echo.
echo ========================================
echo   DeepAudit Pro - 导出真实数据库
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 未安装或不在 PATH 中
    echo.
    pause
    exit /b 1
)

REM 检查虚拟环境
if exist ".venv\Scripts\python.exe" (
    echo [使用虚拟环境中的 Python]
    .venv\Scripts\python.exe scripts\export_real_db.py
) else (
    echo [使用系统 Python]
    python scripts\export_real_db.py
)

exit /b %errorlevel%

