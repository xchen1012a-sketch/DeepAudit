@echo off
REM 快速修复 admin01 权限问题 (Windows 版本)
REM 使用方法: quick_fix_admin01.bat

echo ========================================
echo 快速修复 admin01 权限问题
echo ========================================
echo.

REM 检查是否在项目根目录
if not exist "app.py" (
    echo [错误] 请在项目根目录运行此脚本
    exit /b 1
)

REM 检查数据库文件
if not exist "database.db" (
    echo [错误] 数据库文件不存在: database.db
    exit /b 1
)

echo [步骤 1] 备份数据库...
set BACKUP_FILE=database.db.backup.%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set BACKUP_FILE=%BACKUP_FILE: =0%
copy database.db "%BACKUP_FILE%"
echo ✓ 备份完成: %BACKUP_FILE%
echo.

echo [步骤 2] 运行修复脚本...
python fix_admin01_permissions.py
echo.

echo [步骤 3] 运行诊断脚本验证...
python diagnose_admin01.py
echo.

echo ========================================
echo 修复完成！
echo ========================================
echo.
echo 下一步操作：
echo 1. 重启应用
echo 2. 清除浏览器缓存
echo 3. 使用 admin01 / admin123 重新登录
echo.
echo 如果仍有问题，请查看: 部署修复指南.md
pause

