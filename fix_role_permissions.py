#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色权限修复脚本
解决角色权限配置后不生效的问题

问题排查：
1. 权限缓存未刷新 - Flask session 缓存
2. 接口未更新角色权限 - role_permissions 表未正确写入
3. 数据库权限字段未写入 - 数据完整性检查
4. 前端权限判断逻辑错误 - 权限查询逻辑验证
5. 路由/按钮权限未重新加载 - 需要重新登录或清除 session

修复方案：
- 验证并修复 role_permissions 表数据
- 清理所有用户 session（强制重新登录）
- 验证权限查询逻辑
- 输出诊断报告
"""

import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
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
    
    # 检查多个可能的位置
    possible_paths = [
        PROJECT_ROOT / "database.db",
        PROJECT_ROOT / "instance" / "database.db",
    ]
    
    for path in possible_paths:
        if path.exists():
            return str(path)
    
    return str(PROJECT_ROOT / "database.db")

DB_PATH = get_db_path()

def get_conn():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_tables_exist(conn):
    """检查必要的表是否存在"""
    tables = ['users', 'roles', 'permissions', 'user_roles', 'role_permissions']
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ({})".format(
            ','.join(['?'] * len(tables))
        ),
        tables
    )
    existing = {row[0] for row in cursor.fetchall()}
    missing = set(tables) - existing
    
    if missing:
        print(f"❌ 缺少必要的表: {', '.join(missing)}")
        return False
    
    print("✅ 所有必要的表都存在")
    return True

def diagnose_role_permissions(conn):
    """诊断角色权限配置"""
    print("\n" + "="*60)
    print("📊 角色权限诊断")
    print("="*60)
    
    # 1. 检查角色表
    roles = conn.execute("SELECT id, role_name, status FROM roles WHERE is_deleted = 0").fetchall()
    print(f"\n1️⃣ 角色总数: {len(roles)}")
    for role in roles:
        status = role['status'] or 'ACTIVE'
        print(f"   - [{role['id']}] {role['role_name']} (状态: {status})")
    
    # 2. 检查权限表
    permissions = conn.execute("SELECT id, permission_key FROM permissions").fetchall()
    print(f"\n2️⃣ 权限总数: {len(permissions)}")
    
    # 3. 检查角色权限关联
    print(f"\n3️⃣ 角色权限关联检查:")
    for role in roles:
        role_perms = conn.execute("""
            SELECT p.permission_key
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = ?
        """, (role['id'],)).fetchall()
        
        perm_keys = [p['permission_key'] for p in role_perms]
        print(f"   - {role['role_name']}: {len(perm_keys)} 个权限")
        if len(perm_keys) == 0:
            print(f"     ⚠️  警告: 该角色没有任何权限!")
        elif len(perm_keys) <= 5:
            print(f"     权限: {', '.join(perm_keys)}")
    
    # 4. 检查用户角色关联
    print(f"\n4️⃣ 用户角色关联检查:")
    users = conn.execute("""
        SELECT u.id, u.username, u.employee_name, u.status
        FROM users u
        WHERE u.status = 'ACTIVE'
        ORDER BY u.id
    """).fetchall()
    
    for user in users:
        user_roles = conn.execute("""
            SELECT r.role_name
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = ?
        """, (user['id'],)).fetchall()
        
        role_names = [r['role_name'] for r in user_roles]
        
        # 获取用户的所有权限
        user_perms = conn.execute("""
            SELECT DISTINCT p.permission_key
            FROM user_roles ur
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ur.user_id = ?
        """, (user['id'],)).fetchall()
        
        perm_count = len(user_perms)
        
        print(f"   - [{user['id']}] {user['username']} ({user['employee_name'] or '-'})")
        print(f"     角色: {', '.join(role_names) if role_names else '无角色'}")
        print(f"     权限数: {perm_count}")
        
        if not role_names:
            print(f"     ⚠️  警告: 该用户没有分配任何角色!")
        elif perm_count == 0:
            print(f"     ⚠️  警告: 该用户的角色没有任何权限!")

def fix_role_permissions(conn):
    """修复角色权限数据"""
    print("\n" + "="*60)
    print("🔧 开始修复角色权限")
    print("="*60)
    
    # 1. 确保系统管理员拥有所有权限
    print("\n1️⃣ 修复系统管理员权限...")
    admin_role = conn.execute(
        "SELECT id FROM roles WHERE role_name = '系统管理员' AND is_deleted = 0 LIMIT 1"
    ).fetchone()
    
    if admin_role:
        admin_role_id = admin_role['id']
        all_perms = conn.execute("SELECT id FROM permissions").fetchall()
        
        fixed_count = 0
        for perm in all_perms:
            try:
                conn.execute("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (?, ?)
                    ON CONFLICT(role_id, permission_id) DO NOTHING
                """, (admin_role_id, perm['id']))
                fixed_count += 1
            except Exception as e:
                print(f"   ⚠️  添加权限失败: {e}")
        
        conn.commit()
        print(f"   ✅ 系统管理员权限已修复 (添加 {fixed_count} 个权限)")
    else:
        print("   ⚠️  未找到系统管理员角色")
    
    # 2. 检查并修复其他角色的基础权限
    print("\n2️⃣ 检查其他角色权限...")
    
    # 财务经理应该有的基础权限
    finance_manager_perms = [
        'VIEW_DASHBOARD', 'VIEW_BANK_STATS', 'VIEW_INVOICES',
        'CREATE_CASE', 'ASSIGN_CASE', 'CLOSE_CASE', 'DELETE_INVOICE'
    ]
    
    finance_manager = conn.execute(
        "SELECT id FROM roles WHERE role_name = '财务经理' AND is_deleted = 0 LIMIT 1"
    ).fetchone()
    
    if finance_manager:
        for perm_key in finance_manager_perms:
            perm = conn.execute(
                "SELECT id FROM permissions WHERE permission_key = ?", (perm_key,)
            ).fetchone()
            if perm:
                try:
                    conn.execute("""
                        INSERT INTO role_permissions (role_id, permission_id)
                        VALUES (?, ?)
                        ON CONFLICT(role_id, permission_id) DO NOTHING
                    """, (finance_manager['id'], perm['id']))
                except Exception:
                    pass
        conn.commit()
        print("   ✅ 财务经理权限已修复")
    
    # 3. 确保 admin01 用户有系统管理员角色
    print("\n3️⃣ 修复 admin01 用户角色...")
    admin_user = conn.execute(
        "SELECT id FROM users WHERE username = 'admin01' LIMIT 1"
    ).fetchone()
    
    if admin_user and admin_role:
        try:
            conn.execute("""
                INSERT INTO user_roles (user_id, role_id)
                VALUES (?, ?)
                ON CONFLICT(user_id, role_id) DO NOTHING
            """, (admin_user['id'], admin_role_id))
            conn.commit()
            print("   ✅ admin01 用户角色已修复")
        except Exception as e:
            print(f"   ⚠️  修复失败: {e}")
    
    print("\n✅ 角色权限修复完成")

