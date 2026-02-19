# -*- coding: utf-8 -*-
"""
Power BI API 路由
提供 CSV/JSON 格式的数据接口供 Power BI 拉取
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timedelta
from flask import Blueprint, Response, jsonify, request
from functools import wraps

from services.pbi_aggregation_service import (
    aggregate_daily_metrics,
    aggregate_action_metrics,
    aggregate_risk_metrics,
    aggregate_department_metrics,
    aggregate_dashboard_summary,
)

bp = Blueprint('pbi_api', __name__, url_prefix='/api/pbi')

# API Key 配置（从环境变量读取，如果未配置则不启用认证）
PBI_API_KEY = os.getenv('PBI_API_KEY', '').strip()


def require_api_key(f):
    """API Key 认证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 如果未配置 API Key，则跳过认证
        if not PBI_API_KEY:
            return f(*args, **kwargs)
        
        # 从请求参数或 Header 获取 API Key
        api_key = request.args.get('api_key') or request.headers.get('X-API-Key')
        
        if not api_key or api_key != PBI_API_KEY:
            return jsonify({
                'ok': False,
                'error': 'Invalid or missing API key',
                'message': 'Please provide a valid API key via ?api_key=xxx or X-API-Key header'
            }), 401
        
        return f(*args, **kwargs)
    return decorated_function


def _get_date_range():
    """从请求参数获取日期范围，默认最近 90 天"""
    end_date = request.args.get('end_date')
    start_date = request.args.get('start_date')
    
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    if not start_date:
        # 默认最近 90 天
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    return start_date, end_date


def _get_format():
    """从请求参数获取输出格式，默认 JSON"""
    return request.args.get('format', 'json').lower()


def _to_csv_response(data: list[dict], filename: str) -> Response:
    """将数据转换为 CSV 响应"""
    if not data:
        return Response("No data available", mimetype='text/csv')
    
    # 创建 CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    
    # 返回响应
    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


def _to_json_response(data: any) -> Response:
    """将数据转换为 JSON 响应"""
    return jsonify({
        'ok': True,
        'data': data,
        'metadata': {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'count': len(data) if isinstance(data, list) else 1,
        }
    })


@bp.route('/metrics/daily', methods=['GET'])
@require_api_key
def get_daily_metrics():
    """
    获取每日指标数据
    
    参数：
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    - format: 输出格式 (json/csv)
    
    示例：
    - /api/pbi/metrics/daily?start_date=2026-01-01&end_date=2026-02-19&format=csv
    - /api/pbi/metrics/daily?format=json
    """
    start_date, end_date = _get_date_range()
    output_format = _get_format()
    
    # 获取数据
    data = aggregate_daily_metrics(start_date, end_date)
    
    # 返回响应
    if output_format == 'csv':
        return _to_csv_response(data, f'daily_metrics_{start_date}_{end_date}.csv')
    else:
        return _to_json_response(data)


@bp.route('/metrics/actions', methods=['GET'])
@require_api_key
def get_action_metrics():
    """
    获取动作指标数据
    
    参数：
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    - format: 输出格式 (json/csv)
    
    示例：
    - /api/pbi/metrics/actions?start_date=2026-01-01&end_date=2026-02-19&format=csv
    """
    start_date, end_date = _get_date_range()
    output_format = _get_format()
    
    # 获取数据
    data = aggregate_action_metrics(start_date, end_date)
    
    # 返回响应
    if output_format == 'csv':
        return _to_csv_response(data, f'action_metrics_{start_date}_{end_date}.csv')
    else:
        return _to_json_response(data)


@bp.route('/metrics/risks', methods=['GET'])
@require_api_key
def get_risk_metrics():
    """
    获取风险指标数据
    
    参数：
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    - format: 输出格式 (json/csv)
    
    示例：
    - /api/pbi/metrics/risks?start_date=2026-01-01&end_date=2026-02-19&format=csv
    """
    start_date, end_date = _get_date_range()
    output_format = _get_format()
    
    # 获取数据
    data = aggregate_risk_metrics(start_date, end_date)
    
    # 返回响应
    if output_format == 'csv':
        return _to_csv_response(data, f'risk_metrics_{start_date}_{end_date}.csv')
    else:
        return _to_json_response(data)


@bp.route('/metrics/departments', methods=['GET'])
@require_api_key
def get_department_metrics():
    """
    获取部门指标数据
    
    参数：
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    - format: 输出格式 (json/csv)
    
    示例：
    - /api/pbi/metrics/departments?format=csv
    """
    start_date, end_date = _get_date_range()
    output_format = _get_format()
    
    # 获取数据
    data = aggregate_department_metrics(start_date, end_date)
    
    # 返回响应
    if output_format == 'csv':
        return _to_csv_response(data, f'department_metrics_{start_date}_{end_date}.csv')
    else:
        return _to_json_response(data)


@bp.route('/dashboard', methods=['GET'])
@require_api_key
def get_dashboard_data():
    """
    获取综合仪表板数据
    
    参数：
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    - format: 输出格式 (json only)
    
    示例：
    - /api/pbi/dashboard?start_date=2026-01-01&end_date=2026-02-19
    """
    start_date, end_date = _get_date_range()
    
    # 获取数据
    data = aggregate_dashboard_summary(start_date, end_date)
    
    # 仪表板数据只支持 JSON 格式
    return jsonify({
        'ok': True,
        'data': data,
        'metadata': {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    })


@bp.route('/health', methods=['GET'])
def health_check():
    """
    健康检查接口
    
    示例：
    - /api/pbi/health
    """
    return jsonify({
        'ok': True,
        'service': 'Power BI API',
        'version': '1.0.0',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

