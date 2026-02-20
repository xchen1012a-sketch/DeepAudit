#!/bin/bash
# 快速修复 admin01 权限问题
# 使用方法: bash quick_fix_admin01.sh

set -e

echo "========================================"
echo "快速修复 admin01 权限问题"
echo "========================================"
echo ""

# 检查是否在项目根目录
if [ ! -f "app.py" ]; then
    echo "[错误] 请在项目根目录运行此脚本"
    exit 1
fi

# 检查数据库文件
if [ ! -f "database.db" ]; then
    echo "[错误] 数据库文件不存在: database.db"
    exit 1
fi

echo "[步骤 1] 备份数据库..."
BACKUP_FILE="database.db.backup.$(date +%Y%m%d_%H%M%S)"
cp database.db "$BACKUP_FILE"
echo "✓ 备份完成: $BACKUP_FILE"
echo ""

echo "[步骤 2] 运行修复脚本..."
python fix_admin01_permissions.py
echo ""

echo "[步骤 3] 运行诊断脚本验证..."
python diagnose_admin01.py | tail -20
echo ""

echo "========================================"
echo "修复完成！"
echo "========================================"
echo ""
echo "下一步操作："
echo "1. 重启应用: sudo systemctl restart deepaudit"
echo "2. 清除浏览器缓存"
echo "3. 使用 admin01 / admin123 重新登录"
echo ""
echo "如果仍有问题，请查看: 部署修复指南.md"