def clear_flask_sessions():
    """清除 Flask session 文件（如果使用文件系统存储）"""
    print("\n" + "="*60)
    print("🗑️  清除 Session 缓存")
    print("="*60)
    
    # Flask 默认使用客户端 cookie 存储 session，无需清理文件
    # 但如果使用了 Flask-Session 扩展，可能需要清理
    
    session_dirs = [
        PROJECT_ROOT / "flask_session",
        PROJECT_ROOT / "instance" / "flask_session",
    ]
    
    cleared = False
    for session_dir in session_dirs:
        if session_dir.exists():
            import shutil
            try:
                shutil.rmtree(session_dir)
                print(f"   ✅ 已清除: {session_dir}")
                cleared = True
            except Exception as e:
                print(f"   ⚠️  清除失败: {e}")
    
    if not cleared:
        print("   ℹ️  未找到 session 文件目录（可能使用 cookie 存储）")
        print("   ℹ️  建议：让所有用户重新登录以刷新权限")

def verify_permission_query():
    """验证权限查询逻辑"""
    print("\n" + "="*60)
    print("🔍 验证权限查询逻辑")
    print("="*60)
    
    conn = get_conn()
    
    # 测试 admin01 用户的权限
    admin_user = conn.execute(
        "SELECT id, username FROM users WHERE username = 'admin01' LIMIT 1"
    ).fetchone()
    
    if admin_user:
        user_id = admin_user['id']
        
        # 查询用户权限
        perms = conn.execute("""
            SELECT DISTINCT p.permission_key
            FROM user_roles ur
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ur.user_id = ?
        """, (user_id,)).fetchall()
        
        perm_keys = [p['permission_key'] for p in perms]
        
        print(f"\n   用户: {admin_user['username']}")
        print(f"   权限数量: {len(perm_keys)}")
        
        if len(perm_keys) > 0:
            print(f"   ✅ 权限查询正常")
            if len(perm_keys) <= 10:
                print(f"   权限列表: {', '.join(perm_keys)}")
        else:
            print(f"   ❌ 权限查询异常：用户没有任何权限")
    else:
        print("   ⚠️  未找到 admin01 用户")
    
    conn.close()

