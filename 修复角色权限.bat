@echo off
chcp 65001 >nul
echo ========================================
echo 角色权限修复工具
echo ========================================
echo.

cd /d "%~dp0"

echo 正在检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo.
echo 开始执行修复脚本...
echo.

python fix_role_permissions.py

echo.
echo ========================================
echo 修复完成
echo ========================================
echo.
pause

