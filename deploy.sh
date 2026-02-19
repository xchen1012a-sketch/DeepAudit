#!/bin/bash
# DeepAudit Pro 部署脚本

set -e

echo "=========================================="
echo "DeepAudit Pro 部署脚本"
echo "=========================================="

# 检查 Python 版本
echo "检查 Python 版本..."
python3 --version

# 创建必要的目录
echo "创建必要的目录..."
mkdir -p logs
mkdir -p instance
mkdir -p uploads
mkdir -p exports

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "创建 Python 虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 升级 pip
echo "升级 pip..."
pip install --upgrade pip

# 安装依赖
echo "安装 Python 依赖..."
pip install -r requirements.txt
pip install gunicorn pymysql

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "警告：未找到 .env 文件"
    if [ -f ".env.production" ]; then
        echo "复制 .env.production 到 .env..."
        cp .env.production .env
        echo "请编辑 .env 文件，配置 SECRET_KEY 等参数"
        exit 1
    else
        echo "错误：请创建 .env 配置文件"
        exit 1
    fi
fi

# 初始化数据库
echo "初始化数据库..."
python3 scripts/verify_init.py

# 创建管理员账户（如果需要）
if [ "$1" == "--create-admin" ]; then
    echo "创建管理员账户..."
    python3 scripts/create_admin.py
fi

# 设置文件权限
echo "设置文件权限..."
chmod -R 755 .
chmod -R 777 logs
chmod -R 777 instance
chmod -R 777 uploads
chmod -R 777 exports

echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo ""
echo "启动命令："
echo "  开发模式: python3 app.py"
echo "  生产模式: gunicorn -c gunicorn_config.py app:app"
echo ""
echo "使用 PM2 管理（推荐）："
echo "  pm2 start gunicorn_config.py --name deepaudit --interpreter python3"
echo ""