def generate_report():
    """生成诊断报告"""
    print("\n" + "="*60)
    print("📋 生成诊断报告")
    print("="*60)
    
    report_path = PROJECT_ROOT / "role_permission_fix_report.txt"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*60 + "\n")
        f.write("角色权限修复报告\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*60 + "\n\n")
        
        conn = get_conn()
        
        # 角色统计
        roles = conn.execute("SELECT COUNT(*) as cnt FROM roles WHERE is_deleted = 0").fetchone()
        f.write(f"角色总数: {roles['cnt']}\n")
        
        # 权限统计
        perms = conn.execute("SELECT COUNT(*) as cnt FROM permissions").fetchone()
        f.write(f"权限总数: {perms['cnt']}\n")
        
        # 用户统计
        users = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE status = 'ACTIVE'").fetchone()
        f.write(f"活跃用户数: {users['cnt']}\n\n")
        
        # 详细信息
        f.write("角色权限详情:\n")
        f.write("-"*60 + "\n")
        
        roles_detail = conn.execute("""
            SELECT r.role_name, COUNT(rp.permission_id) as perm_count
            FROM roles r
            LEFT JOIN role_permissions rp ON rp.role_id = r.id
            WHERE r.is_deleted = 0
            GROUP BY r.id, r.role_name
            ORDER BY r.id
        """).fetchall()
        
        for role in roles_detail:
            f.write(f"{role['role_name']}: {role['perm_count']} 个权限\n")
        
        conn.close()
    
    print(f"   ✅ 报告已生成: {report_path}")

def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 角色权限修复工具")
    print("="*60)
    print(f"数据库路径: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print(f"\n❌ 错误: 数据库文件不存在: {DB_PATH}")
        return 1
    
    print(f"数据库大小: {os.path.getsize(DB_PATH) / 1024:.2f} KB")
    
    try:
        conn = get_conn()
        
        # 1. 检查表结构
        if not check_tables_exist(conn):
            print("\n❌ 数据库表结构不完整，无法继续")
            return 1
        
        # 2. 诊断当前状态
        diagnose_role_permissions(conn)
        
        # 3. 询问是否修复
        print("\n" + "="*60)
        response = input("是否执行修复? (y/n): ").strip().lower()
        
        if response == 'y':
            # 4. 执行修复
            fix_role_permissions(conn)
            
            # 5. 清除 session
            clear_flask_sessions()
            
            # 6. 验证修复结果
            print("\n" + "="*60)
            print("✅ 验证修复结果")
            print("="*60)
            diagnose_role_permissions(conn)
            
            # 7. 验证权限查询
            verify_permission_query()
            
            # 8. 生成报告
            generate_report()
            
            print("\n" + "="*60)
            print("✅ 修复完成!")
            print("="*60)
            print("\n📌 重要提示:")
            print("   1. 请重启应用服务器")
            print("   2. 让所有用户重新登录以刷新权限")
            print("   3. 如果问题仍然存在，请检查前端权限判断逻辑")
            print("   4. 查看生成的诊断报告了解详细信息")
        else:
            print("\n❌ 已取消修复")
        
        conn.close()
        return 0
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

