#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权限验证脚本
快速验证角色权限是否正确配置和生效
"""

import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

def get_db_path():
    """获取数据库路径"""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url and database_url.startswith("sqlite:///"):
        db_file = database_url[10:]
        if not os.path.isabs(db_file):
            return os.path.abspath(str(PROJECT_ROOT / db_file))
        return os.path.abspath(db_file)
    
    db_path = os.getenv("DB_PATH", "").strip()
    if db_path:
        return os.path.abspath(db_path)
    
    possible_paths = [
        PROJECT_ROOT / "database.db",
        PROJECT_ROOT / "instance" / "database.db",
    ]
    
    for path in possible_paths:
        if path.exists():
            return str(path)
    
    return str(PROJECT_ROOT / "database.db")

def verify_user_permissions(username):
    """验证指定用户的权限"""
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # 查询用户
        user = conn.execute(
            "SELECT id, username, employee_name, status FROM users WHERE username = ? LIMIT 1",
            (username,)
        ).fetchone()
        
        if not user:
            print(f"❌ 用户不存在: {username}")
            return False
        
        print(f"\n{'='*60}")
        print(f"用户信息")
        print(f"{'='*60}")
        print(f"ID: {user['id']}")
        print(f"用户名: {user['username']}")
        print(f"姓名: {user['employee_name'] or '-'}")
        print(f"状态: {user['status']}")
        
        # 查询用户角色
        roles = conn.execute("""
            SELECT r.id, r.role_name, r.status
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = ?
        """, (user['id'],)).fetchall()
        
        print(f"\n{'='*60}")
        print(f"用户角色 ({len(roles)} 个)")
        print(f"{'='*60}")
        
        if not roles:
            print("⚠️  该用户没有分配任何角色")
            return False
        
        for role in roles:
            print(f"- [{role['id']}] {role['role_name']} (状态: {role['status']})")
        
        # 查询用户权限
        permissions = conn.execute("""
            SELECT DISTINCT p.permission_key, p.description
            FROM user_roles ur
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ur.user_id = ?
            ORDER BY p.permission_key
        """, (user['id'],)).fetchall()
        
        print(f"\n{'='*60}")
        print(f"用户权限 ({len(permissions)} 个)")
        print(f"{'='*60}")
        
        if not permissions:
            print("⚠️  该用户没有任何权限")
            print("   可能原因:")
            print("   1. 角色没有配置权限")
            print("   2. role_permissions 表数据缺失")
            return False
        
        for perm in permissions:
            print(f"- {perm['permission_key']}: {perm['description'] or '-'}")
        
        # 检查每个角色的权限
        print(f"\n{'='*60}")
        print(f"角色权限详情")
        print(f"{'='*60}")
        
        for role in roles:
            role_perms = conn.execute("""
                SELECT p.permission_key
                FROM role_permissions rp
                JOIN permissions p ON p.id = rp.permission_id
                WHERE rp.role_id = ?
                ORDER BY p.permission_key
            """, (role['id'],)).fetchall()
            
            print(f"\n{role['role_name']} ({len(role_perms)} 个权限):")
            if role_perms:
                perm_keys = [p['permission_key'] for p in role_perms]
                for i in range(0, len(perm_keys), 5):
                    print(f"  {', '.join(perm_keys[i:i+5])}")
            else:
                print("  ⚠️  该角色没有任何权限")
        
        print(f"\n{'='*60}")
        print(f"✅ 权限验证完成")
        print(f"{'='*60}")
        
        return True
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

def main():
    """主函数"""
    print("\n" + "="*60)
    print("🔍 权限验证工具")
    print("="*60)
    
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = input("\n请输入要验证的用户名 (默认: admin01): ").strip()
        if not username:
            username = "admin01"
    
    print(f"\n正在验证用户: {username}")
    
    success = verify_user_permissions(username)
    
    if success:
        print("\n✅ 验证通过")
        print("\n📌 提示:")
        print("   - 如果权限已正确配置但前端仍无法访问，请清除浏览器缓存并重新登录")
        print("   - 确保应用服务器已重启")
        return 0
    else:
        print("\n❌ 验证失败")
        print("\n📌 建议:")
        print("   1. 运行修复脚本: python fix_role_permissions.py")
        print("   2. 检查数据库完整性")
        print("   3. 查看应用日志")
        return 1

if __name__ == "__main__":
    sys.exit(main())

