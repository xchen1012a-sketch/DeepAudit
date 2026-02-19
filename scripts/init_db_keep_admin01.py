"""
数据库初始化脚本：删除所有数据，但保留admin01账号
运行方式：python scripts/init_db_keep_admin01.py
"""

import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path

# 设置输出编码为UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 导入数据库路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.path.abspath(str(os.getenv("DB_PATH") or (PROJECT_ROOT / "database.db")))


def get_admin01_user(conn: sqlite3.Connection) -> dict | None:
    """获取admin01用户信息"""
    cursor = conn.execute(
        """
        SELECT id, username, password_hash, department, employee_name, 
               employee_no, role, status, must_change_password, 
               failed_login_attempts, lock_until, password_updated_at, position_id
        FROM users
        WHERE username = 'admin01'
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if row:
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "department": row[3],
            "employee_name": row[4],
            "employee_no": row[5],
            "role": row[6],
            "status": row[7],
            "must_change_password": row[8],
            "failed_login_attempts": row[9],
            "lock_until": row[10],
            "password_updated_at": row[11],
            "position_id": row[12] if len(row) > 12 else None,
        }
    return None


def restore_admin01_user(conn: sqlite3.Connection, admin_data: dict) -> None:
    """恢复admin01用户"""
    # 先删除所有用户
    conn.execute("DELETE FROM users")
    
    # 删除用户角色关联
    conn.execute("DELETE FROM user_roles")
    
    # 重新插入admin01用户
    conn.execute(
        """
        INSERT INTO users (
            username, password_hash, department, employee_name, employee_no, 
            role, status, must_change_password, failed_login_attempts, 
            lock_until, password_updated_at, position_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            admin_data["username"],
            admin_data["password_hash"],
            admin_data["department"],
            admin_data["employee_name"],
            admin_data["employee_no"],
            admin_data["role"],
            admin_data["status"],
            admin_data["must_change_password"],
            admin_data["failed_login_attempts"],
            admin_data["lock_until"],
            admin_data["password_updated_at"],
            admin_data.get("position_id"),
        ),
    )
    
    # 如果admin01有角色关联，需要重新创建
    # 这里假设admin01应该有admin角色，但为了安全，先不自动创建角色关联
    print(f"[init] admin01用户已恢复 (ID: {conn.execute('SELECT last_insert_rowid()').fetchone()[0]})")


def clear_all_data(conn: sqlite3.Connection) -> None:
    """删除所有业务数据，但保留表结构"""
    
    # 需要删除数据的表（按依赖顺序）
    tables_to_clear = [
        # 审计和日志表
        "audit_trace_events",
        "audit_traces",
        "audit_evidence",
        "audit_logs",
        "audit_log",
        
        # 业务数据表
        "case_actions",
        "risk_cases",
        "risk_events",
        "ai_prompt_ledger",
        "bank_transactions",
        "invoices",
        
        # 审批相关（如果有）
        "approvals",
        
        # 企业化相关
        "db_risk_cases",
        "db_metrics",
        "db_sync_logs",
        "db_integrations",
        "db_departments",
        "db_enterprises",
        
        # 工作流
        "workflow_config",
        
        # 用户相关（除了users表，因为要保留admin01）
        "user_roles",
        "role_permissions",
        "role_data_scopes",
        
        # 登录安全
        "login_security_locks",
        
        # 部门、职位、角色（保留结构，但清空数据，因为admin01可能不依赖这些）
        "positions",
        "departments",
        "roles",
        "permissions",
        
        # 治理规则（可选，保留默认规则）
        # "governance_rules",
        
        # 系统设置（可选，保留配置）
        # "system_settings",
    ]
    
    print("\n[init] 开始清理数据...")
    for table in tables_to_clear:
        try:
            cursor = conn.execute(f"DELETE FROM {table}")
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                print(f"  - {table}: 删除了 {deleted_count} 条记录")
        except sqlite3.OperationalError as e:
            # 表不存在时跳过
            if "no such table" not in str(e).lower():
                print(f"  - {table}: 跳过（表不存在或错误: {e}）")
    
    # 重置自增ID
    print("\n[init] 重置自增ID...")
    conn.execute("DELETE FROM sqlite_sequence WHERE name != 'users'")
    print("  - 自增ID已重置（users表除外）")


def main():
    """主函数"""
    import sys
    
    print("=" * 60)
    print("数据库初始化脚本：保留admin01，删除其他所有数据")
    print("=" * 60)
    print(f"\n数据库路径: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print(f"\n[错误] 数据库文件不存在: {DB_PATH}")
        return
    
    # 检查是否有 --yes 参数自动确认
    auto_confirm = "--yes" in sys.argv or "-y" in sys.argv
    
    if not auto_confirm:
        # 确认操作
        print("\n[警告] 此操作将删除除admin01外的所有数据！")
        confirm = input("确认继续？(输入 'yes' 继续): ").strip().lower()
        if confirm != "yes":
            print("[取消] 操作已取消")
            return
    else:
        print("\n[自动确认] 使用 --yes 参数，跳过确认步骤")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # 1. 备份admin01用户信息
        print("\n[步骤1] 备份admin01用户信息...")
        admin_data = get_admin01_user(conn)
        if not admin_data:
            print("[错误] 未找到admin01用户！")
            print("      请先确保admin01用户存在，或手动创建后再运行此脚本。")
            return
        
        print(f"  [OK] 找到admin01用户:")
        print(f"    - ID: {admin_data['id']}")
        print(f"    - 用户名: {admin_data['username']}")
        print(f"    - 部门: {admin_data['department']}")
        print(f"    - 员工姓名: {admin_data['employee_name']}")
        print(f"    - 角色: {admin_data['role']}")
        
        # 2. 删除所有数据
        print("\n[步骤2] 删除所有业务数据...")
        clear_all_data(conn)
        
        # 3. 恢复admin01用户
        print("\n[步骤3] 恢复admin01用户...")
        restore_admin01_user(conn, admin_data)
        
        # 4. 提交事务
        conn.commit()
        print("\n[完成] 数据库初始化完成！")
        print(f"  - admin01账号已保留")
        print(f"  - 所有其他数据已删除")
        print(f"  - 表结构已保留")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[错误] 初始化失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
