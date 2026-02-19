# -*- coding: utf-8 -*-
"""
发票数据生成脚本
生成 50-100 条发票记录，覆盖多种场景
"""
import os
import sys
import io
import sqlite3
import random
import json
from datetime import datetime, timedelta
from pathlib import Path

# 设置 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 供应商列表
SUPPLIERS = [
    "深圳市腾讯科技有限公司",
    "阿里巴巴（中国）有限公司",
    "北京字节跳动科技有限公司",
    "华为技术有限公司",
    "上海美团科技有限公司",
    "广州唯品会信息科技有限公司",
    "杭州网易科技有限公司",
    "北京京东世纪贸易有限公司",
    "深圳市大疆创新科技有限公司",
    "小米科技有限责任公司",
    "百度在线网络技术（北京）有限公司",
    "携程计算机技术（上海）有限公司",
    "上海拼多多网络科技有限公司",
    "北京快手科技有限公司",
    "深圳顺丰速运有限公司",
]

# 发票类型
INVOICE_TYPES = [
    "增值税专用发票",
    "增值税普通发票",
    "电子发票",
]

# 部门列表（从数据库读取）
DEPARTMENTS = []

# 用户列表（从数据库读取）
USERS = []

# 发票项目类型
INVOICE_ITEMS = [
    ("办公用品", 100, 5000),
    ("差旅费", 500, 10000),
    ("会议费", 1000, 20000),
    ("培训费", 2000, 30000),
    ("咨询服务费", 5000, 100000),
    ("软件服务费", 10000, 200000),
    ("设备采购", 20000, 500000),
    ("市场推广费", 5000, 100000),
    ("招待费", 200, 5000),
    ("酒店住宿费", 300, 3000),
]

# 风险等级分布：60% LOW, 30% MEDIUM, 10% HIGH
RISK_LEVELS = ["LOW"] * 60 + ["MEDIUM"] * 30 + ["HIGH"] * 10

# 状态分布
STATUSES = [
    "UPLOADED",
    "OCR_COMPLETED", 
    "AI_AUDITED",
    "RISK_ASSESSED",
    "APPROVAL_PENDING",
    "APPROVED",
    "REJECTED",
    "EXECUTED",
]

# 验真状态
VERIFY_STATUSES = ["SUCCESS", "FAILED", "PENDING", None]


def get_db_connection():
    """获取数据库连接"""
    db_path = os.path.join(PROJECT_ROOT, 'database.db')
    return sqlite3.connect(db_path)


def load_departments_and_users():
    """加载部门和用户数据"""
    global DEPARTMENTS, USERS
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 加载部门
    cursor.execute("SELECT id, name FROM departments")
    DEPARTMENTS = cursor.fetchall()
    
    # 加载用户
    cursor.execute("SELECT id, username, employee_name, department FROM users")
    USERS = cursor.fetchall()
    
    conn.close()
    
    if not DEPARTMENTS:
        print("[警告] 未找到部门数据，将使用默认部门")
        DEPARTMENTS = [(1, "财务部"), (2, "市场部"), (3, "技术部"), (4, "行政部")]
    
    if not USERS:
        print("[警告] 未找到用户数据，将使用默认用户")
        USERS = [(1, "admin01", "系统管理员", "系统管理部")]


def generate_invoice_no():
    """生成发票号码"""
    # 格式：省份代码(2位) + 年份(4位) + 月份(2位) + 流水号(8位)
    province_codes = ["01", "02", "03", "04", "05", "11", "12", "31", "44", "50"]
    province = random.choice(province_codes)
    year = random.randint(2025, 2026)
    month = random.randint(1, 12)
    serial = random.randint(10000000, 99999999)
    return f"{province}{year}{month:02d}{serial}"


def generate_reference_no():
    """生成参考编号"""
    return f"INV-{datetime.now().strftime('%Y%m')}-{random.randint(1000, 9999)}"


