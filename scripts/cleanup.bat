@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   DeepAudit Pro - 项目清理工具
echo ========================================
echo.
echo 此脚本将删除以下文件：
echo   1. Python 缓存文件 (__pycache__)
echo   2. 调试日志文件 (*.log, debug_*.txt)
echo   3. 临时数据库 (database_demo.db, database_clean.db)
echo   4. 数据库备份 (database.db.bak_*)
echo   5. 临时文件
echo.
echo 不会删除：
echo   - database.db (生产数据库)
echo   - .venv (虚拟环境)
echo   - 源代码文件
echo.
echo ========================================
echo.

set /p confirm="确认清理？(输入 Y 继续): "
if /i not "%confirm%"=="Y" (
    echo.
    echo 已取消清理
    pause
    exit /b 0
)

echo.
echo 开始清理...
echo.

REM 切换到项目根目录
cd /d "%~dp0.."

REM 1. 删除 Python 缓存文件
echo [1/5] 删除 Python 缓存文件...
set count=0
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" (
        rd /s /q "%%d" 2>nul
        if not exist "%%d" (
            set /a count+=1
            echo    已删除: %%d
        )
    )
)
echo    [OK] 删除了 !count! 个 __pycache__ 文件夹
echo.

REM 2. 删除日志文件
echo [2/5] 删除日志文件...
set count=0
for %%f in (*.log debug_*.txt _db_output.txt baseline_log.txt debug_500_path.txt) do (
    if exist "%%f" (
        del /q "%%f" 2>nul
        if not exist "%%f" (
            set /a count+=1
            echo    已删除: %%f
        )
    )
)
echo    [OK] 删除了 !count! 个日志文件
echo.

REM 3. 删除临时数据库
echo [3/5] 删除临时数据库...
set count=0
for %%f in (database_demo.db database_clean.db instance\database_demo.db instance\database_clean.db) do (
    if exist "%%f" (
        del /q "%%f" 2>nul
        if not exist "%%f" (
            set /a count+=1
            echo    已删除: %%f
        )
    )
)
echo    [OK] 删除了 !count! 个临时数据库
echo.

REM 4. 删除数据库备份
echo [4/5] 删除数据库备份...
set count=0
for %%f in (database.db.bak_*) do (
    if exist "%%f" (
        del /q "%%f" 2>nul
        if not exist "%%f" (
            set /a count+=1
            echo    已删除: %%f
        )
    )
)
echo    [OK] 删除了 !count! 个数据库备份
echo.

REM 5. 删除临时文件
echo [5/5] 删除临时文件...
set count=0
for %%f in (workbench.activityBar.orientation) do (
    if exist "%%f" (
        del /q "%%f" 2>nul
        if not exist "%%f" (
            set /a count+=1
            echo    已删除: %%f
        )
    )
)
echo    [OK] 删除了 !count! 个临时文件
echo.

echo ========================================
echo   清理完成！
echo ========================================
echo.
echo 已删除的文件类型：
echo   - Python 缓存文件
echo   - 调试日志文件
echo   - 临时数据库
echo   - 数据库备份
echo   - 临时文件
echo.
echo 保留的重要文件：
echo   - database.db (生产数据库)
echo   - .venv (虚拟环境)
echo   - 所有源代码文件
echo.
pause

