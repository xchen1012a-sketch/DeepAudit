# -*- coding: utf-8 -*-
"""
快速创建 admin01 账号到 database.db
用户名: admin01
密码: 123456
"""
import sqlite3
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'database.db'

def main():
    print("=" * 60)
    print("创建 admin01 账号到 database.db")
    print("=" * 60)
    print(f"\n数据库路径: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"\n错误: 数据库不存在: {DB_PATH}")
        print("请先运行系统初始化数据库")
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    try:
        # 检查是否已存在 admin01
        cursor = conn.execute('SELECT * FROM users WHERE username = ?', ('admin01',))
        row = cursor.fetchone()
        
        if row:
            print(f"\nadmin01 账号已存在:")
            print(f"  - ID: {row['id']}")
            print(f"  - 用户名: {row['username']}")
            print(f"  - 员工姓名: {row['employee_name']}")
            print(f"  - 部门: {row['department']}")
            
            # 更新密码为 123456
            print(f"\n正在更新密码为 123456...")
            password_hash = generate_password_hash('123456')
            conn.execute('UPDATE users SET password_hash = ? WHERE username = ?', 
                        (password_hash, 'admin01'))
            conn.commit()
            print(f"✓ 密码已更新")
            
        else:
            print(f"\nadmin01 账号不存在，正在创建...")
            
            # 创建 admin01 账号
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
            print(f"✓ admin01 账号创建成功")
        
        print("\n" + "=" * 60)
        print("完成！")
        print("=" * 60)
        print("\n登录信息:")
        print("  用户名: admin01")
        print("  密码: 123456")
        print("\n数据库: database.db")
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == '__main__':
    main()

