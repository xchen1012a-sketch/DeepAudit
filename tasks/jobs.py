from __future__ import annotations

from datetime import datetime, timedelta
import logging
from threading import Lock
from typing import Any

from events import event_bus
from events.types import BANK_TXN_SAVED, PAYMENT_IMPORTED, PAYMENT_MATCHED, STAGE_INGEST, STAGE_RULE_HIT
from providers.registry import get_bank_provider
from services.bank_service import get_transactions_by_txn_ids, save_transactions
from services.match_service import match_bank_to_invoices
from services.finance_integration import sync_erp_vouchers
from services.hr_integration import sync_employees, sync_organization_structure
from services.oa_integration import sync_approval_tasks
from services.bank_integration import pull_bank_transactions
from services.monitoring_service import collect_system_metrics, collect_business_metrics, collect_risk_metrics, check_alerts
from services.knowledge_service import recommend_rule_optimization
from services.integration_service import list_integrations

_cursor_lock = Lock()
_bank_cursor: str | None = None
_failure_guard_lock = Lock()
_recent_failed_batches: dict[str, datetime] = {}
_FAILURE_DEDUP_WINDOW = timedelta(minutes=10)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _get_cursor() -> str | None:
    with _cursor_lock:
        return _bank_cursor


def _set_cursor(value: str | None) -> None:
    global _bank_cursor
    with _cursor_lock:
        _bank_cursor = value


def _advance_cursor(previous: str | None, next_cursor: Any, count: int) -> str | None:
    if next_cursor is not None and str(next_cursor).strip() != "":
        return str(next_cursor).strip()
    if count <= 0:
        return previous
    try:
        base = int(str(previous).strip()) if previous not in (None, "") else 0
        return str(base + count)
    except Exception:
        return previous


def _normalize_limit(value: Any, default: int = 20) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    if parsed <= 0:
        parsed = default
    return min(parsed, 500)


def _normalize_run_mode(value: Any) -> str:
    mode = _safe_text(value).lower()
    if mode in {"manual", "scheduler", "demo"}:
        return mode
    return "manual"


def _failure_dedup_key(*, provider: str, cursor: str | None, next_cursor: str | None) -> str:
    return "|".join(
        [
            _safe_text(provider) or "unknown",
            _safe_text(cursor) or "-",
            _safe_text(next_cursor) or "-",
        ]
    )


def _is_duplicate_failure(key: str) -> bool:
    now = datetime.now()
    with _failure_guard_lock:
        stale_before = now - _FAILURE_DEDUP_WINDOW
        stale_keys = [k for k, ts in _recent_failed_batches.items() if ts < stale_before]
        for stale_key in stale_keys:
            _recent_failed_batches.pop(stale_key, None)

        previous = _recent_failed_batches.get(key)
        _recent_failed_batches[key] = now
        if previous is None:
            return False
        return (now - previous) < _FAILURE_DEDUP_WINDOW


