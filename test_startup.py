#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试系统启动脚本
"""
import sys
import os
from pathlib import Path

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def test_startup():
    """测试系统启动的各个环节"""
    print("=" * 60)
    print("DeepAudit Pro 启动测试")
    print("=" * 60)
    print()
    
    # 1. 检查Python版本
    print("[1/6] 检查Python版本...")
    py_version = sys.version_info
    if py_version.major < 3 or (py_version.major == 3 and py_version.minor < 8):
        print(f"[X] Python版本过低: {sys.version}")
        print("   需要Python 3.8或更高版本")
        return False
    print(f"[OK] Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    print()
    
    # 2. 检查依赖包
    print("[2/6] 检查依赖包...")
    required_packages = [
        'flask',
        'flask_sqlalchemy',
        'flask_login',
        'flask_migrate',
        'werkzeug',
        'sqlalchemy',
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"[OK] {package}")
        except ImportError:
            print(f"[X] {package} (未安装)")
            missing_packages.append(package)
    
    if missing_packages:
        print()
        print(f"缺少 {len(missing_packages)} 个依赖包，请运行:")
        print("pip install -r requirements.txt")
        return False
    print()
    
    # 3. 检查必要文件
    print("[3/6] 检查必要文件...")
    required_files = [
        'app.py',
        'config.py',
        'requirements.txt',
        'core/app_factory.py',
        'core/settings.py',
    ]
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"[OK] {file_path}")
        else:
            print(f"[X] {file_path} (不存在)")
            return False
    print()
    
    # 4. 检查必要目录
    print("[4/6] 检查必要目录...")
    required_dirs = ['uploads', 'instance', 'static', 'templates']
    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            print(f"[!] {dir_path} (不存在，将自动创建)")
            Path(dir_path).mkdir(exist_ok=True)
        print(f"[OK] {dir_path}")
    print()
    
    # 5. 检查数据库
    print("[5/6] 检查数据库...")
    if Path('database.db').exists():
        print("[OK] database.db 存在")
    else:
        print("[!] database.db 不存在")
        print("  首次启动时会自动创建")
    print()
    
    # 6. 测试应用创建
    print("[6/6] 测试应用创建...")
    try:
        # 设置环境变量
        os.environ['DEV_ALLOW_INSECURE'] = '1'
        os.environ['FLASK_DEBUG'] = '0'
        
        from core.app_factory import create_app
        app = create_app()
        
        if app:
            print("[OK] Flask应用创建成功")
            print(f"[OK] 应用名称: {app.name}")
            print(f"[OK] 调试模式: {app.debug}")
            print()
            
            # 测试路由
            print("已注册的蓝图:")
            for blueprint_name in app.blueprints:
                print(f"  - {blueprint_name}")
            print()
            
            return True
        else:
            print("[X] Flask应用创建失败")
            return False
            
    except Exception as e:
        print(f"[X] 应用创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print()
    success = test_startup()
    print()
    print("=" * 60)
    if success:
        print("[OK] 所有测试通过！系统可以正常启动")
        print()
        print("运行以下命令启动系统:")
        print("  Windows: 启动系统.bat")
        print("  或直接: python app.py")
        print()
        print("访问地址: http://127.0.0.1:5000")
        print("默认账号: admin01 / admin123")
    else:
        print("[X] 测试失败，请修复上述问题后再启动")
    print("=" * 60)
    print()
    
    sys.exit(0 if success else 1)

