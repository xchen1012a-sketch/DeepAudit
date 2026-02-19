# -*- coding: utf-8 -*-
"""
验证数据库写入 - 确认写入操作实际发生在哪个数据库文件
"""
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    print("\n" + "=" * 80)
    print("  数据库写入验证工具")
    print("=" * 80)
    
    # 步骤 1: 导入配置
    print("\n[步骤 1/4] 导入数据库配置...")
    from utils.db import DB_PATH
    print(f"  utils.db.DB_PATH = {DB_PATH}")
    
    # 步骤 2: 记录写入前的状态
    print("\n[步骤 2/4] 记录写入前的数据库状态...")
    
    if not os.path.exists(DB_PATH):
        print(f"  [错误] 数据库文件不存在: {DB_PATH}")
        return 1
    
    before_mtime = os.path.getmtime(DB_PATH)
    before_size = os.path.getsize(DB_PATH)
    
    print(f"  修改时间: {datetime.fromtimestamp(before_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  文件大小: {before_size / 1024:.2f} KB")
    
    # 获取当前记录数
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        before_count = cursor.fetchone()[0]
        print(f"  audit_log 记录数: {before_count}")
    except sqlite3.OperationalError:
        print(f"  [警告] audit_log 表不存在，将创建测试表")
        before_count = 0
    
    # 步骤 3: 执行写入操作
    print("\n[步骤 3/4] 执行测试写入...")
    
    test_message = f"数据库写入验证测试 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    try:
        # 尝试写入 audit_log 表
        cursor.execute("""
            INSERT INTO audit_log (
                user_id, username, action, resource_type, resource_id, 
                details, ip_address, user_agent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            1, 'system', 'DB_WRITE_TEST', 'database', 'verification',
            test_message, '127.0.0.1', 'verify_db_write.py',
            datetime.now().isoformat()
        ))
        conn.commit()
        
        # 验证写入
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        after_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT last_insert_rowid()")
        last_id = cursor.fetchone()[0]
        
        print(f"  [成功] 写入 1 条记录")
        print(f"  新记录 ID: {last_id}")
        print(f"  写入前记录数: {before_count}")
        print(f"  写入后记录数: {after_count}")
        print(f"  增加记录数: {after_count - before_count}")
        
    except Exception as e:
        print(f"  [错误] 写入失败: {e}")
        conn.rollback()
        conn.close()
        return 1
    
    conn.close()
    
    # 步骤 4: 验证文件变化
    print("\n[步骤 4/4] 验证数据库文件变化...")
    
    import time
    time.sleep(0.5)  # 等待文件系统同步
    
    after_mtime = os.path.getmtime(DB_PATH)
    after_size = os.path.getsize(DB_PATH)
    
    print(f"  修改时间: {datetime.fromtimestamp(after_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  文件大小: {after_size / 1024:.2f} KB")
    print(f"  大小变化: {(after_size - before_size) / 1024:.2f} KB")
    
    if after_mtime > before_mtime:
        print(f"  [✓] 文件修改时间已更新")
    else:
        print(f"  [✗] 文件修改时间未变化（可能缓存问题）")
    
    # 总结
    print("\n" + "=" * 80)
    print("  验证结果")
    print("=" * 80)
    print(f"\n  写入目标数据库: {DB_PATH}")
    print(f"  写入操作: 成功")
    print(f"  记录增加: {after_count - before_count} 条")
    print(f"  文件已更新: {'是' if after_mtime > before_mtime else '否'}")
    
    print("\n  【重要】如果你在 Navicat 中打开的是其他文件，将看不到此次写入！")
    print(f"  请确保 Navicat 打开的是: {DB_PATH}")
    print("\n" + "=" * 80)
    
    return 0

if __name__ == '__main__':
    try:
        exit_code = main()
        input("\n按任意键退出...")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[错误] {e}")
        import traceback
        traceback.print_exc()
        input("\n按任意键退出...")
        sys.exit(1)

