# -*- coding: utf-8 -*-
"""
银行交易数据生成脚本
生成 100-200 条银行交易记录，50% 关联发票
"""
import os
import sys
import io
import sqlite3
import random
import math
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

# 设置 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 交易对手方（供应商/客户）
COUNTERPARTIES = [
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
    "中国移动通信集团有限公司",
    "中国电信集团有限公司",
    "国家电网有限公司",
    "中国石油化工集团有限公司",
    "中国建设银行股份有限公司",
]

# 交易备注
MEMO_TEMPLATES = [
    "货款",
    "服务费",
    "咨询费",
    "技术服务费",
    "软件授权费",
    "设备采购款",
    "办公用品采购",
    "差旅费报销",
    "会议费",
    "培训费",
    "市场推广费",
    "广告费",
    "租金",
    "水电费",
    "通讯费",
]

# 匹配原因
MATCH_REASONS = {
    "matched": [
        "金额完全匹配",
        "金额和供应商匹配",
        "发票号匹配",
        "自动匹配成功",
    ],
    "unmatched": [
        "未找到对应发票",
        "金额不匹配",
        "供应商不匹配",
        "待人工核对",
    ],
    "anomaly": [
        "金额异常",
        "交易时间异常",
        "对手方异常",
        "需要进一步核实",
    ]
}


def get_db_connection():
    """获取数据库连接"""
    db_path = os.path.join(PROJECT_ROOT, 'database.db')
    return sqlite3.connect(db_path)


