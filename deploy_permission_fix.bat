@echo off
REM 权限问题修复 - Windows 快速部署脚本
setlocal enabledelayedexpansion

echo =========================================
echo   DeepAudit 权限问题修复 - 部署脚本
echo =========================================
echo.

REM 检查是否在项目根目录
if not exist "app.py" (
    echo [错误] 请在项目根目录运行此脚本
    exit /b 1
)

echo [步骤 1/4] 备份数据库...
if exist "database.db" (
    set BACKUP_FILE=database.db.backup.%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
    set BACKUP_FILE=!BACKUP_FILE: =0!
    copy database.db "!BACKUP_FILE!" >nul
    echo [成功] 数据库已备份到: !BACKUP_FILE!
) else (
    echo [警告] 未找到 database.db，跳过备份
)

echo.
echo [步骤 2/4] 验证修改的文件...
set ALL_EXISTS=1
set FILES=utils\security.py routes\auth.py static\js\permission_refresh.js static\js\admin_roles.js static\js\admin_users.js templates\layout\base.html

for %%f in (%FILES%) do (
    if exist "%%f" (
        echo [成功] %%f
    ) else (
        echo [失败] %%f (文件不存在^)
        set ALL_EXISTS=0
    )
)

if !ALL_EXISTS! == 0 (
    echo [错误] 部分文件不存在，请检查
    exit /b 1
)

echo.
echo [步骤 3/4] 检查 Python 进程...
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [提示] 发现运行中的 Python 进程
    set /p RESTART="是否要重启应用? (y/n): "
    if /i "!RESTART!"=="y" (
        echo 正在停止应用...
        taskkill /F /IM python.exe >nul 2>&1
        timeout /t 2 >nul
        echo [成功] 应用已停止
        
        echo 正在启动应用...
        start /b python app.py > app.log 2>&1
        timeout /t 3 >nul
        
        tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo [成功] 应用已启动
        ) else (
            echo [失败] 应用启动失败，请检查 app.log
            exit /b 1
        )
    )
) else (
    echo [提示] 未发现运行中的应用
    set /p START="是否要启动应用? (y/n): "
    if /i "!START!"=="y" (
        echo 正在启动应用...
        start /b python app.py > app.log 2>&1
        timeout /t 3 >nul
        
        tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo [成功] 应用已启动
        ) else (
            echo [失败] 应用启动失败，请检查 app.log
            exit /b 1
        )
    )
)

echo.
echo [步骤 4/4] 验证修复...
echo 请手动验证以下内容：
echo 1. 访问系统并登录
echo 2. 进入 '组织与权限' -^> '角色权限'
echo 3. 修改一个角色的权限并保存
echo 4. 打开浏览器开发者工具（F12），查看 Console 是否有 '[权限刷新]' 日志
echo 5. 刷新页面，验证权限是否生效

echo.
echo =========================================
echo   部署完成！
echo =========================================
echo.
echo 详细的修复说明请查看: PERMISSION_FIX.md
echo.

pause


