@echo off
chcp 65001 >nul
title 角色权限一键修复工具
color 0A

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                  角色权限一键修复工具                      ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [✗] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)
echo [✓] Python 环境正常
echo.

echo [2/5] 检查数据库文件...
if exist "database.db" (
    echo [✓] 找到数据库: database.db
) else if exist "instance\database.db" (
    echo [✓] 找到数据库: instance\database.db
) else (
    echo [✗] 未找到数据库文件
    echo     请确保在项目根目录运行此脚本
    pause
    exit /b 1
)
echo.

echo [3/5] 执行权限修复...
echo ────────────────────────────────────────────────────────────
python fix_role_permissions.py
if errorlevel 1 (
    echo.
    echo [✗] 修复失败，请查看错误信息
    pause
    exit /b 1
)
echo ────────────────────────────────────────────────────────────
echo [✓] 权限修复完成
echo.

echo [4/5] 验证修复结果...
echo ────────────────────────────────────────────────────────────
python verify_permissions.py admin01
echo ────────────────────────────────────────────────────────────
echo.

echo [5/5] 生成部署报告...
if exist "role_permission_fix_report.txt" (
    echo [✓] 报告已生成: role_permission_fix_report.txt
) else (
    echo [!] 未生成报告文件
)
echo.

echo ╔════════════════════════════════════════════════════════════╗
echo ║                      修复完成！                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
echo 📌 重要提示:
echo    1. 请重启应用服务器
echo    2. 让所有用户重新登录以刷新权限
echo    3. 清除浏览器缓存
echo    4. 查看生成的诊断报告了解详细信息
echo.
echo 📋 生成的文件:
echo    - role_permission_fix_report.txt (诊断报告)
echo    - 角色权限修复指南.md (详细文档)
echo.

pause

