@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ================================================================================
echo   DeepAudit Pro - 数据库同步问题修复工具
echo ================================================================================
echo.

cd /d "%~dp0.."

REM 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 虚拟环境不存在
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo [步骤 1/3] 诊断数据库路径配置...
echo.
python scripts\diagnose_db_path.py
echo.

echo.
echo [步骤 2/3] 验证数据库写入...
echo.
python scripts\verify_db_write.py
echo.

echo.
echo [步骤 3/3] 导出最新数据库到 exports/ 目录...
echo.
python scripts\export_real_db.py
echo.

echo.
echo ================================================================================
echo   修复完成！
echo ================================================================================
echo.
echo   请根据上方诊断结果：
echo   1. 确认 Flask 应用实际使用的数据库文件路径
echo   2. 在 Navicat 中打开该路径的数据库文件（不是 exports/ 下的副本）
echo   3. 如果需要使用 exports/ 下的副本，每次修改后需重新运行此脚本
echo.

pause

