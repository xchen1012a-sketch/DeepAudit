#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""系统核心问题诊断脚本 - 不执行任何修改操作"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "database.db"

def check_database_structure():
    """检查数据库表结构"""
    print("=" * 80)
    print("1. 数据库表结构检查")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # 获取所有表
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    
    print(f"\n数据库表数量: {len(tables)}")
    print("表列表:", [row['name'] for row in tables])
    
    # 检查关键表
    key_tables = ['users', 'roles', 'permissions', 'user_roles', 'role_permissions', 
                  'invoices', 'audit_log', 'departments']
    
    print("\n关键表存在性检查:")
    for table in key_tables:
        exists = any(row['name'] == table for row in tables)
        print(f"  {table}: {'✓ 存在' if exists else '✗ 缺失'}")
    
    conn.close()
    return True


def check_users_and_roles():
    """检查用户和角色配置"""
    print("\n" + "=" * 80)
    print("2. 用户和角色配置检查")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # 用户统计
    user_count = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt']
    active_users = conn.execute(
        "SELECT COUNT(*) as cnt FROM users WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'"
    ).fetchone()['cnt']
    
    print(f"\n用户统计:")
    print(f"  总用户数: {user_count}")
    print(f"  活跃用户数: {active_users}")
    
    # 角色统计
    role_count = conn.execute("SELECT COUNT(*) as cnt FROM roles").fetchone()['cnt']
    active_roles = conn.execute(
        "SELECT COUNT(*) as cnt FROM roles WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'"
    ).fetchone()['cnt']
    
    print(f"\n角色统计:")
    print(f"  总角色数: {role_count}")
    print(f"  活跃角色数: {active_roles}")
    
    # 权限统计
    perm_count = conn.execute("SELECT COUNT(*) as cnt FROM permissions").fetchone()['cnt']
    print(f"\n权限统计:")
    print(f"  总权限数: {perm_count}")
    
    # 检查用户角色关联
    user_role_count = conn.execute("SELECT COUNT(*) as cnt FROM user_roles").fetchone()['cnt']
    print(f"\n用户角色关联:")
    print(f"  关联记录数: {user_role_count}")
    
    # 检查角色权限关联
    role_perm_count = conn.execute("SELECT COUNT(*) as cnt FROM role_permissions").fetchone()['cnt']
    print(f"\n角色权限关联:")
    print(f"  关联记录数: {role_perm_count}")
    
    conn.close()
    return True


def check_permission_sync():
    """检查权限配置是否能实时同步"""
    print("\n" + "=" * 80)
    print("3. 权限配置实时同步检查")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # 检查是否有用户没有角色
    users_without_roles = conn.execute("""
        SELECT u.id, u.username, u.employee_name, u.department, u.role as legacy_role
        FROM users u
        LEFT JOIN user_roles ur ON u.id = ur.user_id
        WHERE ur.user_id IS NULL
        AND UPPER(COALESCE(u.status, 'ACTIVE')) = 'ACTIVE'
    """).fetchall()
    
    print(f"\n没有角色关联的活跃用户数: {len(users_without_roles)}")
    if users_without_roles:
        print("  详情:")
        for user in users_without_roles[:5]:
            print(f"    - ID:{user['id']}, 用户名:{user['username']}, "
                  f"姓名:{user['employee_name']}, 部门:{user['department']}, "
                  f"旧角色字段:{user['legacy_role']}")
        if len(users_without_roles) > 5:
            print(f"    ... 还有 {len(users_without_roles) - 5} 个用户")
    
    # 检查是否有角色没有权限
    roles_without_perms = conn.execute("""
        SELECT r.id, r.role_name, r.data_scope, r.status
        FROM roles r
        LEFT JOIN role_permissions rp ON r.id = rp.role_id
        WHERE rp.role_id IS NULL
        AND UPPER(COALESCE(r.status, 'ACTIVE')) = 'ACTIVE'
    """).fetchall()
    
    print(f"\n没有权限配置的活跃角色数: {len(roles_without_perms)}")
    if roles_without_perms:
        print("  详情:")
        for role in roles_without_perms:
            print(f"    - ID:{role['id']}, 角色名:{role['role_name']}, "
                  f"数据范围:{role['data_scope']}, 状态:{role['status']}")
    
    # 检查用户-角色-权限完整链路
    print("\n用户-角色-权限完整链路检查:")
    complete_chain = conn.execute("""
        SELECT COUNT(DISTINCT u.id) as user_count
        FROM users u
        INNER JOIN user_roles ur ON u.id = ur.user_id
        INNER JOIN roles r ON ur.role_id = r.id
        INNER JOIN role_permissions rp ON r.id = rp.role_id
        INNER JOIN permissions p ON rp.permission_id = p.id
        WHERE UPPER(COALESCE(u.status, 'ACTIVE')) = 'ACTIVE'
        AND UPPER(COALESCE(r.status, 'ACTIVE')) = 'ACTIVE'
    """).fetchone()['user_count']
    
    print(f"  拥有完整权限链路的用户数: {complete_chain}")
    
    conn.close()
    return True


