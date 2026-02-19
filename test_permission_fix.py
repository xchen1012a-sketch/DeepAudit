#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权限问题修复 - 验证脚本
用于验证权限系统是否正常工作
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_permission_functions():
    """测试权限相关函数"""
    print("=" * 60)
    print("测试 1: 权限查询函数")
    print("=" * 60)
    
    try:
        from utils.db import get_user_permissions, get_user_role_names, user_has_permission
        
        # 测试用户 ID 1（通常是管理员）
        user_id = 1
        
        print(f"\n用户 ID: {user_id}")
        print("-" * 60)
        
        # 获取角色
        roles = get_user_role_names(user_id)
        print(f"角色列表: {roles}")
        
        # 获取权限
        permissions = get_user_permissions(user_id)
        print(f"权限列表: {permissions}")
        print(f"权限数量: {len(permissions)}")
        
        # 测试特定权限
        test_perms = ["VIEW_DASHBOARD", "MANAGE_USERS", "VIEW_INVOICES"]
        print("\n权限检查:")
        for perm in test_perms:
            has_perm = user_has_permission(user_id, perm)
            status = "✓" if has_perm else "✗"
            print(f"  {status} {perm}: {has_perm}")
        
        print("\n✓ 权限查询函数测试通过")
        return True
        
    except Exception as e:
        print(f"\n✗ 权限查询函数测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_security_functions():
    """测试安全相关函数"""
    print("\n" + "=" * 60)
    print("测试 2: 安全函数")
    print("=" * 60)
    
    try:
        from utils.security import (
            is_system_admin,
            has_governance_admin_role,
            can_approve,
            current_user_role_keys,
            current_user_permissions
        )
        from utils.db import get_user_by_id
        
        # 测试用户 ID 1
        user_id = 1
        user = get_user_by_id(user_id)
        
        if not user:
            print(f"✗ 未找到用户 ID: {user_id}")
            return False
        
        print(f"\n用户信息:")
        print(f"  ID: {user.get('id')}")
        print(f"  用户名: {user.get('username')}")
        print(f"  部门: {user.get('department')}")
        print(f"  角色字段: {user.get('role')}")
        
        print("\n角色判断:")
        print(f"  是否系统管理员: {is_system_admin(user)}")
        print(f"  是否治理管理员: {has_governance_admin_role(user)}")
        print(f"  是否可审批: {can_approve(user)}")
        
        print("\n角色键:")
        role_keys = current_user_role_keys(user)
        for key in sorted(role_keys):
            print(f"  - {key}")
        
        print("\n权限列表:")
        permissions = current_user_permissions(user)
        for perm in sorted(permissions):
            print(f"  - {perm}")
        
        print(f"\n权限总数: {len(permissions)}")
        
        print("\n✓ 安全函数测试通过")
        return True
        
    except Exception as e:
        print(f"\n✗ 安全函数测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_structure():
    """测试数据库结构"""
    print("\n" + "=" * 60)
    print("测试 3: 数据库结构")
    print("=" * 60)
    
    try:
        from utils.db import get_conn
        
        with get_conn() as conn:
            # 检查关键表
            tables = [
                'users',
                'roles',
                'permissions',
                'user_roles',
                'role_permissions',
                'role_data_scopes'
            ]
            
            print("\n表结构检查:")
            for table in tables:
                cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                count = cursor.fetchone()['cnt']
                print(f"  ✓ {table}: {count} 条记录")
            
            # 检查权限数据
            print("\n权限数据检查:")
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM permissions")
            perm_count = cursor.fetchone()['cnt']
            print(f"  权限总数: {perm_count}")
            
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM role_permissions")
            role_perm_count = cursor.fetchone()['cnt']
            print(f"  角色-权限关联: {role_perm_count}")
            
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM user_roles")
            user_role_count = cursor.fetchone()['cnt']
            print(f"  用户-角色关联: {user_role_count}")
            
            # 检查是否有用户没有角色
            cursor = conn.execute("""
                SELECT COUNT(*) as cnt 
                FROM users u 
                LEFT JOIN user_roles ur ON u.id = ur.user_id 
                WHERE ur.user_id IS NULL AND u.status = 'ACTIVE'
            """)
            no_role_count = cursor.fetchone()['cnt']
            if no_role_count > 0:
                print(f"  ⚠ 警告: {no_role_count} 个活跃用户没有分配角色")
            
            # 检查是否有角色没有权限
            cursor = conn.execute("""
                SELECT COUNT(*) as cnt 
                FROM roles r 
                LEFT JOIN role_permissions rp ON r.id = rp.role_id 
                WHERE rp.role_id IS NULL AND r.status = 'ACTIVE'
            """)
            no_perm_count = cursor.fetchone()['cnt']
            if no_perm_count > 0:
                print(f"  ⚠ 警告: {no_perm_count} 个活跃角色没有分配权限")
        
        print("\n✓ 数据库结构测试通过")
        return True
        
    except Exception as e:
        print(f"\n✗ 数据库结构测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  DeepAudit 权限系统验证脚本")
    print("=" * 60)
    
    results = []
    
    # 运行测试
    results.append(("权限查询函数", test_permission_functions()))
    results.append(("安全函数", test_security_functions()))
    results.append(("数据库结构", test_database_structure()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n✓ 所有测试通过！权限系统工作正常。")
        return 0
    else:
        print("\n✗ 部分测试失败，请检查上述错误信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())