def load_invoices():
    """加载发票数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, invoice_date FROM invoices WHERE status IN ('APPROVED', 'EXECUTED', 'CLOSED')")
    invoices = cursor.fetchall()
    conn.close()
    return invoices


def generate_txn_id():
    """生成交易ID"""
    # 格式：TXN + 日期 + 随机数
    date_str = datetime.now().strftime('%Y%m%d')
    random_str = ''.join([str(random.randint(0, 9)) for _ in range(8)])
    return f"TXN{date_str}{random_str}"


def generate_amount():
    """生成交易金额（对数正态分布）"""
    mu = 8.5  # 对数均值
    sigma = 1.5  # 对数标准差
    amount = math.exp(random.gauss(mu, sigma))
    
    # 限制范围
    amount = max(1000, min(1000000, amount))
    
    # 四舍五入到两位小数
    return round(amount, 2)


def generate_transaction_date(days_ago_range=(0, 180)):
    """生成交易日期（最近 6 个月）"""
    days_ago = random.randint(*days_ago_range)
    txn_date = datetime.now() - timedelta(days=days_ago)
    
    # 避免周末（工作日概率更高）
    if txn_date.weekday() >= 5 and random.random() < 0.8:
        # 80% 概率调整到工作日
        txn_date -= timedelta(days=txn_date.weekday() - 4)
    
    return txn_date.strftime('%Y-%m-%d %H:%M:%S')


def calculate_match_score(matched):
    """计算匹配分数"""
    if matched == "matched":
        return round(random.uniform(0.85, 1.0), 2)
    elif matched == "unmatched":
        return round(random.uniform(0.0, 0.5), 2)
    else:  # anomaly
        return round(random.uniform(0.3, 0.7), 2)


def generate_bank_transactions(count=150):
    """生成银行交易数据"""
    print("=" * 80)
    print("银行交易数据生成脚本")
    print("=" * 80)
    print()
    
    # 加载发票数据
    print("[1/4] 加载发票数据...")
    invoices = load_invoices()
    if not invoices:
        print("  [警告] 未找到已批准的发票数据，将生成独立交易")
        invoices = []
    else:
        print(f"  [OK] 加载了 {len(invoices)} 条已批准发票")
    print()
    
    # 连接数据库
    print("[2/4] 连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查现有交易数量
    cursor.execute("SELECT COUNT(*) FROM bank_transactions")
    existing_count = cursor.fetchone()[0]
    print(f"  [OK] 当前银行交易数量: {existing_count} 条")
    print()
    
    # 生成银行交易
    print(f"[3/4] 生成 {count} 条银行交易数据...")
    transactions = []
    
    # 50% 关联发票（已匹配），30% 未匹配，20% 异常
    matched_count = int(count * 0.5)
    unmatched_count = int(count * 0.3)
    anomaly_count = count - matched_count - unmatched_count
    
    # 生成已匹配交易（关联发票）
    for i in range(matched_count):
        if invoices:
            # 随机选择一张发票
            invoice_id, invoice_amount, invoice_date = random.choice(invoices)
            
            # 金额与发票金额一致或接近
            if random.random() < 0.8:
                amount = float(invoice_amount)
            else:
                # 20% 的情况金额略有差异
                amount = float(invoice_amount) * random.uniform(0.95, 1.05)
            
            matched_invoice_id = invoice_id
            match_status = "matched"
        else:
            amount = generate_amount()
            matched_invoice_id = None
            match_status = "unmatched"
        
        transaction = {
            "txn_id": generate_txn_id(),
            "ts": generate_transaction_date(),
            "amount": amount,
            "counterparty": random.choice(COUNTERPARTIES),
            "memo": random.choice(MEMO_TEMPLATES),
            "imported_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "matched_invoice_id": matched_invoice_id,
            "match_score": calculate_match_score(match_status),
            "match_reason": random.choice(MATCH_REASONS[match_status]),
        }
        
        transactions.append(transaction)
    
    # 生成未匹配交易
    for i in range(unmatched_count):
        transaction = {
            "txn_id": generate_txn_id(),
            "ts": generate_transaction_date(),
            "amount": generate_amount(),
            "counterparty": random.choice(COUNTERPARTIES),
            "memo": random.choice(MEMO_TEMPLATES),
            "imported_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "matched_invoice_id": None,
            "match_score": calculate_match_score("unmatched"),
            "match_reason": random.choice(MATCH_REASONS["unmatched"]),
        }
        
        transactions.append(transaction)
    
    # 生成异常交易
    for i in range(anomaly_count):
        transaction = {
            "txn_id": generate_txn_id(),
            "ts": generate_transaction_date(),
            "amount": generate_amount(),
            "counterparty": random.choice(COUNTERPARTIES),
            "memo": random.choice(MEMO_TEMPLATES),
            "imported_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "matched_invoice_id": None,
            "match_score": calculate_match_score("anomaly"),
            "match_reason": random.choice(MATCH_REASONS["anomaly"]),
        }
        
        transactions.append(transaction)
    
    # 打乱顺序
    random.shuffle(transactions)
    
    print(f"  [OK] 生成完成 (已匹配: {matched_count}, 未匹配: {unmatched_count}, 异常: {anomaly_count})")
    print()
    
    # 插入数据库
    print("[4/4] 插入数据库...")
    
    insert_sql = """
    INSERT INTO bank_transactions (
        txn_id, ts, amount, counterparty, memo, imported_at,
        matched_invoice_id, match_score, match_reason
    ) VALUES (
        :txn_id, :ts, :amount, :counterparty, :memo, :imported_at,
        :matched_invoice_id, :match_score, :match_reason
    )
    """
    
    try:
        cursor.executemany(insert_sql, transactions)
        conn.commit()
        print(f"  [OK] 成功插入 {len(transactions)} 条银行交易数据")
    except Exception as e:
        conn.rollback()
        print(f"  [错误] 插入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()
    
    # 统计信息
    print()
    print("=" * 80)
    print("生成统计")
    print("=" * 80)
    
    # 匹配状态统计
    matched = sum(1 for t in transactions if t['matched_invoice_id'] is not None)
    unmatched = sum(1 for t in transactions if t['matched_invoice_id'] is None and t['match_score'] < 0.5)
    anomaly = len(transactions) - matched - unmatched
    
    print("\n匹配状态分布:")
    print(f"  已匹配: {matched} 条 ({matched/len(transactions)*100:.1f}%)")
    print(f"  未匹配: {unmatched} 条 ({unmatched/len(transactions)*100:.1f}%)")
    print(f"  异常: {anomaly} 条 ({anomaly/len(transactions)*100:.1f}%)")
    
    # 金额统计
    amounts = [t['amount'] for t in transactions]
    print(f"\n金额统计:")
    print(f"  总金额: {sum(amounts):,.2f} 元")
    print(f"  平均金额: {sum(amounts)/len(amounts):,.2f} 元")
    print(f"  最小金额: {min(amounts):,.2f} 元")
    print(f"  最大金额: {max(amounts):,.2f} 元")
    
    # 匹配分数统计
    scores = [t['match_score'] for t in transactions]
    print(f"\n匹配分数统计:")
    print(f"  平均分数: {sum(scores)/len(scores):.2f}")
    print(f"  最低分数: {min(scores):.2f}")
    print(f"  最高分数: {max(scores):.2f}")
    
    # 对手方统计（Top 5）
    counterparty_stats = {}
    for t in transactions:
        counterparty_stats[t['counterparty']] = counterparty_stats.get(t['counterparty'], 0) + 1
    
    print("\n对手方分布 (Top 5):")
    for counterparty, count in sorted(counterparty_stats.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {counterparty[:30]:30} {count:3} 条 ({count/len(transactions)*100:.1f}%)")
    
    print()
    print("=" * 80)
    print("[OK] 银行交易数据生成完成！")
    print("=" * 80)
    
    return True


if __name__ == '__main__':
    try:
        success = generate_bank_transactions(count=150)
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

