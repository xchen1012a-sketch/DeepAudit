#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断 admin01 账号权限问题
"""

import sys
import os
import sqlite3
from pathlib import Path

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "database.db"

print("=" * 80)
print("诊断 admin01 账号权限问题")
print("=" * 80)
print(f"\n数据库路径: {DB_PATH}")
print(f"数据库存在: {DB_PATH.exists()}\n")

if not DB_PATH.exists():
    print("[错误] 数据库文件不存在！")
    sys.exit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

print("-" * 80)
print("1. 检查 admin01 用户基本信息")
print("-" * 80)

cursor = conn.execute("""
    SELECT id, username, employee_name, employee_no, department, role, status
    FROM users
    WHERE username = 'admin01'
""")
user = cursor.fetchone()

if not user:
    print("[错误] 未找到 admin01 用户！")
    conn.close()
    sys.exit(1)

print(f"✓ 找到用户:")
print(f"  - ID: {user['id']}")
print(f"  - 用户名: {user['username']}")
print(f"  - 员工姓名: {user['employee_name']}")
print(f"  - 员工编号: {user['employee_no']}")
print(f"  - 部门: {user['department']}")
print(f"  - 角色字段(role): {user['role']}")
print(f"  - 状态: {user['status']}")

user_id = user['id']

print("\n" + "-" * 80)
print("2. 检查用户角色关联 (user_roles 表)")
print("-" * 80)

try:
    cursor = conn.execute("""
        SELECT ur.id, ur.user_id, ur.role_id, r.role_name, r.role_key
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = ?
    """, (user_id,))
    user_roles = cursor.fetchall()
    has_role_key = True
except sqlite3.OperationalError:
    # 如果没有 role_key 字段，使用简化查询
    cursor = conn.execute("""
        SELECT ur.id, ur.user_id, ur.role_id, r.role_name
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = ?
    """, (user_id,))
    user_roles = cursor.fetchall()
    has_role_key = False

if not user_roles:
    print("[警告] 用户没有关联任何角色！")
    print("  这可能是权限问题的原因。")
else:
    print(f"✓ 找到 {len(user_roles)} 个角色关联:")
    for ur in user_roles:
        if has_role_key:
            print(f"  - 角色ID: {ur['role_id']}, 角色名: {ur['role_name']}, 角色键: {ur['role_key']}")
        else:
            print(f"  - 角色ID: {ur['role_id']}, 角色名: {ur['role_name']}")

print("\n" + "-" * 80)
print("3. 检查角色权限 (role_permissions 表)")
print("-" * 80)

if user_roles:
    role_ids = [ur['role_id'] for ur in user_roles]
    placeholders = ','.join('?' * len(role_ids))
    try:
        cursor = conn.execute(f"""
            SELECT rp.role_id, r.role_name, p.permission_key, p.permission_name
            FROM role_permissions rp
            JOIN roles r ON r.id = rp.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id IN ({placeholders})
            ORDER BY r.role_name, p.permission_key
        """, role_ids)
        role_permissions = cursor.fetchall()
        has_permission_name = True
    except sqlite3.OperationalError:
        cursor = conn.execute(f"""
            SELECT rp.role_id, r.role_name, p.permission_key
            FROM role_permissions rp
            JOIN roles r ON r.id = rp.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id IN ({placeholders})
            ORDER BY r.role_name, p.permission_key
        """, role_ids)
        role_permissions = cursor.fetchall()
        has_permission_name = False
    
    if not role_permissions:
        print("[警告] 用户的角色没有分配任何权限！")
        print("  这是权限问题的主要原因。")
    else:
        print(f"✓ 找到 {len(role_permissions)} 个权限:")
        current_role = None
        for rp in role_permissions:
            if current_role != rp['role_name']:
                current_role = rp['role_name']
                print(f"\n  角色: {current_role}")
            if has_permission_name:
                print(f"    - {rp['permission_key']}: {rp['permission_name']}")
            else:
                print(f"    - {rp['permission_key']}")
else:
    print("[跳过] 用户没有角色关联，无法检查角色权限。")

print("\n" + "-" * 80)
print("4. 检查所有可用权限")
print("-" * 80)

try:
    cursor = conn.execute("""
        SELECT id, permission_key, permission_name
        FROM permissions
        ORDER BY permission_key
    """)
    all_permissions = cursor.fetchall()
    has_permission_name = True
except sqlite3.OperationalError:
    cursor = conn.execute("""
        SELECT id, permission_key
        FROM permissions
        ORDER BY permission_key
    """)
    all_permissions = cursor.fetchall()
    has_permission_name = False

print(f"✓ 系统中共有 {len(all_permissions)} 个权限:")
for p in all_permissions:
    if has_permission_name:
        print(f"  - {p['permission_key']}: {p['permission_name']}")
    else:
        print(f"  - {p['permission_key']}")

print("\n" + "-" * 80)
print("5. 检查所有可用角色")
print("-" * 80)

try:
    cursor = conn.execute("""
        SELECT id, role_name, role_key, description
        FROM roles
        ORDER BY id
    """)
    all_roles = cursor.fetchall()
    has_role_key = True
    has_description = True
except sqlite3.OperationalError:
    try:
        cursor = conn.execute("""
            SELECT id, role_name, description
            FROM roles
            ORDER BY id
        """)
        all_roles = cursor.fetchall()
        has_role_key = False
        has_description = True
    except sqlite3.OperationalError:
        cursor = conn.execute("""
            SELECT id, role_name
            FROM roles
            ORDER BY id
        """)
        all_roles = cursor.fetchall()
        has_role_key = False
        has_description = False

print(f"✓ 系统中共有 {len(all_roles)} 个角色:")
for r in all_roles:
    if has_role_key:
        print(f"  - ID: {r['id']}, 名称: {r['role_name']}, 键: {r['role_key']}")
    else:
        print(f"  - ID: {r['id']}, 名称: {r['role_name']}")
    if has_description and 'description' in r.keys() and r['description']:
        print(f"    描述: {r['description']}")

print("\n" + "-" * 80)
print("6. 诊断结果")
print("-" * 80)

issues = []
recommendations = []

# 检查用户状态
if user['status'] != 'ACTIVE':
    issues.append(f"用户状态不是 ACTIVE (当前: {user['status']})")
    recommendations.append("将用户状态改为 ACTIVE")

# 检查角色关联
if not user_roles:
    issues.append("用户没有关联任何角色")
    recommendations.append("为用户分配系统管理员角色")

# 检查权限
if user_roles and not role_permissions:
    issues.append("用户的角色没有分配任何权限")
    recommendations.append("为用户的角色分配必要的权限")

# 检查是否是系统管理员
is_system_admin = False
if user['username'] in ['admin', 'admin01', 'administrator']:
    is_system_admin = True
    print("✓ 用户名符合系统管理员兜底逻辑 (SYSTEM_ADMIN_USERNAMES)")

if user['role'] and 'admin' in user['role'].lower():
    print(f"✓ 用户角色字段包含 'admin': {user['role']}")

if issues:
    print("\n[发现问题]")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
    
    print("\n[修复建议]")
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec}")
else:
    print("\n✓ 未发现明显问题")
    if is_system_admin:
        print("  用户应该通过系统管理员兜底逻辑获得权限")

print("\n" + "-" * 80)
print("7. 权限系统工作原理说明")
print("-" * 80)

print("""
权限判断流程：
1. 检查用户名是否在 SYSTEM_ADMIN_USERNAMES 中 (admin, admin01 等)
   → 如果是，直接赋予所有管理员权限（兜底逻辑）

2. 查询数据库中的权限：
   users → user_roles → roles → role_permissions → permissions
   
3. 如果数据库中没有权限记录，使用兜底逻辑：
   - 根据 users.role 字段判断（如 'admin', 'finance_manager' 等）
   - 赋予对应的默认权限

关键代码位置：
- utils/security.py: current_user_permissions()
- utils/security.py: is_system_admin()
- utils/security.py: SYSTEM_ADMIN_USERNAMES
""")

print("\n" + "=" * 80)
print("诊断完成")
print("=" * 80)

conn.close()

