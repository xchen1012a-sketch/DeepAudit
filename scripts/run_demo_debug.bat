@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 创建日志文件
set LOG_FILE=run_demo_debug.log
echo ======================================== > %LOG_FILE%
echo DeepAudit Pro - 演示模式启动调试日志 >> %LOG_FILE%
echo 启动时间: %date% %time% >> %LOG_FILE%
echo ======================================== >> %LOG_FILE%
echo. >> %LOG_FILE%

REM 自动切换到项目根目录
cd /d "%~dp0.."
echo 当前目录: %CD% >> %LOG_FILE%

echo ========================================
echo   DeepAudit Pro - 演示模式启动 (调试版)
echo ========================================
echo.
echo 当前目录: %CD%
echo 日志文件: %LOG_FILE%
echo.

REM 1. 检查 Python
echo [DEBUG] 检查 Python 安装... >> %LOG_FILE%
python --version >> %LOG_FILE% 2>&1
if errorlevel 1 (
    echo [错误] Python 未安装或不在 PATH 中 >> %LOG_FILE%
    echo.
    echo X Python 未安装或不在 PATH 中
    echo   请先安装 Python 3.8+ 并添加到系统 PATH
    echo.
    pause
    exit /b 1
)
echo [OK] Python 已安装 >> %LOG_FILE%

REM 2. 检查并创建虚拟环境
echo. >> %LOG_FILE%
echo [DEBUG] 检查虚拟环境... >> %LOG_FILE%
if not exist ".venv" (
    echo [1/8] 创建 Python 虚拟环境...
    echo [DEBUG] 创建虚拟环境... >> %LOG_FILE%
    python -m venv .venv >> %LOG_FILE% 2>&1
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败 >> %LOG_FILE%
        echo X 虚拟环境创建失败
        echo   查看日志: %LOG_FILE%
        pause
        exit /b 1
    )
    echo    OK 虚拟环境创建成功
    echo [OK] 虚拟环境创建成功 >> %LOG_FILE%
) else (
    echo [1/8] OK 虚拟环境已存在
    echo [OK] 虚拟环境已存在 >> %LOG_FILE%
)
echo.

REM 3. 激活虚拟环境
echo [2/8] 激活虚拟环境...
echo [DEBUG] 激活虚拟环境... >> %LOG_FILE%
call .venv\Scripts\activate.bat >> %LOG_FILE% 2>&1
if errorlevel 1 (
    echo [错误] 虚拟环境激活失败 >> %LOG_FILE%
    echo X 虚拟环境激活失败
    echo   查看日志: %LOG_FILE%
    pause
    exit /b 1
)
echo    OK 虚拟环境已激活
echo [OK] 虚拟环境已激活 >> %LOG_FILE%
echo.

REM 4. 检查依赖文件
echo [DEBUG] 检查依赖文件... >> %LOG_FILE%
if exist "requirements.lock.txt" (
    echo [DEBUG] 找到 requirements.lock.txt >> %LOG_FILE%
    set REQ_FILE=requirements.lock.txt
) else if exist "requirements.txt" (
    echo [DEBUG] 找到 requirements.txt >> %LOG_FILE%
    set REQ_FILE=requirements.txt
) else (
    echo [错误] 未找到依赖文件 >> %LOG_FILE%
    echo X 未找到依赖文件 requirements.txt 或 requirements.lock.txt
    echo   查看日志: %LOG_FILE%
    pause
    exit /b 1
)

REM 5. 安装依赖
echo [3/8] 安装项目依赖...
echo    使用 %REQ_FILE%...
echo [DEBUG] 安装依赖: %REQ_FILE% >> %LOG_FILE%
pip install -r %REQ_FILE% >> %LOG_FILE% 2>&1
if errorlevel 1 (
    echo [错误] 依赖安装失败 >> %LOG_FILE%
    echo X 依赖安装失败
    echo   查看日志: %LOG_FILE%
    pause
    exit /b 1
)
echo    OK 依赖安装完成
echo [OK] 依赖安装完成 >> %LOG_FILE%
echo.

REM 6. 设置环境变量
echo [4/8] 配置环境变量...
set DATABASE_URL=sqlite:///database_demo.db
set APP_MODE=demo
set FLASK_ENV=development
set FLASK_DEBUG=1
set FLASK_APP=app.py
set DEV_ALLOW_INSECURE=1
echo    OK DATABASE_URL=sqlite:///database_demo.db
echo    OK APP_MODE=demo
echo    OK FLASK_DEBUG=1
echo [DEBUG] 环境变量已设置 >> %LOG_FILE%
echo   DATABASE_URL=%DATABASE_URL% >> %LOG_FILE%
echo   APP_MODE=%APP_MODE% >> %LOG_FILE%
echo.

REM 7. 自动确认
echo ========================================
echo   INFO 演示模式启动
echo ========================================
echo.
echo 演示模式将执行以下操作：
echo   1. 删除并重建 database_demo.db
echo   2. 自动生成演示数据
echo   3. 不会影响 database.db
echo.
echo [自动确认] 3秒后自动继续...
timeout /t 3 /nobreak >nul
echo OK 已确认，继续启动
echo.

