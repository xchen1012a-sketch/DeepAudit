# -*- coding: utf-8 -*-
"""
检查和创建 admin01 账号
"""
import sqlite3
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def check_and_create_admin(db_path):
    """检查并创建 admin01 账号"""
    print(f"\n检查数据库: {db_path}")
    
    if not db_path.exists():
        print(f"  数据库不存在: {db_path}")
        return False
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    try:
        # 检查是否有 admin01
        cursor = conn.execute('SELECT * FROM users WHERE username = ?', ('admin01',))
        row = cursor.fetchone()
        
        if row:
            print(f"  找到 admin01 账号:")
            print(f"    - ID: {row['id']}")
            print(f"    - 用户名: {row['username']}")
            print(f"    - 员工姓名: {row['employee_name']}")
            print(f"    - 部门: {row['department']}")
            print(f"    - 角色: {row['role']}")
            return True
        else:
            print(f"  未找到 admin01 账号，正在创建...")
            
            # 创建 admin01 账号，密码 123456
            password_hash = generate_password_hash('123456')
            
            conn.execute('''
                INSERT INTO users (
                    username, password_hash, department, employee_name, 
                    employee_no, role, status, must_change_password
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'admin01',
                password_hash,
                '系统管理部',
                '系统管理员',
                'EMP001',
                'ADMIN',
                'ACTIVE',
                0
            ))
            
            conn.commit()
            print(f"  ✓ admin01 账号创建成功")
            print(f"    - 用户名: admin01")
            print(f"    - 密码: 123456")
            return True
            
    except Exception as e:
        print(f"  错误: {e}")
        return False
    finally:
        conn.close()

def main():
    print("=" * 60)
    print("检查和创建 admin01 账号 (密码: 123456)")
    print("=" * 60)
    
    # 检查三个数据库
    databases = [
        PROJECT_ROOT / 'database.db',
        PROJECT_ROOT / 'database_demo.db',
        PROJECT_ROOT / 'database_clean.db',
    ]
    
    for db_path in databases:
        check_and_create_admin(db_path)
    
    print("\n" + "=" * 60)
    print("检查完成！")
    print("=" * 60)

if __name__ == '__main__':
    main()

