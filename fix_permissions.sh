#!/bin/bash
# 角色权限修复脚本 - Linux/Mac 版本

set -e

echo "========================================"
echo "角色权限一键修复工具"
echo "========================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python
echo "[1/5] 检查 Python 环境..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
    echo -e "${GREEN}[✓]${NC} Python 环境正常: $(python3 --version)"
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
    echo -e "${GREEN}[✓]${NC} Python 环境正常: $(python --version)"
else
    echo -e "${RED}[✗]${NC} 未找到 Python，请先安装 Python 3.8+"
    exit 1
fi
echo ""

# 检查数据库
echo "[2/5] 检查数据库文件..."
if [ -f "database.db" ]; then
    echo -e "${GREEN}[✓]${NC} 找到数据库: database.db"
elif [ -f "instance/database.db" ]; then
    echo -e "${GREEN}[✓]${NC} 找到数据库: instance/database.db"
else
    echo -e "${RED}[✗]${NC} 未找到数据库文件"
    echo "    请确保在项目根目录运行此脚本"
    exit 1
fi
echo ""

# 执行修复
echo "[3/5] 执行权限修复..."
echo "----------------------------------------"
$PYTHON_CMD fix_role_permissions.py
if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}[✗]${NC} 修复失败，请查看错误信息"
    exit 1
fi
echo "----------------------------------------"
echo -e "${GREEN}[✓]${NC} 权限修复完成"
echo ""

# 验证结果
echo "[4/5] 验证修复结果..."
echo "----------------------------------------"
$PYTHON_CMD verify_permissions.py admin01
echo "----------------------------------------"
echo ""

# 生成报告
echo "[5/5] 生成部署报告..."
if [ -f "role_permission_fix_report.txt" ]; then
    echo -e "${GREEN}[✓]${NC} 报告已生成: role_permission_fix_report.txt"
else
    echo -e "${YELLOW}[!]${NC} 未生成报告文件"
fi
echo ""

echo "========================================"
echo "修复完成！"
echo "========================================"
echo ""
echo -e "${YELLOW}📌 重要提示:${NC}"
echo "   1. 请重启应用服务器"
echo "      - systemd: sudo systemctl restart deepaudit"
echo "      - supervisor: sudo supervisorctl restart deepaudit"
echo "      - gunicorn: pkill -HUP gunicorn"
echo "   2. 让所有用户重新登录以刷新权限"
echo "   3. 清除浏览器缓存"
echo "   4. 查看生成的诊断报告了解详细信息"
echo ""
echo -e "${GREEN}📋 生成的文件:${NC}"
echo "   - role_permission_fix_report.txt (诊断报告)"
echo "   - 角色权限修复指南.md (详细文档)"
echo ""

# 询问是否重启服务
read -p "是否现在重启应用服务? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "请选择服务管理方式:"
    echo "1) systemd"
    echo "2) supervisor"
    echo "3) 手动重启 (显示命令)"
    echo "4) 跳过"
    read -p "请选择 (1-4): " -n 1 -r choice
    echo ""
    
    case $choice in
        1)
            echo "正在重启服务 (systemd)..."
            sudo systemctl restart deepaudit
            echo -e "${GREEN}[✓]${NC} 服务已重启"
            ;;
        2)
            echo "正在重启服务 (supervisor)..."
            sudo supervisorctl restart deepaudit
            echo -e "${GREEN}[✓]${NC} 服务已重启"
            ;;
        3)
            echo ""
            echo "请手动执行以下命令之一:"
            echo "  systemd:    sudo systemctl restart deepaudit"
            echo "  supervisor: sudo supervisorctl restart deepaudit"
            echo "  gunicorn:   pkill -HUP gunicorn"
            echo ""
            ;;
        *)
            echo "已跳过服务重启"
            ;;
    esac
fi

echo ""
echo -e "${GREEN}✅ 所有操作完成！${NC}"
echo ""