def generate_invoice_date(days_ago_range=(0, 180)):
    """生成发票日期（最近 6 个月）"""
    days_ago = random.randint(*days_ago_range)
    invoice_date = datetime.now() - timedelta(days=days_ago)
    
    # 避免周末（工作日概率更高）
    if invoice_date.weekday() >= 5 and random.random() < 0.7:
        # 70% 概率调整到工作日
        invoice_date -= timedelta(days=invoice_date.weekday() - 4)
    
    return invoice_date.strftime('%Y-%m-%d')


def generate_amount():
    """生成金额（对数正态分布，小额多，大额少）"""
    # 使用对数正态分布
    import math
    mu = 7.5  # 对数均值
    sigma = 1.5  # 对数标准差
    amount = math.exp(random.gauss(mu, sigma))
    
    # 限制范围
    amount = max(100, min(500000, amount))
    
    # 四舍五入到整数
    return round(amount, 2)


def calculate_tax(amount, rate=0.13):
    """计算税额"""
    return round(amount * rate, 2)


def generate_risk_reason(risk_level, amount):
    """生成风险原因"""
    if risk_level == "HIGH":
        reasons = [
            "金额超过审批阈值",
            "供应商存在风险记录",
            "发票信息与合同不符",
            "重复报销风险",
            "异常时间段开票",
        ]
    elif risk_level == "MEDIUM":
        reasons = [
            "金额较大需要复核",
            "首次合作供应商",
            "跨部门报销",
            "发票信息不完整",
        ]
    else:
        reasons = [
            "常规发票",
            "金额在正常范围内",
            "供应商信誉良好",
        ]
    
    return random.choice(reasons)


def generate_ai_analysis(risk_level):
    """生成 AI 分析结果"""
    if risk_level == "HIGH":
        analyses = [
            "检测到金额异常，建议人工复核",
            "供应商风险评分较低，建议谨慎处理",
            "发票信息存在疑点，需要进一步核实",
        ]
    elif risk_level == "MEDIUM":
        analyses = [
            "发票信息基本正常，建议常规审批",
            "金额在合理范围内，无明显异常",
        ]
    else:
        analyses = [
            "发票信息完整，无风险",
            "常规业务发票，可正常处理",
        ]
    
    return random.choice(analyses)


def generate_raw_json(invoice_no, amount, tax_amount, supplier, item_name):
    """生成原始 OCR JSON 数据"""
    return json.dumps({
        "invoice_no": invoice_no,
        "invoice_code": f"0{random.randint(100000000, 999999999)}",
        "amount": str(amount),
        "tax_amount": str(tax_amount),
        "total_amount": str(amount + tax_amount),
        "seller_name": supplier,
        "buyer_name": "深圳市某某科技有限公司",
        "item_name": item_name,
        "ocr_confidence": round(random.uniform(0.85, 0.99), 2),
    }, ensure_ascii=False)