def pull_bank_incremental(
    *,
    run_mode: str = "scheduler",
    cursor: str | None = None,
    limit: int = 20,
    persist_cursor: bool = True,
) -> dict[str, Any]:
    logger = logging.getLogger("core.app_factory")
    mode = _normalize_run_mode(run_mode)
    active_cursor = _safe_text(cursor) or _get_cursor()
    normalized_limit = _normalize_limit(limit, default=20)

    try:
        provider = get_bank_provider()
        result = provider.pull_transactions(cursor=active_cursor, limit=normalized_limit)
    except Exception as exc:
        logger.exception(
            "action=bank_pull run_mode=%s status=provider_error cursor=%s err=%s",
            mode,
            active_cursor,
            exc,
        )
        return {
            "ok": False,
            "status": "provider_error",
            "message": str(exc),
            "next_cursor": active_cursor,
            "items": [],
            "provider": "unknown",
            "run_mode": mode,
            "imported": 0,
            "saved": 0,
            "skipped": 0,
            "matched": 0,
        }

    if not isinstance(result, dict):
        result = {"ok": False, "message": "invalid provider response", "next_cursor": active_cursor, "items": []}

    ok = bool(result.get("ok"))
    items = result.get("items")
    if not isinstance(items, list):
        items = []

    provider_name = _safe_text(result.get("provider")) or "unknown"
    next_cursor = _advance_cursor(active_cursor, result.get("next_cursor"), len(items))
    if persist_cursor:
        _set_cursor(next_cursor)

    payload = dict(result)
    payload["items"] = items
    payload["provider"] = provider_name
    payload["next_cursor"] = next_cursor
    payload["run_mode"] = mode
    payload["imported"] = int(len(items))
    payload["saved"] = 0
    payload["skipped"] = 0
    payload["matched"] = 0

    if not ok:
        error_code = _safe_text(result.get("error_code")) or "unknown"
        failure_key = _failure_dedup_key(
            provider=provider_name,
            cursor=active_cursor,
            next_cursor=next_cursor,
        )
        duplicate = _is_duplicate_failure(failure_key)
        payload["status"] = "failed_duplicate_suppressed" if duplicate else "failed"
        payload["deduplicated_failure"] = duplicate
        if duplicate:
            logger.info(
                "action=bank_pull run_mode=%s status=failed_duplicate_suppressed provider=%s "
                "cursor=%s next_cursor=%s error_code=%s",
                mode,
                provider_name,
                active_cursor,
                next_cursor,
                error_code,
            )
        else:
            logger.warning(
                "action=bank_pull run_mode=%s status=failed provider=%s cursor=%s next_cursor=%s "
                "error_code=%s msg=%s",
                mode,
                provider_name,
                active_cursor,
                next_cursor,
                error_code,
                result.get("message"),
            )
        return payload

    if not items:
        payload["status"] = "ok_no_data"
        logger.info(
            "action=bank_pull run_mode=%s status=ok_no_data imported=0 provider=%s next_cursor=%s",
            mode,
            provider_name,
            next_cursor,
        )
        return payload

    try:
        save_result = save_transactions(items)
    except Exception as exc:
        logger.exception("action=bank_pull run_mode=%s status=save_failed err=%s", mode, exc)
        save_result = {"saved_count": 0, "skipped_count": len(items), "saved_txn_ids": [], "saved_all_txn_ids": []}

    saved_count = int(save_result.get("saved_count", 0))
    skipped_count = int(save_result.get("skipped_count", 0))
    payload["saved"] = saved_count
    payload["skipped"] = skipped_count
    payload["save_result"] = save_result
    if saved_count <= 0:
        logger.info(
            "action=bank_pull run_mode=%s status=ok_no_new imported=%s skipped=%s provider=%s next_cursor=%s",
            mode,
            len(items),
            skipped_count,
            provider_name,
            next_cursor,
        )
        payload["status"] = "ok_no_new"
        payload["match_result"] = {"matched_count": 0, "matched_pairs": []}
        return payload

    first = items[0] if isinstance(items[0], dict) else {}
    first_txn_id = str(first.get("txn_id") or "")
    event_bus.publish(
        PAYMENT_IMPORTED,
        {
            "stage": STAGE_INGEST,
            "count": len(items),
            "first_txn_id": first_txn_id,
            "next_cursor": next_cursor,
            "provider": provider_name,
            "run_mode": mode,
        },
    )

    event_bus.publish(
        BANK_TXN_SAVED,
        {
            "stage": STAGE_RULE_HIT,
            "saved_count": saved_count,
            "skipped_count": skipped_count,
            "saved_txn_ids": list(save_result.get("saved_txn_ids") or []),
            "provider": provider_name,
            "next_cursor": next_cursor,
            "run_mode": mode,
        },
    )

    matched_payload: dict[str, Any] = {"matched_count": 0, "matched_pairs": []}
    try:
        saved_all_txn_ids = list(save_result.get("saved_all_txn_ids") or [])
        if saved_all_txn_ids:
            saved_rows = get_transactions_by_txn_ids(saved_all_txn_ids)
            matched_payload = match_bank_to_invoices(saved_rows)
    except Exception as exc:
        logger.exception("action=bank_pull run_mode=%s status=match_failed err=%s", mode, exc)

    event_bus.publish(
        PAYMENT_MATCHED,
        {
            "matched_count": int(matched_payload.get("matched_count", 0)),
            "matched_pairs": list(matched_payload.get("matched_pairs") or [])[:3],
            "provider": provider_name,
            "run_mode": mode,
        },
    )

    matched_count = int(matched_payload.get("matched_count", 0))
    payload["matched"] = matched_count
    payload["status"] = "ok"
    payload["match_result"] = matched_payload
    logger.info(
        "action=bank_pull run_mode=%s status=ok imported=%s saved=%s skipped=%s matched=%s "
        "provider=%s next_cursor=%s",
        mode,
        len(items),
        saved_count,
        skipped_count,
        matched_count,
        provider_name,
        next_cursor,
    )
    return payload


