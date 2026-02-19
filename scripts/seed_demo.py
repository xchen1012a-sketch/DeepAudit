# -*- coding: utf-8 -*-
"""
演示数据生成脚本
仅在 APP_MODE=demo 时运行，向当前 DATABASE_URL 指向的数据库写入演示数据
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    """生成演示数据"""
    # 安全检查：必须在 demo 模式下运行
    app_mode = os.getenv("APP_MODE", "").strip().lower()
    if app_mode != "demo":
        print("[ERROR] seed_demo.py 只能在 APP_MODE=demo 模式下运行")
        print(f"   当前 APP_MODE={app_mode}")
        print("   请使用 scripts\\run_demo.bat 启动演示模式")
        sys.exit(1)
    
    database_url = os.getenv("DATABASE_URL", "sqlite:///database.db")
    print(f"[OK] 演示模式确认，目标数据库：{database_url}")
    
    # 导入数据库模块
    try:
        from core.extensions import db
        from core.app_factory import create_app
        from models import AuditLog, RiskEvent
    except ImportError as e:
        print(f"[ERROR] 导入失败：{e}")
        sys.exit(1)
    
    # 创建 Flask 应用上下文
    app = create_app()
    
    with app.app_context():
        print("\n开始生成演示数据...")
        
        # 1. 生成审计日志（至少 5 条）
        print("\n[1/3] 生成审计日志...")
        try:
            base_time = datetime.now()
            audit_logs = [
                AuditLog(
                    created_at=base_time - timedelta(hours=5),
                    actor_user_id=1,
                    actor_name="DEMO_管理员",
                    action="LOGIN",
                    target_type="USER",
                    target_id="1",
                    client_ip="192.168.1.100",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    request_id="demo-req-001",
                    session_id="demo-session-001",
                    detail="演示用户登录系统"
                ),
                AuditLog(
                    created_at=base_time - timedelta(hours=4),
                    actor_user_id=1,
                    actor_name="DEMO_管理员",
                    action="UPLOAD_INVOICE",
                    target_type="INVOICE",
                    target_id="DEMO-001",
                    client_ip="192.168.1.100",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    request_id="demo-req-002",
                    session_id="demo-session-001",
                    detail="上传发票：DEMO_差旅报销_20260101.pdf"
                ),
                AuditLog(
                    created_at=base_time - timedelta(hours=3),
                    actor_user_id=2,
                    actor_name="DEMO_财务专员",
                    action="APPROVE_INVOICE",
                    target_type="INVOICE",
                    target_id="DEMO-001",
                    client_ip="192.168.1.101",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    request_id="demo-req-003",
                    session_id="demo-session-002",
                    detail="审批通过：DEMO_差旅报销_20260101.pdf"
                ),
                AuditLog(
                    created_at=base_time - timedelta(hours=2),
                    actor_user_id=1,
                    actor_name="DEMO_管理员",
                    action="EXPORT_DATA",
                    target_type="REPORT",
                    target_id="DEMO-REPORT-001",
                    client_ip="192.168.1.100",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    request_id="demo-req-004",
                    session_id="demo-session-001",
                    detail="导出审计报表：2026年1月"
                ),
                AuditLog(
                    created_at=base_time - timedelta(hours=1),
                    actor_user_id=3,
                    actor_name="DEMO_风控专员",
                    action="CREATE_RISK_CASE",
                    target_type="RISK_EVENT",
                    target_id="DEMO-RISK-001",
                    client_ip="192.168.1.102",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    request_id="demo-req-005",
                    session_id="demo-session-003",
                    detail="创建风险案件：DEMO_异常金额检测"
                ),
                AuditLog(
                    created_at=base_time - timedelta(minutes=30),
                    actor_user_id=1,
                    actor_name="DEMO_管理员",
                    action="UPDATE_SETTINGS",
                    target_type="SYSTEM",
                    target_id="SETTINGS",
                    client_ip="192.168.1.100",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    request_id="demo-req-006",
                    session_id="demo-session-001",
                    detail="更新系统配置：风险阈值调整"
                ),
            ]
            
            for log in audit_logs:
                db.session.add(log)
            
            db.session.commit()
            print(f"   [OK] 已生成 {len(audit_logs)} 条审计日志")
        except Exception as e:
            print(f"   [WARNING] 审计日志生成失败：{e}")
            db.session.rollback()
        
        # 2. 生成风险事件（至少 2 条）
        print("\n[2/3] 生成风险事件...")
        try:
            risk_events = [
                RiskEvent(
                    created_at=base_time - timedelta(hours=6),
                    event_type="AMOUNT_ANOMALY",
                    severity="HIGH",
                    status="OPEN",
                    source_type="INVOICE",
                    source_id="DEMO-INV-001",
                    description="DEMO_检测到异常金额：单笔报销金额 ¥15,800 超出部门平均水平 3 倍",
                    risk_score=85.5,
                    assigned_to=3,
                    meta_json='{"amount": 15800, "avg_amount": 5200, "department": "DEMO_销售部"}'
                ),
                RiskEvent(
                    created_at=base_time - timedelta(hours=4),
                    event_type="DUPLICATE_INVOICE",
                    severity="MEDIUM",
                    status="INVESTIGATING",
                    source_type="INVOICE",
                    source_id="DEMO-INV-002",
                    description="DEMO_疑似重复报销：发票号码 03224000000012345678 在系统中已存在",
                    risk_score=72.0,
                    assigned_to=3,
                    meta_json='{"invoice_no": "03224000000012345678", "previous_submission": "2026-01-15"}'
                ),
                RiskEvent(
                    created_at=base_time - timedelta(hours=2),
                    event_type="POLICY_VIOLATION",
                    severity="MEDIUM",
                    status="RESOLVED",
                    source_type="INVOICE",
                    source_id="DEMO-INV-003",
                    description="DEMO_差旅政策违规：住宿费用 ¥1,200/晚 超出标准 ¥800/晚",
                    risk_score=65.0,
                    assigned_to=3,
                    resolved_at=base_time - timedelta(hours=1),
                    resolved_by=3,
                    resolution_note="DEMO_已确认为广交会期间特批，符合政策例外条款",
                    meta_json='{"hotel_cost": 1200, "standard": 800, "location": "广州", "event": "广交会"}'
                ),
            ]
            
            for event in risk_events:
                db.session.add(event)
            
            db.session.commit()
            print(f"   [OK] 已生成 {len(risk_events)} 条风险事件")
        except Exception as e:
            print(f"   [WARNING] 风险事件生成失败：{e}")
            db.session.rollback()
        
        # 3. 生成发票/台账数据（如果表存在）
        print("\n[3/3] 生成发票台账数据...")
        try:
            # 检查 invoices 表是否存在
            from utils.db import get_conn
            with get_conn() as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'"
                )
                if cursor.fetchone():
                    # 插入演示发票数据
                    base_date = datetime.now()
                    invoices_data = [
                        {
                            "reference_no": f"DEMO-{base_date.strftime('%Y%m%d')}-001",
                            "filename": "DEMO_差旅报销_酒店住宿.pdf",
                            "amount": "1200.00",
                            "invoice_date": (base_date - timedelta(days=5)).strftime("%Y-%m-%d"),
                            "applicant": "DEMO_张三",
                            "department": "DEMO_销售部",
                            "status": "APPROVED",
                            "record_state": "LEDGER",
                            "source": "demo",
                            "currency": "CNY",
                            "risk_level": "MEDIUM",
                            "risk_reason": "DEMO_住宿费用略高于标准",
                            "created_at": (base_date - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
                        },
                        {
                            "reference_no": f"DEMO-{base_date.strftime('%Y%m%d')}-002",
                            "filename": "DEMO_办公用品采购.pdf",
                            "amount": "3500.00",
                            "invoice_date": (base_date - timedelta(days=3)).strftime("%Y-%m-%d"),
                            "applicant": "DEMO_李四",
                            "department": "DEMO_行政部",
                            "status": "APPROVED",
                            "record_state": "LEDGER",
                            "source": "demo",
                            "currency": "CNY",
                            "risk_level": "LOW",
                            "risk_reason": "",
                            "created_at": (base_date - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                        },
                        {
                            "reference_no": f"DEMO-{base_date.strftime('%Y%m%d')}-003",
                            "filename": "DEMO_业务招待费.pdf",
                            "amount": "8800.00",
                            "invoice_date": (base_date - timedelta(days=1)).strftime("%Y-%m-%d"),
                            "applicant": "DEMO_王五",
                            "department": "DEMO_销售部",
                            "status": "PENDING",
                            "record_state": "DRAFT",
                            "source": "demo",
                            "currency": "CNY",
                            "risk_level": "HIGH",
                            "risk_reason": "DEMO_金额较大，需要额外审批",
                            "created_at": (base_date - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                        },
                    ]
                    
                    for inv_data in invoices_data:
                        columns = ", ".join(inv_data.keys())
                        placeholders = ", ".join(["?" for _ in inv_data])
                        conn.execute(
                            f"INSERT INTO invoices ({columns}) VALUES ({placeholders})",
                            tuple(inv_data.values())
                        )
                    
                    conn.commit()
                    print(f"   [OK] 已生成 {len(invoices_data)} 条发票台账数据")
                else:
                    print("   [WARNING] invoices 表不存在，跳过")
        except Exception as e:
            print(f"   [WARNING] 发票台账数据生成失败：{e}")
        
        print("\n" + "="*60)
        print("[OK] 演示数据生成完成！")
        print("="*60)
        print(f"数据库位置：{database_url}")
        print("数据统计：")
        print(f"  - 审计日志：6+ 条")
        print(f"  - 风险事件：3 条")
        print(f"  - 发票台账：3 条")
        print("\n现在可以访问系统查看演示数据")

if __name__ == "__main__":
    main()

