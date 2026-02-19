from __future__ import annotations

from typing import Any, Callable

# 全局状态与动作中文映射（台账中心单一来源）
APPROVAL_STATUS_MAP: dict[str, str] = {
    "PENDING": "待审核",
    "APPROVED": "已通过",
    "REJECTED": "已驳回",
    "ESCALATED": "已升级",
    "ON_HOLD": "已挂起",
    "RETURNED": "已打回",
    "DONE": "已完成",
}

LEDGER_STATE_MAP: dict[str, str] = {
    "DRAFT": "待补录",
    "LEDGER": "已入账",
    "ARCHIVED": "已归档",
}

VERIFY_STATUS_MAP: dict[str, str] = {
    "PENDING": "待验真",
    "PASS": "验真通过",
    "PASSED": "验真通过",
    "FAIL": "验真不通过",
    "FAILED": "验真不通过",
    "UNKNOWN": "验真未知",
}

APPROVAL_STAGE_MAP: dict[str, str] = {
    "L1": "一级审批",
    "L2": "二级复核",
    "DONE": "已完成",
}

LEDGER_ACTION_MAP: dict[str, str] = {
    "SUBMIT_REVIEW": "提交复核",
    "RETURN_TO_DRAFT": "打回补录",
    "POST_LEDGER": "入账",
    "RERUN_AI_RISK": "重跑识别/重算风险",
    "SUPPLEMENT": "补录",
    "BATCH_RETURN_TO_DRAFT": "批量打回补录",
    "BATCH_SUPPLEMENT": "批量补录",
    "LEDGER_STRUCTURED_EDIT": "更新凭证要素",
    "STRUCTURED_EDIT": "要素校正",
    "EVIDENCE_CENTER": "证据中心",
    "UI_ACTION_BLOCKED": "界面动作拦截",
    "UNKNOWN_ACTION": "未知动作",
}

CHANGE_REASON_CODE_MAP: dict[str, str] = {
    "DATA_COMPLETION": "数据补全",
    "DATA_CORRECTION": "数据更正",
    "SUBMIT_REVIEW": "提交复核",
    "RETURN_FOR_COMPLETION": "打回补录",
    "RERUN_AI_RISK": "重跑识别/重算风险",
    "MANUAL_OVERRIDE": "人工覆盖",
    "POLICY_EXCEPTION": "制度例外",
    "NEED_MORE_INFO": "需补充信息",
    "SYSTEM_AUTO": "系统自动处理",
    # 规则变更专用
    "MANUAL_ADJUST": "人工调整",
    "POLICY_UPDATE": "政策变更",
    "THRESHOLD_CALIBRATION": "阈值校准",
    "FALSE_POSITIVE_FIX": "误报修正",
    "TEMP_CONTROL": "临时管控",
    "RESTORE_DEFAULT": "恢复默认",
}

# 审计动作中文映射（企业级审计要求）
AUDIT_ACTION_MAP: dict[str, str] = {
    "CREATE": "创建",
    "UPDATE": "更新",
    "DELETE": "删除",
    "APPROVE": "审批通过",
    "REJECT": "审批驳回",
    "ASSIGN": "分派",
    "CLOSE": "关闭",
    "SUBMIT": "提交",
    "RETURN": "打回",
    "POST": "入账",
    "RERUN": "重跑",
    "SUPPLEMENT": "补录",
    "EDIT": "编辑",
    "BATCH_UPDATE": "批量更新",
    "BATCH_DELETE": "批量删除",
    "ENABLE": "启用",
    "DISABLE": "禁用",
    "RESET_PASSWORD": "重置密码",
    "CHANGE_PASSWORD": "修改密码",
    "LOGIN": "登录",
    "LOGOUT": "登出",
    "LOCK": "锁定",
    "UNLOCK": "解锁",
    "APPEND_EVENT": "追加事件",
    "LINK_EVIDENCE": "关联证据",
}

# 目标类型中文映射
AUDIT_TARGET_TYPE_MAP: dict[str, str] = {
    "invoice": "凭证",
    "user": "用户",
    "role": "角色",
    "department": "部门",
    "rule": "规则",
    "case": "案件",
    "event": "事件",
    "workflow": "流程",
    "settings": "系统设置",
    "permission": "权限",
}


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().upper()


def to_cn_status(value: Any, mapping: dict[str, str]) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    return mapping.get(_normalize_key(text), text)


def to_cn_approval_status(value: Any) -> str:
    return to_cn_status(value, APPROVAL_STATUS_MAP)


def to_cn_ledger_state(value: Any) -> str:
    return to_cn_status(value, LEDGER_STATE_MAP)


def to_cn_verify_status(value: Any) -> str:
    return to_cn_status(value, VERIFY_STATUS_MAP)


def to_cn_approval_stage(value: Any) -> str:
    return to_cn_status(value, APPROVAL_STAGE_MAP)


def to_cn_ledger_action(value: Any) -> str:
    return to_cn_status(value, LEDGER_ACTION_MAP)


def to_cn_reason_code(value: Any) -> str:
    return to_cn_status(value, CHANGE_REASON_CODE_MAP)


def to_cn_audit_action(value: Any) -> str:
    """审计动作中文映射"""
    return to_cn_status(value, AUDIT_ACTION_MAP)


def to_cn_audit_target_type(value: Any) -> str:
    """审计目标类型中文映射"""
    return to_cn_status(value, AUDIT_TARGET_TYPE_MAP)


def with_cn_status_fields(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return row

    approval_raw = row.get("approval_status") or row.get("status")
    row["approval_status_cn"] = to_cn_approval_status(approval_raw)
    row["status_cn"] = row["approval_status_cn"]
    row["record_state_cn"] = to_cn_ledger_state(row.get("record_state"))
    row["verify_status_cn"] = to_cn_verify_status(row.get("verify_status"))
    row["approval_stage_cn"] = to_cn_approval_stage(row.get("approval_stage"))
    return row


def localize_status_snapshot(snapshot: Any) -> Any:
    field_map: dict[str, Callable[[Any], str]] = {
        "record_state": to_cn_ledger_state,
        "approval_status": to_cn_approval_status,
        "status": to_cn_approval_status,
        "verify_status": to_cn_verify_status,
        "approval_stage": to_cn_approval_stage,
    }

    if isinstance(snapshot, dict):
        localized: dict[str, Any] = {}
        for key, value in snapshot.items():
            key_text = str(key or "")
            translator = field_map.get(key_text)
            if translator is not None and not isinstance(value, (dict, list, tuple)):
                localized[key_text] = translator(value)
            else:
                localized[key_text] = localize_status_snapshot(value)
        return localized

    if isinstance(snapshot, list):
        return [localize_status_snapshot(item) for item in snapshot]
    if isinstance(snapshot, tuple):
        return tuple(localize_status_snapshot(item) for item in snapshot)
    return snapshot
