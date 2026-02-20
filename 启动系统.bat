@echo off
chcp 65001 >nul
title DeepAudit Pro - 智能审计系统

echo ========================================
echo    DeepAudit Pro 智能审计系统
echo ========================================
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.8或更高版本
    echo.
    pause
    exit /b 1
)

echo [1/4] 检查Python环境...
python --version
echo.

:: 检查依赖包
echo [2/4] 检查依赖包...
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [警告] 缺少依赖包，正在安装...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖包安装失败
        pause
        exit /b 1
    )
) else (
    echo 依赖包检查通过
)
echo.

:: 检查数据库
echo [3/4] 检查数据库...
if not exist "database.db" (
    echo [警告] 数据库不存在，正在初始化...
    python scripts\init_db_keep_admin01.py
    if errorlevel 1 (
        echo [错误] 数据库初始化失败
        pause
        exit /b 1
    )
) else (
    echo 数据库检查通过
)
echo.

:: 检查必要的文件夹
if not exist "uploads" mkdir uploads
if not exist "instance" mkdir instance

:: 设置环境变量
set DEV_ALLOW_INSECURE=1
set FLASK_HOST=127.0.0.1
set FLASK_PORT=5000
set FLASK_DEBUG=0

echo [4/4] 启动系统...
echo.
echo ========================================
echo  系统启动成功！
echo  访问地址: http://127.0.0.1:5000
echo  
echo  默认管理员账号:
echo    用户名: admin01
echo    密码: admin123
echo  
echo  按 Ctrl+C 停止系统
echo ========================================
echo.

:: 启动Flask应用
python app.py

:: 如果启动失败
if errorlevel 1 (
    echo.
    echo [错误] 系统启动失败，请检查错误信息
    echo.
    pause
)

