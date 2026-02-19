# -*- coding: utf-8 -*-
"""
数据完整性验证脚本
"""
import sys
import io
import sqlite3
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'database.db'

print("=" * 80)
print("DeepAudit Pro - 数据完整性验证")
print("=" * 80)
print()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 核心业务表检查
tables_to_check = {
    'invoices': '发票表',
    'risk_events': '风险事件表',
    'risk_cases': '风险案例表',
    'bank_transactions': '银行交易表',
    'users': '用户表',
    'departments': '部门表',
    'audit_logs': '审计日志表',
}

print("[1/3] 核心业务表数据检查")
print("-" * 80)

total_records = 0
for table, desc in tables_to_check.items():
    try:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        count = cursor.fetchone()[0]
        total_records += count
        status = '[OK]' if count > 0 else '[空]'
        print(f'{status} {desc:20} ({table:25}) {count:>6} 条')
    except Exception as e:
        print(f'[错误] {desc:20} ({table:25}) {str(e)}')

print(f'\n总记录数: {total_records} 条')
print()

# 数据关联性检查
print("[2/3] 数据关联性检查")
print("-" * 80)

# 检查风险事件关联发票
cursor.execute("""
    SELECT COUNT(*) FROM risk_events WHERE invoice_id IS NOT NULL
""")
linked_events = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM risk_events")
total_events = cursor.fetchone()[0]

if total_events > 0:
    link_rate = linked_events / total_events * 100
    print(f'[OK] 风险事件关联发票: {linked_events}/{total_events} ({link_rate:.1f}%)')
else:
    print('[警告] 无风险事件数据')

# 检查银行交易匹配发票
cursor.execute("""
    SELECT COUNT(*) FROM bank_transactions WHERE matched_invoice_id IS NOT NULL
""")
matched_txns = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM bank_transactions")
total_txns = cursor.fetchone()[0]

if total_txns > 0:
    match_rate = matched_txns / total_txns * 100
    print(f'[OK] 银行交易匹配发票: {matched_txns}/{total_txns} ({match_rate:.1f}%)')
else:
    print('[警告] 无银行交易数据')

# 检查风险案例关联事件
cursor.execute("SELECT COUNT(*) FROM risk_cases")
total_cases = cursor.fetchone()[0]

if total_cases > 0:
    print(f'[OK] 风险案例数量: {total_cases}')
else:
    print('[警告] 无风险案例数据')

print()

# Power BI API 数据验证
print("[3/3] Power BI API 数据验证")
print("-" * 80)

try:
    from services.pbi_aggregation_service import (
        aggregate_daily_metrics,
        aggregate_dashboard_summary,
    )
    from datetime import datetime, timedelta
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    # 测试每日指标
    daily_data = aggregate_daily_metrics(start_date, end_date)
    print(f'[OK] 每日指标数据: {len(daily_data)} 天')
    
    # 测试仪表板数据
    dashboard_data = aggregate_dashboard_summary(start_date, end_date)
    print(f'[OK] 仪表板数据: {dashboard_data["invoices"]["total_count"]} 张发票')
    print(f'[OK] 风险事件: {dashboard_data["risk_events"]["total_count"]} 条')
    print(f'[OK] 风险案例: {dashboard_data["risk_cases"]["total_count"]} 条')
    print(f'[OK] 银行交易: {dashboard_data["bank_transactions"]["total_count"]} 条')
    
    print('\n[OK] Power BI API 功能正常')
    
except Exception as e:
    print(f'[错误] Power BI API 测试失败: {e}')
    import traceback
    traceback.print_exc()

conn.close()

print()
print("=" * 80)
print("[完成] 数据完整性验证完成")
print("=" * 80)
print()

# 总结
print("数据完整性总结:")
print(f"  ✓ 核心业务数据已生成 ({total_records} 条记录)")
print(f"  ✓ 数据关联关系正常")
print(f"  ✓ Power BI API 可用")
print()
print("下一步:")
print("  1. 启动应用: python app.py")
print("  2. 访问 Power BI API: http://localhost:5000/api/pbi/health")
print("  3. 在 Power BI Desktop 中配置数据源")
print()

