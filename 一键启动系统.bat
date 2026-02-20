@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title DeepAudit Pro - 一键启动系统
color 0A

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║              DeepAudit Pro - 一键启动系统                  ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

echo [1/6] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [✗] 未找到 Python，请先安装 Python 3.8+
    echo [!] 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [✓] Python 环境正常 - %PYTHON_VERSION%
echo.

echo [2/6] 检查虚拟环境...
if not exist ".venv" (
    echo [!] 虚拟环境不存在，正在创建...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [✗] 虚拟环境创建失败
        echo [!] 请确保 Python 已正确安装并包含 venv 模块
        pause
        exit /b 1
    )
    echo [✓] 虚拟环境创建成功
) else (
    echo [✓] 虚拟环境已存在
)
echo.

echo [3/6] 激活虚拟环境...
if not exist ".venv\Scripts\activate.bat" (
    echo [✗] 虚拟环境激活脚本不存在
    echo [!] 虚拟环境可能损坏，正在重新创建...
    rmdir /s /q .venv
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [✗] 虚拟环境重建失败
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [✗] 虚拟环境激活失败
    pause
    exit /b 1
)
echo [✓] 虚拟环境已激活
echo.

echo [4/6] 检查并安装依赖...
if not exist "requirements.txt" (
    echo [✗] 未找到 requirements.txt 文件
    pause
    exit /b 1
)

echo [!] 正在升级 pip...
python -m pip install --upgrade pip >nul 2>&1

echo [!] 正在安装依赖包，请稍候...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [✗] 依赖安装失败，请检查网络连接或尝试使用国内镜像源
    echo [!] 使用镜像源命令：pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)
echo [✓] 依赖安装完成
echo.

echo [5/6] 检查数据库...
if exist "database.db" (
    echo [✓] 找到数据库: database.db
) else if exist "instance\database.db" (
    echo [✓] 找到数据库: instance\database.db
) else (
    echo [!] 未找到数据库文件，将在首次运行时自动创建
)
echo.

echo [6/6] 启动 DeepAudit Pro 系统...
echo.
echo ════════════════════════════════════════════════════════════
echo   系统启动中...
echo ════════════════════════════════════════════════════════════
echo.
echo 📌 访问地址：http://127.0.0.1:5000
echo 📌 数据库：database.db
echo 📌 按 Ctrl+C 停止服务器
echo.
echo ════════════════════════════════════════════════════════════
echo.

REM 延迟3秒后自动打开浏览器
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5000"

REM 启动Flask应用
python app.py

REM 如果异常退出
if %errorlevel% neq 0 (
    echo.
    echo [✗] 系统启动失败，请查看上方错误信息
    pause
    exit /b 1
)

pause
