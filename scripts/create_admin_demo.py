# -*- coding: utf-8 -*-
"""
为 database_demo.db 创建管理员账号
用户名: admin01
密码: 123456
"""
import sqlite3
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'database_demo.db'

def main():
    print("正在创建管理员账号...")
    
    if not DB_PATH.exists():
        print(f"[ERROR] 数据库不存在: {DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    try:
        # 检查是否已存在 admin01
        cursor = conn.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin01',))
        count = cursor.fetchone()[0]
        
        if count > 0:
            # 更新密码
            password_hash = generate_password_hash('123456')
            conn.execute('UPDATE users SET password_hash = ? WHERE username = ?', 
                        (password_hash, 'admin01'))
            conn.commit()
            print('[OK] 管理员账号已存在，密码已更新为 123456')
        else:
            # 创建新账号
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
            print('[OK] 管理员账号已创建 (admin01/123456)')
        
    except Exception as e:
        print(f"[ERROR] 创建管理员账号失败: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    main()

