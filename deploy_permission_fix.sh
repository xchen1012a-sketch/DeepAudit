#!/bin/bash
# 权限问题修复 - 快速部署脚本

set -e

echo "========================================="
echo "  DeepAudit 权限问题修复 - 部署脚本"
echo "========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在项目根目录
if [ ! -f "app.py" ]; then
    echo -e "${RED}错误: 请在项目根目录运行此脚本${NC}"
    exit 1
fi

echo -e "${YELLOW}步骤 1/4: 备份数据库...${NC}"
if [ -f "database.db" ]; then
    BACKUP_FILE="database.db.backup.$(date +%Y%m%d_%H%M%S)"
    cp database.db "$BACKUP_FILE"
    echo -e "${GREEN}✓ 数据库已备份到: $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}⚠ 未找到 database.db，跳过备份${NC}"
fi

echo ""
echo -e "${YELLOW}步骤 2/4: 验证修改的文件...${NC}"
FILES=(
    "utils/security.py"
    "routes/auth.py"
    "static/js/permission_refresh.js"
    "static/js/admin_roles.js"
    "static/js/admin_users.js"
    "templates/layout/base.html"
)

ALL_EXISTS=true
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ $file${NC}"
    else
        echo -e "${RED}✗ $file (文件不存在)${NC}"
        ALL_EXISTS=false
    fi
done

if [ "$ALL_EXISTS" = false ]; then
    echo -e "${RED}错误: 部分文件不存在，请检查${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}步骤 3/4: 检查 Python 进程...${NC}"
if pgrep -f "python.*app.py" > /dev/null; then
    echo -e "${YELLOW}发现运行中的 Python 进程${NC}"
    read -p "是否要重启应用? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "正在停止应用..."
        pkill -f "python.*app.py" || true
        sleep 2
        echo -e "${GREEN}✓ 应用已停止${NC}"
        
        echo "正在启动应用..."
        nohup python app.py > app.log 2>&1 &
        sleep 3
        
        if pgrep -f "python.*app.py" > /dev/null; then
            echo -e "${GREEN}✓ 应用已启动${NC}"
        else
            echo -e "${RED}✗ 应用启动失败，请检查 app.log${NC}"
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}未发现运行中的应用${NC}"
    read -p "是否要启动应用? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "正在启动应用..."
        nohup python app.py > app.log 2>&1 &
        sleep 3
        
        if pgrep -f "python.*app.py" > /dev/null; then
            echo -e "${GREEN}✓ 应用已启动${NC}"
        else
            echo -e "${RED}✗ 应用启动失败，请检查 app.log${NC}"
            exit 1
        fi
    fi
fi

echo ""
echo -e "${YELLOW}步骤 4/4: 验证修复...${NC}"
echo "请手动验证以下内容："
echo "1. 访问系统并登录"
echo "2. 进入 '组织与权限' -> '角色权限'"
echo "3. 修改一个角色的权限并保存"
echo "4. 打开浏览器开发者工具（F12），查看 Console 是否有 '[权限刷新]' 日志"
echo "5. 刷新页面，验证权限是否生效"

echo ""
echo -e "${GREEN}========================================="
echo "  部署完成！"
echo "=========================================${NC}"
echo ""
echo "详细的修复说明请查看: PERMISSION_FIX.md"
echo ""


