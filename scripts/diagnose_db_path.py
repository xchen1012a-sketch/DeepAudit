# -*- coding: utf-8 -*-
"""
数据库路径诊断工具 - 找出 Flask 应用实际使用的数据库文件
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

def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def check_env_vars():
    """检查环境变量配置"""
    print_section("步骤 1/5：检查环境变量")
    
    database_url = os.getenv("DATABASE_URL", "").strip()
    sqlalchemy_uri = os.getenv("SQLALCHEMY_DATABASE_URI", "").strip()
    db_path = os.getenv("DB_PATH", "").strip()
    app_mode = os.getenv("APP_MODE", "").strip()
    
    print(f"  DATABASE_URL           = {database_url or '(未设置)'}")
    print(f"  SQLALCHEMY_DATABASE_URI = {sqlalchemy_uri or '(未设置)'}")
    print(f"  DB_PATH                = {db_path or '(未设置)'}")
    print(f"  APP_MODE               = {app_mode or '(未设置)'}")
    
    return database_url or sqlalchemy_uri

def check_config_files():
    """检查配置文件中的数据库设置"""
    print_section("步骤 2/5：检查配置文件")
    
    # 检查 core/settings.py
    settings_file = PROJECT_ROOT / "core" / "settings.py"
    if settings_file.exists():
        print(f"\n  [core/settings.py]")
        with open(settings_file, 'r', encoding='utf-8') as f:
            for line in f:
                if 'SQLALCHEMY_DATABASE_URI' in line and '=' in line:
                    print(f"    {line.strip()}")
    
    # 检查 utils/db.py
    db_utils_file = PROJECT_ROOT / "utils" / "db.py"
    if db_utils_file.exists():
        print(f"\n  [utils/db.py]")
        with open(db_utils_file, 'r', encoding='utf-8') as f:
            in_function = False
            for line in f:
                if 'def _get_db_path_from_env' in line:
                    in_function = True
                if in_function and ('return' in line or 'DB_PATH =' in line):
                    print(f"    {line.strip()}")
                    if 'DB_PATH =' in line:
                        break

def scan_db_files():
    """扫描所有数据库文件"""
    print_section("步骤 3/5：扫描所有数据库文件")
    
    db_files = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # 跳过虚拟环境
        dirs[:] = [d for d in dirs if d not in {'.venv', 'venv', '__pycache__', '.git', 'node_modules'}]
        
        for filename in files:
            if filename.endswith('.db'):
                full_path = Path(root) / filename
                try:
                    stat = full_path.stat()
                    rel_path = full_path.relative_to(PROJECT_ROOT)
                    
                    # 尝试读取数据库信息
                    table_count = 0
                    row_count = 0
                    try:
                        conn = sqlite3.connect(str(full_path))
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                        table_count = cursor.fetchone()[0]
                        
                        # 尝试获取 users 表的行数
                        try:
                            cursor.execute("SELECT COUNT(*) FROM users")
                            row_count = cursor.fetchone()[0]
                        except:
                            pass
                        
                        conn.close()
                    except:
                        pass
                    
                    db_files.append({
                        'path': full_path,
                        'rel_path': rel_path,
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'tables': table_count,
                        'users': row_count
                    })
                except Exception as e:
                    print(f"  [警告] 无法读取 {filename}: {e}")
    
    # 按修改时间排序
    db_files.sort(key=lambda x: x['mtime'], reverse=True)
    
    print(f"\n  找到 {len(db_files)} 个数据库文件：\n")
    
    for i, db in enumerate(db_files, 1):
        mtime_str = datetime.fromtimestamp(db['mtime']).strftime('%Y-%m-%d %H:%M:%S')
        size_kb = db['size'] / 1024
        
        marker = "🔴 [最新]" if i == 1 else "⚪"
        print(f"  {marker} {db['rel_path']}")
        print(f"      修改时间: {mtime_str}")
        print(f"      文件大小: {size_kb:.2f} KB")
        print(f"      表数量:   {db['tables']}")
        print(f"      用户数:   {db['users']}")
        print()
    
    return db_files

def test_import_db_path():
    """测试导入 utils.db.DB_PATH"""
    print_section("步骤 4/5：测试 Python 导入的 DB_PATH")
    
    try:
        # 临时添加项目根目录到 sys.path
        sys.path.insert(0, str(PROJECT_ROOT))
        
        from utils.db import DB_PATH
        
        print(f"\n  utils.db.DB_PATH = {DB_PATH}")
        
        if Path(DB_PATH).exists():
            stat = Path(DB_PATH).stat()
            mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            size_kb = stat.st_size / 1024
            print(f"  文件存在: ✓")
            print(f"  修改时间: {mtime_str}")
            print(f"  文件大小: {size_kb:.2f} KB")
        else:
            print(f"  文件存在: ✗ (路径不存在)")
        
        return DB_PATH
    except Exception as e:
        print(f"\n  [错误] 无法导入 DB_PATH: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_flask_app_db():
    """测试 Flask 应用实际使用的数据库"""
    print_section("步骤 5/5：测试 Flask 应用的数据库配置")
    
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        
        # 导入 Flask 应用
        from app import app
        
        sqlalchemy_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        print(f"\n  Flask app.config['SQLALCHEMY_DATABASE_URI'] = {sqlalchemy_uri}")
        
        # 解析路径
        if sqlalchemy_uri.startswith('sqlite:///'):
            db_file = sqlalchemy_uri[10:]
            if not os.path.isabs(db_file):
                db_path = PROJECT_ROOT / db_file
            else:
                db_path = Path(db_file)
            
            print(f"  解析后的绝对路径 = {db_path}")
            
            if db_path.exists():
                stat = db_path.stat()
                mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                size_kb = stat.st_size / 1024
                print(f"  文件存在: ✓")
                print(f"  修改时间: {mtime_str}")
                print(f"  文件大小: {size_kb:.2f} KB")
            else:
                print(f"  文件存在: ✗")
            
            return str(db_path)
        else:
            print(f"  [警告] 非 SQLite 数据库或格式不识别")
            return None
            
    except Exception as e:
        print(f"\n  [错误] 无法加载 Flask 应用: {e}")
        import traceback
        traceback.print_exc()
        return None

def print_summary(env_db, db_files, utils_db_path, flask_db_path):
    """打印诊断总结"""
    print_section("诊断总结与建议")
    
    print("\n  【当前状态】")
    print(f"    环境变量指定:     {env_db or '(未设置，使用默认值)'}")
    print(f"    utils.db.DB_PATH: {utils_db_path or '(无法获取)'}")
    print(f"    Flask 应用使用:   {flask_db_path or '(无法获取)'}")
    
    if db_files:
        latest = db_files[0]
        print(f"\n    最新修改的数据库: {latest['rel_path']}")
        print(f"    修改时间:         {datetime.fromtimestamp(latest['mtime']).strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n  【问题分析】")
    
    # 检查是否有多个数据库文件
    non_export_dbs = [db for db in db_files if 'export' not in str(db['rel_path']).lower()]
    
    if len(non_export_dbs) > 1:
        print(f"    ⚠️  发现 {len(non_export_dbs)} 个非导出数据库文件（不包括 exports/ 目录）")
        print(f"    ⚠️  可能存在多个数据库副本，导致写入和读取不同步")
    
    # 检查 exports 目录的数据库
    export_dbs = [db for db in db_files if 'export' in str(db['rel_path']).lower()]
    if export_dbs:
        print(f"    ⚠️  exports/ 目录下有 {len(export_dbs)} 个数据库文件")
        print(f"    ⚠️  这些是静态导出副本，不会自动同步")
    
    print("\n  【修复建议】")
    print("    1. 统一数据库路径：所有配置都指向同一个数据库文件")
    print("    2. 推荐使用根目录的 database.db 作为唯一真实库")
    print("    3. Navicat 应该直接打开真实库，而不是 exports/ 下的副本")
    print("    4. 如果需要导出副本，每次修改后需要重新运行导出脚本")
    
    if flask_db_path:
        print(f"\n  【Navicat 应该打开的文件】")
        print(f"    {flask_db_path}")
        print(f"    （这是 Flask 应用实际写入的数据库）")

def main():
    print("\n" + "=" * 80)
    print("  DeepAudit Pro - 数据库路径诊断工具")
    print("=" * 80)
    print(f"\n  项目根目录: {PROJECT_ROOT}")
    
    env_db = check_env_vars()
    check_config_files()
    db_files = scan_db_files()
    utils_db_path = test_import_db_path()
    flask_db_path = test_flask_app_db()
    
    print_summary(env_db, db_files, utils_db_path, flask_db_path)
    
    print("\n" + "=" * 80)
    print("  诊断完成")
    print("=" * 80)
    print()

if __name__ == '__main__':
    try:
        main()
        input("\n按任意键退出...")
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n\n[错误] {e}")
        import traceback
        traceback.print_exc()
        input("\n按任意键退出...")

