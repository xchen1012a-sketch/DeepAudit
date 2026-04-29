@echo off
chcp 65001 >nul
title 停止 DeepAudit Pro

echo ========================================
echo    停止 DeepAudit Pro 系统
echo ========================================
echo.

:: 查找并终止Python进程（运行app.py的进程）
echo 正在查找运行中的系统进程...
echo.

:: 查找占用5000端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    echo 找到进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
    if not errorlevel 1 (
        echo [成功] 已停止端口5000上的进程
    )
)

:: 查找占用5001端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5001" ^| findstr "LISTENING"') do (
    echo 找到进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
    if not errorlevel 1 (
        echo [成功] 已停止端口5001上的进程
    )
)

echo.
echo ========================================
echo  系统已停止
echo ========================================
echo.
pause




