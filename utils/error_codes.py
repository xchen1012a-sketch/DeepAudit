# -*- coding: utf-8 -*-
"""
企业级错误码中文映射系统
保持内部错误码不变，仅提供中文映射显示
"""

from typing import Any

# 错误码分类
ERROR_CATEGORY_AUTH = "AUTH"  # 认证授权
ERROR_CATEGORY_VALIDATION = "VALIDATION"  # 数据验证
ERROR_CATEGORY_BUSINESS = "BUSINESS"  # 业务逻辑
ERROR_CATEGORY_SYSTEM = "SYSTEM"  # 系统错误
ERROR_CATEGORY_PERMISSION = "PERMISSION"  # 权限错误

# 错误码中文映射表
ERROR_CODE_MAP: dict[str, dict[str, Any]] = {
    # 认证授权错误 (401)
    "unauthorized": {
        "code": "AUTH_001",
        "message_cn": "未授权访问",
        "description_cn": "您尚未登录或登录已过期，请重新登录",
        "category": ERROR_CATEGORY_AUTH,
        "http_status": 401,
    },
    "password_change_required": {
        "code": "AUTH_002",
        "message_cn": "需要修改密码",
        "description_cn": "您的密码需要修改后才能继续使用系统",
        "category": ERROR_CATEGORY_AUTH,
        "http_status": 403,
    },
    "csrf_invalid": {
        "code": "AUTH_003",
        "message_cn": "CSRF令牌无效",
        "description_cn": "请求的安全令牌验证失败，请刷新页面后重试",
        "category": ERROR_CATEGORY_AUTH,
        "http_status": 403,
    },
    # 权限错误 (403)
    "forbidden": {
        "code": "PERM_001",
        "message_cn": "无权限访问",
        "description_cn": "您没有权限访问该资源",
        "category": ERROR_CATEGORY_PERMISSION,
        "http_status": 403,
    },
    "unauthorized_access": {
        "code": "PERM_002",
        "message_cn": "无权限访问该资源",
        "description_cn": "您没有权限访问该资源，请联系管理员",
        "category": ERROR_CATEGORY_PERMISSION,
        "http_status": 403,
    },
    "data_scope_forbidden": {
        "code": "PERM_003",
        "message_cn": "数据范围越权",
        "description_cn": "您无权访问该数据范围的数据",
        "category": ERROR_CATEGORY_PERMISSION,
        "http_status": 403,
    },
    # 数据验证错误 (400)
    "validation_error": {
        "code": "VAL_001",
        "message_cn": "数据验证失败",
        "description_cn": "提交的数据不符合要求，请检查后重试",
        "category": ERROR_CATEGORY_VALIDATION,
        "http_status": 400,
    },
    "missing_required_field": {
        "code": "VAL_002",
        "message_cn": "缺少必填字段",
        "description_cn": "请填写所有必填字段",
        "category": ERROR_CATEGORY_VALIDATION,
        "http_status": 400,
    },
    "invalid_format": {
        "code": "VAL_003",
        "message_cn": "数据格式错误",
        "description_cn": "提交的数据格式不正确",
        "category": ERROR_CATEGORY_VALIDATION,
        "http_status": 400,
    },
    "missing_reason": {
        "code": "VAL_004",
        "message_cn": "缺少变更原因",
        "description_cn": "必须填写变更原因（审计要求）",
        "category": ERROR_CATEGORY_VALIDATION,
        "http_status": 400,
    },
    "rule_validation_error": {
        "code": "VAL_005",
        "message_cn": "规则参数校验失败",
        "description_cn": "阈值或参数不符合规则类型要求",
        "category": ERROR_CATEGORY_VALIDATION,
        "http_status": 422,
    },
    # 业务逻辑错误 (400/409)
    "not_found": {
        "code": "BIZ_001",
        "message_cn": "资源不存在",
        "description_cn": "请求的资源不存在或已被删除",
        "category": ERROR_CATEGORY_BUSINESS,
        "http_status": 404,
    },
    "duplicate_entry": {
        "code": "BIZ_002",
        "message_cn": "数据已存在",
        "description_cn": "该数据已存在，无法重复创建",
        "category": ERROR_CATEGORY_BUSINESS,
        "http_status": 409,
    },
    "invalid_state": {
        "code": "BIZ_003",
        "message_cn": "状态不允许",
        "description_cn": "当前状态不允许执行该操作",
        "category": ERROR_CATEGORY_BUSINESS,
        "http_status": 400,
    },
    "workflow_error": {
        "code": "BIZ_004",
        "message_cn": "流程错误",
        "description_cn": "流程操作失败，请检查流程状态",
        "category": ERROR_CATEGORY_BUSINESS,
        "http_status": 400,
    },
    # 系统错误 (500)
    "internal_error": {
        "code": "SYS_001",
        "message_cn": "系统内部错误",
        "description_cn": "系统处理请求时发生错误，请稍后重试",
        "category": ERROR_CATEGORY_SYSTEM,
        "http_status": 500,
    },
    "service_unavailable": {
        "code": "SYS_002",
        "message_cn": "服务暂时不可用",
        "description_cn": "服务暂时不可用，请稍后重试",
        "category": ERROR_CATEGORY_SYSTEM,
        "http_status": 503,
    },
    "database_error": {
        "code": "SYS_003",
        "message_cn": "数据库错误",
        "description_cn": "数据库操作失败，请稍后重试",
        "category": ERROR_CATEGORY_SYSTEM,
        "http_status": 500,
    },
}


def _normalize_error_key(value: Any) -> str:
    """标准化错误码key"""
    return str(value or "").strip().lower()


def get_error_info(error_key: str, default_message_cn: str | None = None) -> dict[str, Any]:
    """
    获取错误信息（中文）
    
    Args:
        error_key: 错误码key（如 "unauthorized", "forbidden"）
        default_message_cn: 默认中文消息（如果找不到映射）
    
    Returns:
        包含错误码、中文消息、描述等的字典
    """
    normalized_key = _normalize_error_key(error_key)
    error_info = ERROR_CODE_MAP.get(normalized_key)
    
    if error_info:
        return dict(error_info)
    
    # 如果没有找到映射，返回默认值
    return {
        "code": f"UNKNOWN_{normalized_key.upper()}",
        "message_cn": default_message_cn or "未知错误",
        "description_cn": f"错误码: {error_key}",
        "category": ERROR_CATEGORY_SYSTEM,
        "http_status": 500,
    }


def format_error_response(
    error_key: str,
    *,
    message_cn: str | None = None,
    technical_details: dict[str, Any] | None = None,
    default_message_cn: str | None = None,
) -> dict[str, Any]:
    """
    格式化错误响应（企业级格式）
    
    Args:
        error_key: 错误码key
        message_cn: 自定义中文消息（覆盖默认）
        technical_details: 技术详情（可折叠显示）
        default_message_cn: 默认中文消息
    
    Returns:
        格式化的错误响应字典
    """
    error_info = get_error_info(error_key, default_message_cn)
    
    response = {
        "ok": False,
        "error": {
            "code": error_info["code"],
            "key": error_key,
            "message_cn": message_cn or error_info["message_cn"],
            "description_cn": error_info["description_cn"],
            "category": error_info["category"],
        },
    }
    
    # 添加技术详情（可折叠）
    if technical_details:
        response["error"]["technical"] = technical_details
    
    return response


def get_http_status(error_key: str, default: int = 500) -> int:
    """获取HTTP状态码"""
    error_info = ERROR_CODE_MAP.get(_normalize_error_key(error_key))
    return error_info.get("http_status", default) if error_info else default
