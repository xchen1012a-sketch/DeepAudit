# -*- coding: utf-8 -*-
"""
重置admin01管理员密码
运行方式：python reset_admin_password.py
"""

import sqlite3
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash
from datetime import datetime

# 设置输出编码为UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 数据库路径
PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "database.db"

def reset_password():
    """重置admin01密码为123456"""
    
    if not DB_PATH.exists():
        print(f"[错误] 数据库文件不存在: {DB_PATH}")
        return False
    
    # 新密码
    new_password = "123456"
    
    # 生成密码哈希
    password_hash = generate_password_hash(new_password)
    
    print("=" * 60)
    print("重置admin01管理员密码")
    print("=" * 60)
    print(f"\n数据库路径: {DB_PATH}")
    print(f"新密码: {new_password}")
    print(f"密码哈希: {password_hash[:50]}...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 检查admin01用户是否存在
        cursor.execute("SELECT id, username, employee_name FROM users WHERE username = ?", ("admin01",))
        user = cursor.fetchone()
        
        if not user:
            print("\n[错误] 未找到admin01用户！")
            conn.close()
            return False
        
        user_id, username, employee_name = user
        print(f"\n找到用户:")
        print(f"  - ID: {user_id}")
        print(f"  - 用户名: {username}")
        print(f"  - 姓名: {employee_name}")
        
        # 更新密码
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            UPDATE users 
            SET password_hash = ?,
                password_updated_at = ?,
                must_change_password = 0,
                failed_login_attempts = 0,
                lock_until = NULL
            WHERE username = ?
            """,
            (password_hash, now, "admin01")
        )
        
        # 清除登录失败记录
        cursor.execute("DELETE FROM login_security_locks WHERE username = ?", ("admin01",))
        
        conn.commit()
        
        print(f"\n[成功] 密码已重置！")
        print(f"  - 新密码: {new_password}")
        print(f"  - 更新时间: {now}")
        print(f"  - 已清除登录失败记录")
        print(f"  - 已解除账号锁定")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n[错误] 重置失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = reset_password()
    sys.exit(0 if success else 1)


