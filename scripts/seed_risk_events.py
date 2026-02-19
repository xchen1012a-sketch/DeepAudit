# -*- coding: utf-8 -*-
"""
风险事件数据生成脚本
生成 30-50 条风险事件，70% 关联发票
"""
import os
import sys
import io
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

# 设置 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 风险类型和描述
RISK_TYPES = [
    ("AMOUNT_ANOMALY", "金额异常", [
        "发票金额超过部门预算",
        "单笔金额异常偏高",
        "金额与历史平均值偏差较大",
        "连续大额支出异常",
    ]),
    ("DUPLICATE_INVOICE", "发票重复", [
        "检测到重复发票号",
        "相同供应商相同金额重复报销",
        "疑似重复报销",
    ]),
    ("SUPPLIER_RISK", "供应商风险", [
        "供应商信用评级较低",
        "供应商存在历史违约记录",
        "新供应商首次合作",
        "供应商资质即将过期",
    ]),
    ("COMPLIANCE_RISK", "合规风险", [
        "发票信息不完整",
        "缺少必要的审批流程",
        "超出审批权限",
        "违反采购政策",
        "发票税率异常",
    ]),
    ("TIME_ANOMALY", "时间异常", [
        "非工作时间开票",
        "开票日期与业务发生日期不符",
        "发票过期",
    ]),
    ("CATEGORY_MISMATCH", "类别不匹配", [
        "费用类别与部门业务不符",
        "报销类别选择错误",
    ]),
]

# 风险等级分布：60% LOW, 30% MEDIUM, 10% HIGH
RISK_LEVELS = ["LOW"] * 60 + ["MEDIUM"] * 30 + ["HIGH"] * 10

# 风险分数范围
RISK_SCORE_RANGES = {
    "LOW": (0, 40),
    "MEDIUM": (41, 70),
    "HIGH": (71, 100),
}


def get_db_connection():
    """获取数据库连接"""
    db_path = os.path.join(PROJECT_ROOT, 'database.db')
    return sqlite3.connect(db_path)


def load_invoices():
    """加载发票数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, risk_level, created_at FROM invoices")
    invoices = cursor.fetchall()
    conn.close()
    return invoices


def generate_risk_score(risk_level):
    """根据风险等级生成风险分数"""
    min_score, max_score = RISK_SCORE_RANGES[risk_level]
    return random.randint(min_score, max_score)


def generate_rule_summary(risk_type, risk_level, description):
    """生成规则摘要"""
    return f"[{risk_type}] {description} (风险等级: {risk_level})"


def generate_risk_events(count=40):
    """生成风险事件数据"""
    print("=" * 80)
    print("风险事件数据生成脚本")
    print("=" * 80)
    print()
    
    # 加载发票数据
    print("[1/4] 加载发票数据...")
    invoices = load_invoices()
    if not invoices:
        print("  [错误] 未找到发票数据，请先运行 seed_invoices.py")
        return False
    print(f"  [OK] 加载了 {len(invoices)} 条发票")
    print()
    
    # 连接数据库
    print("[2/4] 连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查现有风险事件数量
    cursor.execute("SELECT COUNT(*) FROM risk_events")
    existing_count = cursor.fetchone()[0]
    print(f"  [OK] 当前风险事件数量: {existing_count} 条")
    print()
    
    # 生成风险事件
    print(f"[3/4] 生成 {count} 条风险事件数据...")
    risk_events = []
    
    # 70% 关联发票，30% 独立事件
    linked_count = int(count * 0.7)
    independent_count = count - linked_count
    
    # 生成关联发票的风险事件
    for i in range(linked_count):
        # 随机选择一张发票
        invoice_id, amount, invoice_risk_level, invoice_created_at = random.choice(invoices)
        
        # 选择风险类型
        risk_type, risk_type_name, descriptions = random.choice(RISK_TYPES)
        description = random.choice(descriptions)
        
        # 风险等级（优先使用发票的风险等级）
        if random.random() < 0.8:
            risk_level = invoice_risk_level
        else:
            risk_level = random.choice(RISK_LEVELS)
        
        # 生成风险事件
        risk_event = {
            "invoice_id": invoice_id,
            "risk_level": risk_level,
            "risk_score": generate_risk_score(risk_level),
            "rule_summary": generate_rule_summary(risk_type, risk_level, description),
            "trace_id": f"trace_{uuid4().hex[:16]}",
            "created_at": (datetime.now() - timedelta(days=random.randint(0, 90))).strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        risk_events.append(risk_event)
    
    # 生成独立风险事件（不关联发票）
    for i in range(independent_count):
        # 选择风险类型
        risk_type, risk_type_name, descriptions = random.choice(RISK_TYPES)
        description = random.choice(descriptions)
        
        # 风险等级
        risk_level = random.choice(RISK_LEVELS)
        
        # 生成风险事件
        risk_event = {
            "invoice_id": None,
            "risk_level": risk_level,
            "risk_score": generate_risk_score(risk_level),
            "rule_summary": generate_rule_summary(risk_type, risk_level, description),
            "trace_id": f"trace_{uuid4().hex[:16]}",
            "created_at": (datetime.now() - timedelta(days=random.randint(0, 90))).strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        risk_events.append(risk_event)
    
    print(f"  [OK] 生成完成 (关联发票: {linked_count}, 独立事件: {independent_count})")
    print()
    
    # 插入数据库
    print("[4/4] 插入数据库...")
    
    insert_sql = """
    INSERT INTO risk_events (
        invoice_id, risk_level, risk_score, rule_summary, trace_id, created_at
    ) VALUES (
        :invoice_id, :risk_level, :risk_score, :rule_summary, :trace_id, :created_at
    )
    """
    
    try:
        cursor.executemany(insert_sql, risk_events)
        conn.commit()
        print(f"  [OK] 成功插入 {len(risk_events)} 条风险事件数据")
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
    for event in risk_events:
        risk_stats[event['risk_level']] = risk_stats.get(event['risk_level'], 0) + 1
    
    print("\n风险等级分布:")
    for level, count in sorted(risk_stats.items()):
        print(f"  {level:10} {count:3} 条 ({count/len(risk_events)*100:.1f}%)")
    
    # 按风险类型统计
    type_stats = {}
    for event in risk_events:
        risk_type = event['rule_summary'].split(']')[0].replace('[', '')
        type_stats[risk_type] = type_stats.get(risk_type, 0) + 1
    
    print("\n风险类型分布:")
    for risk_type, count in sorted(type_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {risk_type:20} {count:3} 条 ({count/len(risk_events)*100:.1f}%)")
    
    # 风险分数统计
    scores = [event['risk_score'] for event in risk_events]
    print(f"\n风险分数统计:")
    print(f"  平均分数: {sum(scores)/len(scores):.1f}")
    print(f"  最低分数: {min(scores)}")
    print(f"  最高分数: {max(scores)}")
    
    # 关联统计
    linked = sum(1 for e in risk_events if e['invoice_id'] is not None)
    print(f"\n关联统计:")
    print(f"  关联发票: {linked} 条 ({linked/len(risk_events)*100:.1f}%)")
    print(f"  独立事件: {len(risk_events) - linked} 条 ({(len(risk_events) - linked)/len(risk_events)*100:.1f}%)")
    
    print()
    print("=" * 80)
    print("[OK] 风险事件数据生成完成！")
    print("=" * 80)
    
    return True


if __name__ == '__main__':
    try:
        success = generate_risk_events(count=40)
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

