# -*- coding: utf-8 -*-
"""
Power BI 数据聚合服务
提供按天、按动作、按风险状态的数据聚合
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from utils.db import get_conn
from utils.pbi_cache import pbi_cache


@pbi_cache.cached('daily_metrics')
def aggregate_daily_metrics(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """
    按天聚合指标
    
    返回字段：
    - date: 日期
    - invoice_count: 发票数量
    - invoice_amount: 发票总金额
    - risk_event_count: 风险事件数量
    - risk_case_count: 风险案例数量
    - bank_txn_count: 银行交易数量
    - bank_txn_amount: 银行交易总金额
    - high_risk_count: 高风险数量
    - medium_risk_count: 中风险数量
    - low_risk_count: 低风险数量
    """
    conn = get_conn()
    cursor = conn.cursor()
    
    # 按天聚合发票数据
    invoice_sql = """
    SELECT 
        DATE(created_at) as date,
        COUNT(*) as invoice_count,
        SUM(CAST(amount AS REAL)) as invoice_amount,
        SUM(CASE WHEN risk_level = 'HIGH' THEN 1 ELSE 0 END) as high_risk_count,
        SUM(CASE WHEN risk_level = 'MEDIUM' THEN 1 ELSE 0 END) as medium_risk_count,
        SUM(CASE WHEN risk_level = 'LOW' THEN 1 ELSE 0 END) as low_risk_count
    FROM invoices
    WHERE DATE(created_at) BETWEEN ? AND ?
    GROUP BY DATE(created_at)
    ORDER BY date
    """
    
    cursor.execute(invoice_sql, (start_date, end_date))
    invoice_data = {row[0]: {
        'date': row[0],
        'invoice_count': row[1],
        'invoice_amount': row[2] or 0,
        'high_risk_count': row[3],
        'medium_risk_count': row[4],
        'low_risk_count': row[5],
    } for row in cursor.fetchall()}
    
    # 按天聚合风险事件数据
    risk_event_sql = """
    SELECT 
        DATE(created_at) as date,
        COUNT(*) as risk_event_count
    FROM risk_events
    WHERE DATE(created_at) BETWEEN ? AND ?
    GROUP BY DATE(created_at)
    """
    
    cursor.execute(risk_event_sql, (start_date, end_date))
    for row in cursor.fetchall():
        date = row[0]
        if date not in invoice_data:
            invoice_data[date] = {'date': date, 'invoice_count': 0, 'invoice_amount': 0,
                                   'high_risk_count': 0, 'medium_risk_count': 0, 'low_risk_count': 0}
        invoice_data[date]['risk_event_count'] = row[1]
    
    # 按天聚合风险案例数据
    risk_case_sql = """
    SELECT 
        DATE(created_at) as date,
        COUNT(*) as risk_case_count
    FROM risk_cases
    WHERE DATE(created_at) BETWEEN ? AND ?
    GROUP BY DATE(created_at)
    """
    
    cursor.execute(risk_case_sql, (start_date, end_date))
    for row in cursor.fetchall():
        date = row[0]
        if date not in invoice_data:
            invoice_data[date] = {'date': date, 'invoice_count': 0, 'invoice_amount': 0,
                                   'high_risk_count': 0, 'medium_risk_count': 0, 'low_risk_count': 0,
                                   'risk_event_count': 0}
        invoice_data[date]['risk_case_count'] = row[1]
    
    # 按天聚合银行交易数据
    bank_txn_sql = """
    SELECT 
        DATE(ts) as date,
        COUNT(*) as bank_txn_count,
        SUM(amount) as bank_txn_amount
    FROM bank_transactions
    WHERE DATE(ts) BETWEEN ? AND ?
    GROUP BY DATE(ts)
    """
    
    cursor.execute(bank_txn_sql, (start_date, end_date))
    for row in cursor.fetchall():
        date = row[0]
        if date not in invoice_data:
            invoice_data[date] = {'date': date, 'invoice_count': 0, 'invoice_amount': 0,
                                   'high_risk_count': 0, 'medium_risk_count': 0, 'low_risk_count': 0,
                                   'risk_event_count': 0, 'risk_case_count': 0}
        invoice_data[date]['bank_txn_count'] = row[1]
        invoice_data[date]['bank_txn_amount'] = row[2] or 0
    
    conn.close()
    
    # 填充缺失字段
    for data in invoice_data.values():
        data.setdefault('risk_event_count', 0)
        data.setdefault('risk_case_count', 0)
        data.setdefault('bank_txn_count', 0)
        data.setdefault('bank_txn_amount', 0)
    
    return sorted(invoice_data.values(), key=lambda x: x['date'])


@pbi_cache.cached('action_metrics')
def aggregate_action_metrics(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """
    按动作聚合指标
    
    返回字段：
    - action_type: 动作类型
    - action_count: 动作次数
    - user_count: 涉及用户数
    - department_count: 涉及部门数
    """
    conn = get_conn()
    cursor = conn.cursor()
    
    # 从审计日志聚合动作数据
    action_sql = """
    SELECT 
        action as action_type,
        COUNT(*) as action_count,
        COUNT(DISTINCT user_id) as user_count,
        COUNT(DISTINCT department) as department_count
    FROM audit_logs
    WHERE DATE(timestamp) BETWEEN ? AND ?
    GROUP BY action
    ORDER BY action_count DESC
    """
    
    cursor.execute(action_sql, (start_date, end_date))
    results = []
    for row in cursor.fetchall():
        results.append({
            'action_type': row[0],
            'action_count': row[1],
            'user_count': row[2],
            'department_count': row[3],
        })
    
    conn.close()
    return results


@pbi_cache.cached('risk_metrics')
def aggregate_risk_metrics(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """
    按风险状态聚合指标
    
    返回字段：
    - risk_level: 风险等级 (HIGH/MEDIUM/LOW)
    - status: 状态
    - count: 数量
    - total_amount: 总金额
    - avg_amount: 平均金额
    """
    conn = get_conn()
    cursor = conn.cursor()
    
    # 按风险等级和状态聚合发票数据
    risk_sql = """
    SELECT 
        risk_level,
        status,
        COUNT(*) as count,
        SUM(CAST(amount AS REAL)) as total_amount,
        AVG(CAST(amount AS REAL)) as avg_amount
    FROM invoices
    WHERE DATE(created_at) BETWEEN ? AND ?
    GROUP BY risk_level, status
    ORDER BY risk_level, status
    """
    
    cursor.execute(risk_sql, (start_date, end_date))
    results = []
    for row in cursor.fetchall():
        results.append({
            'risk_level': row[0],
            'status': row[1],
            'count': row[2],
            'total_amount': row[3] or 0,
            'avg_amount': row[4] or 0,
        })
    
    conn.close()
    return results


@pbi_cache.cached('department_metrics')
def aggregate_department_metrics(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """
    按部门聚合指标
    
    返回字段：
    - department: 部门名称
    - invoice_count: 发票数量
    - invoice_amount: 发票总金额
    - risk_event_count: 风险事件数量
    - high_risk_count: 高风险数量
    """
    conn = get_conn()
    cursor = conn.cursor()
    
    dept_sql = """
    SELECT 
        department,
        COUNT(*) as invoice_count,
        SUM(CAST(amount AS REAL)) as invoice_amount,
        SUM(CASE WHEN risk_level = 'HIGH' THEN 1 ELSE 0 END) as high_risk_count
    FROM invoices
    WHERE DATE(created_at) BETWEEN ? AND ?
    GROUP BY department
    ORDER BY invoice_amount DESC
    """
    
    cursor.execute(dept_sql, (start_date, end_date))
    results = []
    for row in cursor.fetchall():
        results.append({
            'department': row[0],
            'invoice_count': row[1],
            'invoice_amount': row[2] or 0,
            'high_risk_count': row[3],
        })
    
    conn.close()
    return results


@pbi_cache.cached('dashboard_summary')
def aggregate_dashboard_summary(start_date: str, end_date: str) -> dict[str, Any]:
    """
    综合仪表板数据
    
    返回所有关键指标的汇总
    """
    conn = get_conn()
    cursor = conn.cursor()
    
    # 发票统计
    cursor.execute("""
        SELECT 
            COUNT(*) as total_invoices,
            SUM(CAST(amount AS REAL)) as total_amount,
            AVG(CAST(amount AS REAL)) as avg_amount,
            SUM(CASE WHEN risk_level = 'HIGH' THEN 1 ELSE 0 END) as high_risk_count,
            SUM(CASE WHEN risk_level = 'MEDIUM' THEN 1 ELSE 0 END) as medium_risk_count,
            SUM(CASE WHEN risk_level = 'LOW' THEN 1 ELSE 0 END) as low_risk_count,
            SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) as approved_count,
            SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) as rejected_count
        FROM invoices
        WHERE DATE(created_at) BETWEEN ? AND ?
    """, (start_date, end_date))
    
    invoice_stats = cursor.fetchone()
    
    # 风险事件统计
    cursor.execute("""
        SELECT COUNT(*) FROM risk_events
        WHERE DATE(created_at) BETWEEN ? AND ?
    """, (start_date, end_date))
    risk_event_count = cursor.fetchone()[0]
    
    # 风险案例统计
    cursor.execute("""
        SELECT 
            COUNT(*) as total_cases,
            SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) as closed_cases
        FROM risk_cases
        WHERE DATE(created_at) BETWEEN ? AND ?
    """, (start_date, end_date))
    case_stats = cursor.fetchone()
    
    # 银行交易统计
    cursor.execute("""
        SELECT 
            COUNT(*) as total_txns,
            SUM(amount) as total_amount,
            SUM(CASE WHEN matched_invoice_id IS NOT NULL THEN 1 ELSE 0 END) as matched_count
        FROM bank_transactions
        WHERE DATE(ts) BETWEEN ? AND ?
    """, (start_date, end_date))
    bank_stats = cursor.fetchone()
    
    conn.close()
    
    # 计算关闭率
    total_cases = case_stats[0] or 0
    closed_cases = case_stats[1] or 0
    close_rate = (closed_cases / total_cases * 100) if total_cases > 0 else 0
    
    # 计算匹配率
    total_txns = bank_stats[0] or 0
    matched_txns = bank_stats[2] or 0
    match_rate = (matched_txns / total_txns * 100) if total_txns > 0 else 0
    
    return {
        'period': {
            'start_date': start_date,
            'end_date': end_date,
        },
        'invoices': {
            'total_count': invoice_stats[0] or 0,
            'total_amount': invoice_stats[1] or 0,
            'avg_amount': invoice_stats[2] or 0,
            'high_risk_count': invoice_stats[3] or 0,
            'medium_risk_count': invoice_stats[4] or 0,
            'low_risk_count': invoice_stats[5] or 0,
            'approved_count': invoice_stats[6] or 0,
            'rejected_count': invoice_stats[7] or 0,
        },
        'risk_events': {
            'total_count': risk_event_count,
        },
        'risk_cases': {
            'total_count': total_cases,
            'closed_count': closed_cases,
            'close_rate': round(close_rate, 2),
        },
        'bank_transactions': {
            'total_count': total_txns,
            'total_amount': bank_stats[1] or 0,
            'matched_count': matched_txns,
            'match_rate': round(match_rate, 2),
        },
    }