def generate_invoices(count=80):
    """生成发票数据"""
    print("=" * 80)
    print("发票数据生成脚本")
    print("=" * 80)
    print()
    
    # 加载部门和用户
    print("[1/4] 加载部门和用户数据...")
    load_departments_and_users()
    print(f"  [OK] 加载了 {len(DEPARTMENTS)} 个部门，{len(USERS)} 个用户")
    print()
    
    # 连接数据库
    print("[2/4] 连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查现有发票数量
    cursor.execute("SELECT COUNT(*) FROM invoices")
    existing_count = cursor.fetchone()[0]
    print(f"  [OK] 当前发票数量: {existing_count} 条")
    print()
    
    # 生成发票
    print(f"[3/4] 生成 {count} 条发票数据...")
    invoices = []
    
    for i in range(count):
        # 选择发票项目
        item_name, min_amount, max_amount = random.choice(INVOICE_ITEMS)
        
        # 生成基本信息
        invoice_no = generate_invoice_no()
        invoice_date = generate_invoice_date()
        amount = generate_amount()
        tax_amount = calculate_tax(amount)
        supplier = random.choice(SUPPLIERS)
        
        # 选择部门和用户
        dept_id, dept_name = random.choice(DEPARTMENTS)
        user_id, username, employee_name, user_dept = random.choice(USERS)
        
        # 风险等级
        risk_level = random.choice(RISK_LEVELS)
        ai_risk_level = risk_level  # AI 评估结果与实际风险一致
        
        # 状态（80% 已完成流程，20% 进行中）
        if random.random() < 0.8:
            status = random.choice(["APPROVED", "EXECUTED", "CLOSED"])
        else:
            status = random.choice(["UPLOADED", "OCR_COMPLETED", "AI_AUDITED", "APPROVAL_PENDING"])
        
        # 验真状态（90% 成功）
        verify_status = "SUCCESS" if random.random() < 0.9 else random.choice(["FAILED", "PENDING"])
        
        # 审批阶段（NOT NULL 字段，必须有值）
        if status in ["APPROVED", "EXECUTED", "CLOSED"]:
            approval_stage = "L2"
            approval_status = "APPROVED"
        elif status == "APPROVAL_PENDING":
            approval_stage = random.choice(["L1", "L2"])
            approval_status = "PENDING"
        else:
            approval_stage = "NONE"  # 默认值
            approval_status = "NONE"  # 默认值
        
        # 生成记录
        invoice = {
            "filename": f"invoice_{invoice_no}.pdf",
            "amount": str(amount),
            "invoice_date": invoice_date,
            "is_canton_fair": 0,
            "hotel_limit": 500,
            "mode": "normal",
            "raw_json": generate_raw_json(invoice_no, amount, tax_amount, supplier, item_name),
            "created_at": (datetime.now() - timedelta(days=random.randint(0, 180))).strftime('%Y-%m-%d %H:%M:%S'),
            "risk_level": risk_level,
            "risk_reason": generate_risk_reason(risk_level, amount),
            "currency": "CNY",
            "fx_flag": 0,
            "fx_reason": None,
            "manual_rate": None,
            "manual_cny_amount": None,
            "ai_risk_level": ai_risk_level,
            "ai_analysis_reason": generate_ai_analysis(ai_risk_level),
            "status": status,
            "applicant": employee_name,
            "department": dept_name,
            "submitted_by_user_id": user_id,
            "submitter_department": user_dept,
            "submitter_name": employee_name,
            "submitter_no": f"EMP{user_id:03d}",
            "reference_no": generate_reference_no(),
            "source": "WEB",
            "verify_status": verify_status,
            "verify_message": "验真成功" if verify_status == "SUCCESS" else "验真失败",
            "verify_checked_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S') if verify_status else None,
            "verify_count": 1 if verify_status else 0,
            "verify_provider": "GD_TAX" if verify_status else None,
            "verify_request_id": f"req_{uuid4().hex[:16]}" if verify_status else None,
            "verify_latency_ms": random.randint(200, 1500) if verify_status else None,
            "verify_status_code": 200 if verify_status == "SUCCESS" else 400,
            "verify_raw_payload": None,
            "approval_stage": approval_stage,
            "approval_status": approval_status,
            "first_approver_id": str(random.choice(USERS)[0]) if approval_stage else None,
            "second_approver_id": str(random.choice(USERS)[0]) if approval_stage == "L2" else None,
            "first_approved_at": (datetime.now() - timedelta(days=random.randint(1, 30))).strftime('%Y-%m-%d %H:%M:%S') if status in ["APPROVED", "EXECUTED", "CLOSED"] else None,
            "second_approved_at": (datetime.now() - timedelta(days=random.randint(0, 20))).strftime('%Y-%m-%d %H:%M:%S') if status in ["APPROVED", "EXECUTED", "CLOSED"] and approval_stage == "L2" else None,
            "sla_due_at": (datetime.now() + timedelta(days=random.randint(1, 7))).strftime('%Y-%m-%d %H:%M:%S') if status == "APPROVAL_PENDING" else None,
            "queue_owner_id": None,
            "rule_hit_id": None,
            "rule_explain": None,
            "ai_trace_id": f"trace_{uuid4().hex[:16]}",
            "record_state": "ACTIVE",
        }
        
        invoices.append(invoice)
        
        if (i + 1) % 20 == 0:
            print(f"  进度: {i + 1}/{count}")
    
    print(f"  [OK] 生成完成")
    print()
    
    # 插入数据库
    print("[4/4] 插入数据库...")
    
    insert_sql = """
    INSERT INTO invoices (
        filename, amount, invoice_date, is_canton_fair, hotel_limit, mode, raw_json,
        created_at, risk_level, risk_reason, currency, fx_flag, fx_reason,
        manual_rate, manual_cny_amount, ai_risk_level, ai_analysis_reason,
        status, applicant, department, submitted_by_user_id, submitter_department,
        submitter_name, submitter_no, reference_no, source, verify_status,
        verify_message, verify_checked_at, verify_count, verify_provider,
        verify_request_id, verify_latency_ms, verify_status_code, verify_raw_payload,
        approval_stage, approval_status, first_approver_id, second_approver_id,
        first_approved_at, second_approved_at, sla_due_at, queue_owner_id,
        rule_hit_id, rule_explain, ai_trace_id, record_state
    ) VALUES (
        :filename, :amount, :invoice_date, :is_canton_fair, :hotel_limit, :mode, :raw_json,
        :created_at, :risk_level, :risk_reason, :currency, :fx_flag, :fx_reason,
        :manual_rate, :manual_cny_amount, :ai_risk_level, :ai_analysis_reason,
        :status, :applicant, :department, :submitted_by_user_id, :submitter_department,
        :submitter_name, :submitter_no, :reference_no, :source, :verify_status,
        :verify_message, :verify_checked_at, :verify_count, :verify_provider,
        :verify_request_id, :verify_latency_ms, :verify_status_code, :verify_raw_payload,
        :approval_stage, :approval_status, :first_approver_id, :second_approver_id,
        :first_approved_at, :second_approved_at, :sla_due_at, :queue_owner_id,
        :rule_hit_id, :rule_explain, :ai_trace_id, :record_state
    )
    """
    
    try:
        cursor.executemany(insert_sql, invoices)
        conn.commit()
        print(f"  [OK] 成功插入 {len(invoices)} 条发票数据")
    except Exception as e:
        conn.rollback()
        print(f"  [错误] 插入失败: {e}")
        return False
    finally:
        conn.close()
    
    # 统计信息
    print()
    print("=" * 80)
    print("生成统计")
    print("=" * 80)
    
    # 按风险等级统计
    risk_stats = {}
    for inv in invoices:
        risk_stats[inv['risk_level']] = risk_stats.get(inv['risk_level'], 0) + 1
    
    print("\n风险等级分布:")
    for level, count in sorted(risk_stats.items()):
        print(f"  {level:10} {count:3} 条 ({count/len(invoices)*100:.1f}%)")
    
    # 按状态统计
    status_stats = {}
    for inv in invoices:
        status_stats[inv['status']] = status_stats.get(inv['status'], 0) + 1
    
    print("\n状态分布:")
    for status, count in sorted(status_stats.items()):
        print(f"  {status:20} {count:3} 条 ({count/len(invoices)*100:.1f}%)")
    
    # 金额统计
    amounts = [float(inv['amount']) for inv in invoices]
    print(f"\n金额统计:")
    print(f"  总金额: {sum(amounts):,.2f} 元")
    print(f"  平均金额: {sum(amounts)/len(amounts):,.2f} 元")
    print(f"  最小金额: {min(amounts):,.2f} 元")
    print(f"  最大金额: {max(amounts):,.2f} 元")
    
    print()
    print("=" * 80)
    print("[OK] 发票数据生成完成！")
    print("=" * 80)
    
    return True


def uuid4():
    """生成 UUID"""
    import uuid
    return uuid.uuid4()


if __name__ == '__main__':
    try:
        success = generate_invoices(count=80)
        if success:
            print("\n✓ 脚本执行成功")
        else:
            print("\n✗ 脚本执行失败")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[中断] 用户取消操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[错误] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

