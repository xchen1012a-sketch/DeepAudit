#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复 admin01 账号权限问题
适用于部署到服务器后权限丢失的情况
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
print("修复 admin01 账号权限")
print("=" * 80)
print(f"\n数据库路径: {DB_PATH}")
print(f"数据库存在: {DB_PATH.exists()}\n")

if not DB_PATH.exists():
    print("[错误] 数据库文件不存在！")
    sys.exit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

try:
    print("-" * 80)
    print("步骤 1: 检查 admin01 用户")
    print("-" * 80)
    
    cursor = conn.execute("""
        SELECT id, username, employee_name, role, status
        FROM users
        WHERE username = 'admin01'
    """)
    user = cursor.fetchone()
    
    if not user:
        print("[错误] 未找到 admin01 用户！")
        conn.close()
        sys.exit(1)
    
    print(f"✓ 找到用户: {user['username']} (ID: {user['id']})")
    user_id = user['id']
    
    # 确保用户状态为 ACTIVE
    if user['status'] != 'ACTIVE':
        print(f"  [修复] 将用户状态从 '{user['status']}' 改为 'ACTIVE'")
        conn.execute("UPDATE users SET status = 'ACTIVE' WHERE id = ?", (user_id,))
    
    # 确保用户角色字段为 admin
    if user['role'] != 'admin':
        print(f"  [修复] 将用户角色字段从 '{user['role']}' 改为 'admin'")
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    
    print("\n" + "-" * 80)
    print("步骤 2: 检查并创建系统管理员角色")
    print("-" * 80)
    
    cursor = conn.execute("""
        SELECT id, role_name FROM roles WHERE role_name = '系统管理员'
    """)
    admin_role = cursor.fetchone()
    
    if not admin_role:
        print("  [创建] 系统管理员角色不存在，正在创建...")
        conn.execute("""
            INSERT INTO roles (role_name) VALUES ('系统管理员')
        """)
        admin_role_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"  ✓ 创建成功 (ID: {admin_role_id})")
    else:
        admin_role_id = admin_role['id']
        print(f"  ✓ 角色已存在 (ID: {admin_role_id})")
    
    print("\n" + "-" * 80)
    print("步骤 3: 关联用户与角色")
    print("-" * 80)
    
    cursor = conn.execute("""
        SELECT id FROM user_roles WHERE user_id = ? AND role_id = ?
    """, (user_id, admin_role_id))
    user_role = cursor.fetchone()
    
    if not user_role:
        print("  [创建] 用户角色关联不存在，正在创建...")
        conn.execute("""
            INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)
        """, (user_id, admin_role_id))
        print("  ✓ 关联成功")
    else:
        print("  ✓ 关联已存在")
    
    print("\n" + "-" * 80)
    print("步骤 4: 检查并创建权限")
    print("-" * 80)
    
    # 所有必需的权限
    required_permissions = [
        'VIEW_DASHBOARD',
        'VIEW_BANK_STATS',
        'VIEW_INVOICES',
        'CREATE_CASE',
        'ASSIGN_CASE',
        'CLOSE_CASE',
        'DELETE_INVOICE',
        'PULL_BANK_TXN',
        'BANK_PULL',
        'VIEW_AI_LEDGER',
        'MANAGE_USERS',
        'MANAGE_ROLES',
        'MANAGE_RULES',
        'MANAGE_SETTINGS',
        'MANAGE_SYSTEM',
        'VIEW_AUDIT_LOG',
    ]
    
    permission_ids = {}
    created_count = 0
    
    for perm_key in required_permissions:
        cursor = conn.execute("""
            SELECT id FROM permissions WHERE permission_key = ?
        """, (perm_key,))
        perm = cursor.fetchone()
        
        if not perm:
            conn.execute("""
                INSERT INTO permissions (permission_key) VALUES (?)
            """, (perm_key,))
            perm_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            permission_ids[perm_key] = perm_id
            created_count += 1
        else:
            permission_ids[perm_key] = perm['id']
    
    if created_count > 0:
        print(f"  [创建] 创建了 {created_count} 个新权限")
    print(f"  ✓ 共有 {len(permission_ids)} 个权限")
    
    print("\n" + "-" * 80)
    print("步骤 5: 为系统管理员角色分配所有权限")
    print("-" * 80)
    
    assigned_count = 0
    for perm_key, perm_id in permission_ids.items():
        cursor = conn.execute("""
            SELECT id FROM role_permissions WHERE role_id = ? AND permission_id = ?
        """, (admin_role_id, perm_id))
        role_perm = cursor.fetchone()
        
        if not role_perm:
            conn.execute("""
                INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)
            """, (admin_role_id, perm_id))
            assigned_count += 1
    
    if assigned_count > 0:
        print(f"  [分配] 为角色分配了 {assigned_count} 个新权限")
    print(f"  ✓ 系统管理员角色拥有 {len(permission_ids)} 个权限")
    
    print("\n" + "-" * 80)
    print("步骤 6: 验证修复结果")
    print("-" * 80)
    
    cursor = conn.execute("""
        SELECT COUNT(*) as count
        FROM role_permissions rp
        JOIN user_roles ur ON ur.role_id = rp.role_id
        WHERE ur.user_id = ?
    """, (user_id,))
    perm_count = cursor.fetchone()['count']
    
    print(f"  ✓ admin01 通过角色拥有 {perm_count} 个权限")
    
    # 提交所有更改
    conn.commit()
    
    print("\n" + "=" * 80)
    print("修复完成！")
    print("=" * 80)
    print("\n建议操作：")
    print("1. 重启应用服务")
    print("2. 清除浏览器缓存")
    print("3. 重新登录 admin01 账号")
    print("4. 如果仍有问题，检查服务器上的数据库文件路径是否正确")
    
except Exception as e:
    conn.rollback()
    print(f"\n[错误] 修复失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    conn.close()


