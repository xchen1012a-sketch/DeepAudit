#!/usr/bin/env python3
"""
同步上传目录中的文件到数据库
用于处理通过 xftp 等工具直接上传到 uploads 目录的文件
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.db import get_conn, insert_invoice
import config

UPLOAD_DIR = PROJECT_ROOT / "uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".pdf"}


def get_existing_filenames():
    """获取数据库中已存在的文件名"""
    with get_conn() as conn:
        cursor = conn.execute("SELECT DISTINCT filename FROM invoices WHERE filename IS NOT NULL AND filename != ''")
        return {row[0] for row in cursor.fetchall()}


def is_allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_EXTENSIONS


def scan_uploaded_files():
    """扫描 uploads 目录中的文件"""
    if not UPLOAD_DIR.exists():
        print(f"错误: uploads 目录不存在: {UPLOAD_DIR}")
        return []
    
    files = []
    for file_path in UPLOAD_DIR.iterdir():
        if file_path.is_file() and is_allowed_file(file_path.name):
            # 跳过种子文件（这些是系统生成的）
            if file_path.name.startswith(("seed_", "ops_seed_", "demo_seed_")):
                continue
            files.append(file_path.name)
    
    return files


def create_invoice_record(filename: str):
    """为文件创建数据库记录"""
    try:
        # 获取文件修改时间作为创建时间
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            created_at = mtime.strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 创建默认记录
        invoice_data = {
            "filename": filename,
            "amount": "",  # 待补录
            "invoice_date": "",  # 待补录
            "applicant": "系统导入",
            "department": "未分配",
            "is_canton_fair": False,
            "hotel_limit": int(getattr(config, "HOTEL_LIMIT_NORMAL", 500)),
            "mode": "manual_import",
            "raw_json": {
                "mode": "manual_import",
                "entry_mode": "manual",
                "source": "xftp_upload",
                "filename": filename,
                "imported_at": created_at,
            },
            "created_at": created_at,
            "risk_level": "MEDIUM",
            "risk_reason": "文件通过 FTP 直接上传，待人工补录信息",
            "currency": "CNY",
            "fx_flag": False,
            "fx_reason": "",
            "manual_rate": None,
            "manual_cny_amount": None,
            "ai_risk_level": "MEDIUM",
            "ai_analysis_reason": "文件通过 FTP 直接上传，待人工补录后进行分析",
            "status": "PENDING",
            "record_state": "DRAFT",  # 待补录状态
            "submitted_by_user_id": None,
            "submitter_department": "未分配",
            "submitter_name": "系统导入",
            "submitter_no": "-",
        }
        
        invoice_id = insert_invoice(invoice_data)
        return invoice_id
    except Exception as e:
        print(f"  错误: 创建记录失败: {e}")
        return None


def main():
    print("=" * 80)
    print("同步上传文件到数据库")
    print("=" * 80)
    print()
    
    # 1. 扫描 uploads 目录
    print("[1/3] 扫描 uploads 目录...")
    uploaded_files = scan_uploaded_files()
    print(f"  找到 {len(uploaded_files)} 个文件")
    print()
    
    if not uploaded_files:
        print("没有需要处理的文件。")
        return
    
    # 2. 获取数据库中已存在的文件名
    print("[2/3] 检查数据库中的现有记录...")
    existing_filenames = get_existing_filenames()
    print(f"  数据库中已有 {len(existing_filenames)} 个文件记录")
    print()
    
    # 3. 找出需要创建记录的文件
    print("[3/3] 创建缺失的记录...")
    missing_files = [f for f in uploaded_files if f not in existing_filenames]
    
    if not missing_files:
        print("  所有文件都已存在于数据库中。")
        return
    
    print(f"  需要创建 {len(missing_files)} 条记录:")
    print()
    
    success_count = 0
    failed_count = 0
    
    for filename in missing_files:
        print(f"  处理: {filename}")
        invoice_id = create_invoice_record(filename)
        if invoice_id:
            print(f"    [OK] 成功创建记录 (ID: {invoice_id})")
            success_count += 1
        else:
            print(f"    [失败] 创建记录失败")
            failed_count += 1
    
    print()
    print("=" * 80)
    print("同步完成")
    print("=" * 80)
    print(f"成功: {success_count} 条")
    print(f"失败: {failed_count} 条")
    print()
    print("提示: 这些文件现在会显示在页面上，但需要人工补录金额和日期等信息。")
    print("      请在页面上找到这些文件，点击「查看详情」进行补录。")


if __name__ == "__main__":
    main()

