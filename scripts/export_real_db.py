# -*- coding: utf-8 -*-
"""
自动识别并导出真实数据库（非 demo/clean）供 Navicat 使用
"""
import os
import sys
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def get_database_url_from_env():
    """从环境变量获取数据库配置"""
    return os.getenv('DATABASE_URL') or os.getenv('SQLALCHEMY_DATABASE_URI')


def parse_sqlite_path(database_url):
    """解析 SQLite 数据库路径"""
    if not database_url:
        return None
    
    # 处理 sqlite:/// 格式
    if database_url.startswith('sqlite:///'):
        path = database_url.replace('sqlite:///', '', 1)
        # 相对路径转绝对路径
        if not os.path.isabs(path):
            return os.path.abspath(path)
        return path
    
    return None


def scan_db_files(project_root):
    """扫描项目中所有 .db 文件"""
    db_files = []
    
    for root, dirs, files in os.walk(project_root):
        # 跳过虚拟环境和其他不相关目录
        dirs[:] = [d for d in dirs if d not in {'.venv', 'venv', '__pycache__', '.git', 'node_modules'}]
        
        for filename in files:
            if filename.endswith('.db'):
                full_path = os.path.join(root, filename)
                try:
                    mtime = os.path.getmtime(full_path)
                    size = os.path.getsize(full_path)
                    db_files.append({
                        'path': full_path,
                        'filename': filename,
                        'mtime': mtime,
                        'size': size,
                        'is_demo_or_clean': 'demo' in filename.lower() or 'clean' in filename.lower()
                    })
                except Exception:
                    continue
    
    return db_files


def identify_real_database(project_root):
    """识别真实数据库"""
    print("=" * 80)
    print("DeepAudit Pro - 真实数据库识别与导出工具")
    print("=" * 80)
    print()
    
    # 步骤 1: 检查环境变量
    print("[步骤 1/4] 检查环境变量配置...")
    env_db_url = get_database_url_from_env()
    
    if env_db_url:
        print(f"  [OK] 找到环境变量: {env_db_url}")
        sqlite_path = parse_sqlite_path(env_db_url)
        if sqlite_path and os.path.exists(sqlite_path):
            print(f"  [OK] 解析路径: {sqlite_path}")
            if 'demo' not in sqlite_path.lower() and 'clean' not in sqlite_path.lower():
                print(f"  [OK] 识别依据: 环境变量指定的非 demo/clean 数据库")
                return sqlite_path, "环境变量 DATABASE_URL/SQLALCHEMY_DATABASE_URI"
            else:
                print(f"  [X] 该路径包含 demo/clean，跳过")
        else:
            print(f"  [X] 路径不存在或无法解析")
    else:
        print("  - 未配置环境变量 DATABASE_URL 或 SQLALCHEMY_DATABASE_URI")
    
    print()
    
    # 步骤 2: 检查配置文件默认值
    print("[步骤 2/4] 检查配置文件默认值...")
    try:
        # 读取 core/settings.py 中的默认配置
        settings_file = os.path.join(project_root, 'core', 'settings.py')
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 查找默认的 DATABASE_URL
                if 'sqlite:///database.db' in content:
                    default_db = os.path.join(project_root, 'database.db')
                    if os.path.exists(default_db):
                        print(f"  [OK] 找到配置默认值: sqlite:///database.db")
                        print(f"  [OK] 对应路径: {default_db}")
                        print(f"  [OK] 识别依据: core/settings.py 中的默认配置")
                        return default_db, "core/settings.py 默认配置 (sqlite:///database.db)"
        print("  - 未找到明确的默认配置")
    except Exception as e:
        print(f"  - 配置文件解析失败: {e}")
    
    print()
    
    # 步骤 3: 扫描所有数据库文件
    print("[步骤 3/4] 扫描项目中所有数据库文件...")
    db_files = scan_db_files(project_root)
    
    if not db_files:
        print("  [X] 未找到任何 .db 文件")
        return None, None
    
    print(f"  [OK] 找到 {len(db_files)} 个数据库文件:")
    print()
    
    for db in db_files:
        rel_path = os.path.relpath(db['path'], project_root)
        time_str = datetime.fromtimestamp(db['mtime']).strftime('%Y-%m-%d %H:%M:%S')
        size_kb = db['size'] / 1024
        marker = "[DEMO/CLEAN]" if db['is_demo_or_clean'] else "[真实库候选]"
        print(f"    {marker} {rel_path}")
        print(f"      修改时间: {time_str}")
        print(f"      文件大小: {size_kb:.2f} KB")
        print()
    
    # 步骤 4: 应用兜底规则
    print("[步骤 4/4] 应用识别规则...")
    
    # 过滤掉 demo/clean 库
    real_candidates = [db for db in db_files if not db['is_demo_or_clean']]
    
    if not real_candidates:
        print("  [X] 所有数据库都是 demo/clean 库，无法导出")
        return None, None
    
    # 按修改时间排序，选择最新的
    real_candidates.sort(key=lambda x: x['mtime'], reverse=True)
    selected = real_candidates[0]
    
    print(f"  [OK] 兜底规则: 选择非 demo/clean 且最近修改的数据库")
    print(f"  [OK] 选中: {os.path.relpath(selected['path'], project_root)}")
    print(f"  [OK] 修改时间: {datetime.fromtimestamp(selected['mtime']).strftime('%Y-%m-%d %H:%M:%S')}")
    
    return selected['path'], "兜底规则（非 demo/clean 且最近修改）"


