@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ================================================================================
echo   DeepAudit Pro - 启动脚本（带数据库路径显示）
echo ================================================================================
echo.

cd /d "%~dp0.."

REM 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 虚拟环境不存在，请先运行 python -m venv .venv
    pause
    exit /b 1
)

REM 激活虚拟环境
call .venv\Scripts\activate.bat

echo [1/3] 虚拟环境已激活
echo.

REM 设置环境变量（如果需要）
REM set DATABASE_URL=sqlite:///database.db
REM set FLASK_DEBUG=1

echo [2/3] 运行数据库路径诊断...
echo.
python scripts\diagnose_db_path.py
echo.

echo [3/3] 启动 Flask 应用...
echo.
echo ================================================================================
echo   应用启动中，请查看上方的数据库路径信息
echo   按 Ctrl+C 停止应用
echo ================================================================================
echo.

python app.py

pause

