@echo off
chcp 65001 >nul
echo ========================================
echo 权限验证工具
echo ========================================
echo.

cd /d "%~dp0"

set /p username="请输入要验证的用户名 (默认: admin01): "
if "%username%"=="" set username=admin01

echo.
echo 正在验证用户: %username%
echo.

python verify_permissions.py %username%

echo.
pause

