"""
验证数据库初始化结果
"""

import sqlite3
import os
import sys
from pathlib import Path

# 设置输出编码为UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.path.abspath(str(os.getenv("DB_PATH") or (PROJECT_ROOT / "database.db")))

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print("=" * 60)
print("数据库初始化验证")
print("=" * 60)

# 检查admin01用户
admin = conn.execute("SELECT * FROM users WHERE username = 'admin01'").fetchone()
if admin:
    print(f"\n[OK] admin01用户存在:")
    print(f"  - ID: {admin['id']}")
    print(f"  - 用户名: {admin['username']}")
    print(f"  - 部门: {admin['department']}")
    print(f"  - 员工姓名: {admin['employee_name']}")
    print(f"  - 角色: {admin['role']}")
else:
    print("\n[ERROR] admin01用户不存在！")

# 检查用户总数
user_count = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt']
print(f"\n用户总数: {user_count}")

# 检查发票数量
invoice_count = conn.execute("SELECT COUNT(*) as cnt FROM invoices").fetchone()['cnt']
print(f"发票数量: {invoice_count}")

# 检查其他表的数据量
tables = [
    "audit_logs", "risk_cases", "risk_events", "bank_transactions",
    "departments", "roles", "permissions"
]

print("\n其他表数据量:")
for table in tables:
    try:
        count = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()['cnt']
        print(f"  - {table}: {count}")
    except:
        print(f"  - {table}: 表不存在")

conn.close()

print("\n" + "=" * 60)