def check_data_scope_config():
    """检查数据范围配置"""
    print("\n" + "=" * 80)
    print("4. 数据范围配置检查")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # 检查角色的数据范围配置
    roles = conn.execute("""
        SELECT id, role_name, data_scope, 
               COALESCE(data_scope_policy, '{}') as policy
        FROM roles
        WHERE UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
        ORDER BY id
    """).fetchall()
    
    print(f"\n活跃角色的数据范围配置:")
    for role in roles:
        policy = json.loads(role['policy']) if role['policy'] else {}
        scope_type = policy.get('scope_type') or role['data_scope'] or 'DEPT'
        dept_ids = policy.get('dept_ids', [])
        user_ids = policy.get('user_ids', [])
        
        print(f"\n  角色: {role['role_name']} (ID:{role['id']})")
        print(f"    数据范围类型: {scope_type}")
        if dept_ids:
            print(f"    指定部门ID: {dept_ids}")
        if user_ids:
            print(f"    指定用户ID: {user_ids}")
    
    conn.close()
    return True


def check_event_bus():
    """检查事件总线机制"""
    print("\n" + "=" * 80)
    print("5. 事件总线和数据流通检查")
    print("=" * 80)
    
    print("\n事件总线机制:")
    print("  - 事件总线类: events/bus.py -> EventBus")
    print("  - 事件类型定义: events/types.py")
    print("  - 发布方法: EventBus.publish(event_type, payload)")
    print("  - 订阅方法: EventBus.get_since(cursor)")
    
    # 检查事件总线是否在应用中初始化
    try:
        from core.app_factory import create_app
        app = create_app()
        
        if hasattr(app, 'event_bus'):
            print("\n  ✓ 事件总线已在应用中初始化")
            print(f"    事件总线类型: {type(app.event_bus)}")
        else:
            print("\n  ✗ 事件总线未在应用中初始化")
            print("    可能影响: 模块间实时数据同步可能受限")
    except Exception as e:
        print(f"\n  ⚠ 无法检查事件总线初始化状态: {e}")
    
    return True


def check_audit_log():
    """检查审计日志"""
    print("\n" + "=" * 80)
    print("6. 审计日志检查")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # 审计日志统计
    total_logs = conn.execute("SELECT COUNT(*) as cnt FROM audit_log").fetchone()['cnt']
    print(f"\n审计日志总数: {total_logs}")
    
    # 按动作类型统计
    action_stats = conn.execute("""
        SELECT action_type, COUNT(*) as cnt
        FROM audit_log
        GROUP BY action_type
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    
    print("\n审计日志动作类型统计 (Top 10):")
    for stat in action_stats:
        print(f"  {stat['action_type']}: {stat['cnt']} 条")
    
    # 最近的审计日志
    recent_logs = conn.execute("""
        SELECT id, created_at, action_type, operator, target_type, target_id
        FROM audit_log
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()
    
    print("\n最近的审计日志 (最新5条):")
    for log in recent_logs:
        print(f"  [{log['created_at']}] {log['action_type']} by {log['operator']} "
              f"on {log['target_type']}:{log['target_id']}")
    
    conn.close()
    return True


def check_role_permission_realtime():
    """检查角色权限变更后用户能否实时获取"""
    print("\n" + "=" * 80)
    print("7. 角色权限实时生效检查")
    print("=" * 80)
    
    print("\n权限获取机制分析:")
    print("  1. 用户登录时: session存储user_id")
    print("  2. 每次请求时: current_user()从数据库实时查询用户信息")
    print("  3. 权限检查时: get_user_permissions(user_id)实时查询权限")
    print("  4. 数据范围时: list_user_role_data_scopes(user_id)实时查询")
    
    print("\n实时生效路径:")
    print("  角色权限变更 -> 数据库更新 -> 下次请求时实时查询 -> 新权限生效")
    
    print("\n潜在问题:")
    print("  - Session缓存: 如果session中缓存了权限信息，可能不会实时更新")
    print("  - 应用缓存: 如果使用了缓存机制，需要清除缓存")
    
    # 检查是否使用了缓存
    try:
        from core.extensions import cache
        print(f"\n  缓存扩展: {type(cache)}")
        if hasattr(cache, 'cache'):
            print("    ⚠ 系统使用了缓存，权限变更后可能需要清除缓存")
        else:
            print("    ✓ 缓存扩展未启用或为空实现")
    except Exception as e:
        print(f"\n  无法检查缓存状态: {e}")
    
    return True


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("DeepAudit_Pro 系统核心问题诊断")
    print("=" * 80)
    print("\n诊断范围:")
    print("  1. 数据库表结构完整性")
    print("  2. 用户角色权限配置")
    print("  3. 权限配置实时同步")
    print("  4. 数据范围配置")
    print("  5. 事件总线和数据流通")
    print("  6. 审计日志")
    print("  7. 角色权限实时生效")
    print("\n注意: 本脚本仅进行诊断分析，不执行任何修改操作")
    print("=" * 80)
    
    try:
        check_database_structure()
        check_users_and_roles()
        check_permission_sync()
        check_data_scope_config()
        check_event_bus()
        check_audit_log()
        check_role_permission_realtime()
        
        print("\n" + "=" * 80)
        print("诊断完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n诊断过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