def verify_sqlite_database(db_path):
    """验证是否为有效的 SQLite 数据库"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        cursor.fetchone()
        conn.close()
        return True
    except Exception:
        return False


def export_database(source_path, project_root):
    """导出数据库到 exports 目录"""
    print()
    print("=" * 80)
    print("开始导出数据库")
    print("=" * 80)
    print()
    
    # 创建 exports 目录
    exports_dir = os.path.join(project_root, 'exports')
    os.makedirs(exports_dir, exist_ok=True)
    print(f"[1/3] 准备导出目录: {os.path.relpath(exports_dir, project_root)}")
    
    # 目标文件路径
    target_path = os.path.join(exports_dir, 'database_real_for_navicat.db')
    
    # 如果目标文件已存在，先备份
    if os.path.exists(target_path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(exports_dir, f'database_real_for_navicat_{timestamp}.db')
        print(f"[2/3] 备份已存在的导出文件...")
        shutil.copy2(target_path, backup_path)
        print(f"  [OK] 备份至: {os.path.relpath(backup_path, project_root)}")
    else:
        print(f"[2/3] 无需备份（目标文件不存在）")
    
    # 复制数据库
    print(f"[3/3] 复制数据库文件...")
    shutil.copy2(source_path, target_path)
    
    # 验证导出的数据库
    if verify_sqlite_database(target_path):
        print(f"  [OK] 数据库复制成功")
        print(f"  [OK] 导出路径: {os.path.relpath(target_path, project_root)}")
        print(f"  [OK] 文件大小: {os.path.getsize(target_path) / 1024:.2f} KB")
        return target_path
    else:
        print(f"  [X] 导出的数据库文件无效")
        return None


def print_navicat_guide(export_path, project_root):
    """打印 Navicat 导入指南"""
    print()
    print("=" * 80)
    print("Navicat 导入指南")
    print("=" * 80)
    print()
    print("请按以下步骤在 Navicat 中打开数据库：")
    print()
    print("1. 打开 Navicat Premium 或 Navicat for SQLite")
    print()
    print("2. 点击左上角「连接」→ 选择「SQLite」")
    print()
    print("3. 在弹出的连接设置窗口中：")
    print("   - 连接名：DeepAudit_Pro_Real")
    print(f"   - 数据库文件：{os.path.abspath(export_path)}")
    print("     （点击「...」浏览按钮选择上述文件）")
    print()
    print("4. 点击「测试连接」确认可以连接")
    print()
    print("5. 点击「确定」保存连接")
    print()
    print("6. 双击左侧连接列表中的「DeepAudit_Pro_Real」即可查看数据")
    print()
    print("=" * 80)
    print()


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent.resolve()
    
    # 识别真实数据库
    real_db_path, reason = identify_real_database(project_root)
    
    if not real_db_path:
        print()
        print("=" * 80)
        print("[X] 无法识别真实数据库")
        print("=" * 80)
        print()
        print("可能的原因：")
        print("  1. 项目中只有 demo/clean 数据库")
        print("  2. 数据库文件不存在")
        print()
        print("建议：")
        print("  1. 检查项目是否已初始化数据库")
        print("  2. 运行应用至少一次以生成数据库")
        print("  3. 确认 DATABASE_URL 环境变量配置")
        return 1
    
    print()
    print("=" * 80)
    print("[OK] 真实数据库识别成功")
    print("=" * 80)
    print()
    print(f"识别依据: {reason}")
    print(f"数据库路径: {os.path.relpath(real_db_path, project_root)}")
    print(f"绝对路径: {real_db_path}")
    print()
    
    # 验证数据库
    if not verify_sqlite_database(real_db_path):
        print("[X] 数据库文件损坏或格式不正确")
        return 1
    
    # 导出数据库
    export_path = export_database(real_db_path, project_root)
    
    if not export_path:
        print()
        print("[X] 数据库导出失败")
        return 1
    
    # 打印使用指南
    print_navicat_guide(export_path, project_root)
    
    print("[OK] 导出完成！")
    print()
    
    return 0


if __name__ == '__main__':
    try:
        exit_code = main()
        try:
            input("\n按任意键退出...")
        except (EOFError, KeyboardInterrupt):
            pass
        exit(exit_code)
    except Exception as e:
        print()
        print("=" * 80)
        print("[X] 发生错误")
        print("=" * 80)
        print()
        print(f"错误信息: {e}")
        print()
        import traceback
        traceback.print_exc()
        try:
            input("\n按任意键退出...")
        except (EOFError, KeyboardInterrupt):
            pass
        exit(1)