REM 8. 删除旧数据库
echo [5/8] 准备演示数据库...
echo [DEBUG] 删除旧数据库... >> %LOG_FILE%
if exist "database_demo.db" (
    echo    删除旧的 database_demo.db...
    del /f /q database_demo.db >> %LOG_FILE% 2>&1
    if errorlevel 1 (
        echo [错误] 无法删除数据库 >> %LOG_FILE%
        echo X 无法删除 database_demo.db
        echo   可能被其他进程占用
        pause
        exit /b 1
    )
    echo    OK 旧数据库已删除
    echo [OK] 旧数据库已删除 >> %LOG_FILE%
)
echo    OK 准备创建新的演示数据库
echo.

REM 9. 初始化数据库
echo [6/8] 初始化数据库结构...
echo [DEBUG] 初始化数据库... >> %LOG_FILE%

if exist "migrations" (
    echo    使用 Flask-Migrate 初始化...
    echo [DEBUG] 尝试 flask db upgrade >> %LOG_FILE%
    flask db upgrade >> %LOG_FILE% 2>&1
    if errorlevel 1 (
        echo    WARNING Flask-Migrate 失败，使用内置初始化...
        echo [DEBUG] flask db upgrade 失败，尝试内置初始化 >> %LOG_FILE%
        python -c "from core.app_factory import create_app; from utils.db import init_db; app = create_app(); app.app_context().push(); init_db(); print('OK')" >> %LOG_FILE% 2>&1
        if errorlevel 1 (
            echo [错误] 数据库初始化失败 >> %LOG_FILE%
            echo X 数据库初始化失败
            echo   查看日志: %LOG_FILE%
            pause
            exit /b 1
        )
    )
) else (
    echo    使用内置初始化方法...
    echo [DEBUG] 使用内置 init_db >> %LOG_FILE%
    python -c "from core.app_factory import create_app; from utils.db import init_db; app = create_app(); app.app_context().push(); init_db(); print('OK')" >> %LOG_FILE% 2>&1
    if errorlevel 1 (
        echo [错误] 数据库初始化失败 >> %LOG_FILE%
        echo X 数据库初始化失败
        echo   查看日志: %LOG_FILE%
        pause
        exit /b 1
    )
)
echo    OK 数据库结构初始化完成
echo [OK] 数据库初始化完成 >> %LOG_FILE%

REM 10. 创建管理员账号
echo    正在创建管理员账号 admin01...
echo [DEBUG] 创建管理员账号... >> %LOG_FILE%
python -c "import sqlite3; from werkzeug.security import generate_password_hash; conn = sqlite3.connect('database_demo.db'); cursor = conn.execute('SELECT COUNT(*) FROM users WHERE username=\"admin01\"'); count = cursor.fetchone()[0]; conn.close(); exit(0 if count == 0 else 1)" >> %LOG_FILE% 2>&1
if not errorlevel 1 (
    python -c "import sqlite3; from werkzeug.security import generate_password_hash; conn = sqlite3.connect('database_demo.db'); conn.execute('INSERT INTO users (username, password_hash, department, employee_name, employee_no, role, status, must_change_password) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', ('admin01', generate_password_hash('123456'), '系统管理部', '系统管理员', 'EMP001', 'ADMIN', 'ACTIVE', 0)); conn.commit(); conn.close(); print('OK')" >> %LOG_FILE% 2>&1
    echo    OK 管理员账号已创建 (admin01/123456)
    echo [OK] 管理员账号已创建 >> %LOG_FILE%
) else (
    echo    OK 管理员账号已存在
    echo [OK] 管理员账号已存在 >> %LOG_FILE%
)
echo.

REM 11. 生成演示数据
echo [7/8] 生成演示数据...
echo [DEBUG] 生成演示数据... >> %LOG_FILE%
python scripts\seed_demo.py >> %LOG_FILE% 2>&1
if errorlevel 1 (
    echo [错误] 演示数据生成失败 >> %LOG_FILE%
    echo X 演示数据生成失败
    echo   查看日志: %LOG_FILE%
    pause
    exit /b 1
)
echo [OK] 演示数据生成完成 >> %LOG_FILE%
echo.

REM 12. 启动 Flask
echo [8/8] 启动 DeepAudit Pro 演示系统...
echo.
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
echo [DEBUG] 启动 Flask... >> %LOG_FILE%

REM 延迟3秒后自动打开浏览器
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5000"

flask run --host=127.0.0.1 --port=5000 >> %LOG_FILE% 2>&1

REM 如果 Flask 异常退出
if errorlevel 1 (
    echo. >> %LOG_FILE%
    echo [错误] Flask 启动失败 >> %LOG_FILE%
    echo.
    echo X 服务器启动失败
    echo   查看日志: %LOG_FILE%
    pause
    exit /b 1
)

echo. >> %LOG_FILE%
echo [INFO] 服务器正常退出 >> %LOG_FILE%
pause

