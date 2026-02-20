@echo off
chcp 65001 >nul
title DeepAudit Pro - 快速启动

:: 设置环境变量
set DEV_ALLOW_INSECURE=1
set FLASK_HOST=127.0.0.1
set FLASK_PORT=5000
set FLASK_DEBUG=0

echo ========================================
echo    DeepAudit Pro 智能审计系统
echo ========================================
echo.
echo 正在启动...
echo 访问地址: http://127.0.0.1:5000
echo 默认账号: admin01 / admin123
echo.
echo 按 Ctrl+C 停止系统
echo ========================================
echo.

:: 启动Flask应用
python app.py

pause