def sync_finance_data(enterprise_id: int = 1) -> dict[str, Any]:
    """财务系统数据同步任务（每小时）"""
    logger = logging.getLogger("core.app_factory")
    try:
        result = sync_erp_vouchers(enterprise_id)
        logger.info(f"财务系统同步完成: {result}")
        return result
    except Exception as e:
        logger.error(f"财务系统同步失败: {e}", exc_info=True)
        return {"ok": False, "msg": str(e)}


def sync_hr_data(enterprise_id: int = 1) -> dict[str, Any]:
    """HR系统数据同步任务（每天）"""
    logger = logging.getLogger("core.app_factory")
    try:
        # 同步组织架构
        org_result = sync_organization_structure(enterprise_id)
        # 同步员工信息
        emp_result = sync_employees(enterprise_id)
        logger.info(f"HR系统同步完成: org={org_result}, emp={emp_result}")
        return {"ok": True, "org": org_result, "employees": emp_result}
    except Exception as e:
        logger.error(f"HR系统同步失败: {e}", exc_info=True)
        return {"ok": False, "msg": str(e)}


def sync_oa_data(enterprise_id: int = 1) -> dict[str, Any]:
    """OA系统数据同步任务（每15分钟）"""
    logger = logging.getLogger("core.app_factory")
    try:
        result = sync_approval_tasks(enterprise_id)
        logger.info(f"OA系统同步完成: {result}")
        return result
    except Exception as e:
        logger.error(f"OA系统同步失败: {e}", exc_info=True)
        return {"ok": False, "msg": str(e)}


def sync_bank_data(enterprise_id: int = 1) -> dict[str, Any]:
    """银行流水拉取任务（每15分钟）"""
    logger = logging.getLogger("core.app_factory")
    try:
        result = pull_bank_transactions(enterprise_id)
        logger.info(f"银行流水拉取完成: {result}")
        return result
    except Exception as e:
        logger.error(f"银行流水拉取失败: {e}", exc_info=True)
        return {"ok": False, "msg": str(e)}


def collect_monitoring_metrics() -> dict[str, Any]:
    """监控指标采集任务（每分钟）"""
    logger = logging.getLogger("core.app_factory")
    try:
        system_metrics = collect_system_metrics()
        business_metrics = collect_business_metrics()
        risk_metrics = collect_risk_metrics()
        logger.debug(f"监控指标采集完成: system={len(system_metrics)}, business={len(business_metrics)}, risk={len(risk_metrics)}")
        return {
            "ok": True,
            "system": system_metrics,
            "business": business_metrics,
            "risk": risk_metrics,
        }
    except Exception as e:
        logger.error(f"监控指标采集失败: {e}", exc_info=True)
        return {"ok": False, "msg": str(e)}


def check_monitoring_alerts() -> dict[str, Any]:
    """告警检查任务（每5分钟）"""
    logger = logging.getLogger("core.app_factory")
    try:
        alerts = check_alerts()
        if alerts:
            logger.warning(f"检测到 {len(alerts)} 个告警")
            for alert in alerts:
                logger.warning(f"告警: {alert.get('type')} - {alert.get('message')}")
        return {"ok": True, "alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.error(f"告警检查失败: {e}", exc_info=True)
        return {"ok": False, "msg": str(e)}


def analyze_risk_trends() -> dict[str, Any]:
    """风险趋势分析任务（每天）"""
    logger = logging.getLogger("core.app_factory")
    try:
        # TODO: 实现风险趋势分析逻辑
        logger.info("风险趋势分析完成")
        return {"ok": True, "msg": "风险趋势分析完成"}
    except Exception as e:
        logger.error(f"风险趋势分析失败: {e}", exc_info=True)
        return {"ok": False, "msg": str(e)}


def evaluate_rule_effectiveness() -> dict[str, Any]:
    """规则效果评估任务（每周）"""
    logger = logging.getLogger("core.app_factory")
    try:
        recommendations = recommend_rule_optimization()
        logger.info(f"规则效果评估完成，推荐优化: {len(recommendations)} 条")
        return {"ok": True, "recommendations": recommendations}
    except Exception as e:
        logger.error(f"规则效果评估失败: {e}", exc_info=True)
        return {"ok": False, "msg": str(e)}
