@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 自动切换到项目根目录
cd /d "%~dp0.."

echo ========================================
echo   DeepAudit Pro - 演示模式启动
echo ========================================
echo.
echo 当前目录: %CD%
echo.

REM 1. 检查并创建虚拟环境
if not exist ".venv" (
    echo [1/8] 创建 Python 虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] 虚拟环境创建失败，请检查 Python 是否正确安装
        pause
        exit /b 1
    )
    echo    [OK] 虚拟环境创建成功
) else (
    echo [1/8] [OK] 虚拟环境已存在
)
echo.

REM 2. 激活虚拟环境
echo [2/8] 激活虚拟环境...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] 虚拟环境激活失败
    pause
    exit /b 1
)
echo    [OK] 虚拟环境已激活
echo.

REM 3. 安装依赖
echo [3/8] 安装项目依赖...
if exist "requirements.lock.txt" (
    echo    使用 requirements.lock.txt...
    pip install -r requirements.lock.txt -q
    if errorlevel 1 (
        echo [ERROR] 依赖安装失败
        pause
        exit /b 1
    )
) else if exist "requirements.txt" (
    echo    使用 requirements.txt...
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo [ERROR] 依赖安装失败
        pause
        exit /b 1
    )
) else (
    echo [ERROR] 未找到依赖文件 requirements.txt 或 requirements.lock.txt
    pause
    exit /b 1
)
echo    [OK] 依赖安装完成
echo.

REM 4. 设置环境变量
echo [4/8] 配置环境变量...
set DATABASE_URL=sqlite:///database_demo.db
set APP_MODE=demo
set FLASK_ENV=development
set FLASK_DEBUG=1
set FLASK_APP=app.py
set DEV_ALLOW_INSECURE=1
echo    [OK] DATABASE_URL=sqlite:///database_demo.db
echo    [OK] APP_MODE=demo
echo    [OK] FLASK_DEBUG=1
echo.

REM 5. 自动确认
echo ========================================
echo   INFO 演示模式启动
echo ========================================
echo.
echo 演示模式将执行以下操作：
echo   1. 删除并重建 database_demo.db
echo   2. 自动生成演示数据
echo   3. 不会影响 database.db
echo.
echo 目标数据库：database_demo.db
echo 数据隔离：完全独立，不影响生产数据
echo.
echo [自动确认] 3秒后自动继续...
timeout /t 3 /nobreak >nul
echo [OK] 已确认，继续启动
echo.

REM 6. 删除旧的演示数据库
echo [5/8] 准备演示数据库...
if exist "database_demo.db" (
    echo    删除旧的 database_demo.db...
    del /f /q database_demo.db
    if errorlevel 1 (
        echo [ERROR] 无法删除 database_demo.db，可能被其他进程占用
        echo    请关闭所有使用该数据库的程序后重试
        pause
        exit /b 1
    )
    echo    [OK] 旧数据库已删除
)
echo    [OK] 准备创建新的演示数据库
echo.

REM 7. 初始化数据库结构
echo [6/8] 初始化数据库结构...

if exist "migrations" (
    echo    使用 Flask-Migrate 初始化...
    flask db upgrade 2>nul
    if errorlevel 1 (
        echo    [WARNING] Flask-Migrate 初始化失败，尝试使用内置初始化...
        python -c "from core.app_factory import create_app; from utils.db import init_db; app = create_app(); app.app_context().push(); init_db(); print('[OK] 数据库初始化完成')"
        if errorlevel 1 (
            echo [ERROR] 数据库初始化失败
            pause
            exit /b 1
        )
    ) else (
        echo    [OK] 数据库结构初始化完成
    )
) else (
    echo    使用内置初始化方法...
    python -c "from core.app_factory import create_app; from utils.db import init_db; app = create_app(); app.app_context().push(); init_db(); print('[OK] 数据库初始化完成')"
    if errorlevel 1 (
        echo [ERROR] 数据库初始化失败
        pause
        exit /b 1
    )
)
echo.

REM 8. 创建管理员账号
echo [7/8] 创建管理员账号...
python scripts\create_admin_demo.py
if errorlevel 1 (
    echo [ERROR] 管理员账号创建失败
    pause
    exit /b 1
)
echo.

REM 9. 生成演示数据
echo [8/8] 生成演示数据...
python scripts\seed_demo.py
if errorlevel 1 (
    echo [ERROR] 演示数据生成失败
    pause
    exit /b 1
)
echo.

REM 10. 启动 Flask 应用并自动打开浏览器
echo ========================================
echo   LAUNCH 系统启动中...
echo ========================================
echo.
echo 访问地址：http://127.0.0.1:5000
echo 数据库：database_demo.db
echo 账号：admin01 / 123456
echo.
echo 按 Ctrl+C 停止服务器
echo ========================================
echo.

REM 延迟3秒后自动打开浏览器
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5000"

flask run --host=127.0.0.1 --port=5000

REM 如果 Flask 异常退出
if errorlevel 1 (
    echo.
    echo [ERROR] 服务器启动失败
    pause
    exit /b 1
)

pause
