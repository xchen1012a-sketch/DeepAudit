from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

from flask import Flask

from tasks.jobs import (
    pull_bank_incremental,
    sync_finance_data,
    sync_hr_data,
    sync_oa_data,
    sync_bank_data,
    collect_monitoring_metrics,
    check_monitoring_alerts,
    analyze_risk_trends,
    evaluate_rule_effectiveness,
)

_thread_lock = threading.Lock()
_scheduler_thread: threading.Thread | None = None

# 任务执行时间记录
_last_run_times: dict[str, datetime] = {}


def _should_run_task(task_name: str, interval_seconds: int) -> bool:
    """检查任务是否应该运行"""
    now = datetime.now()
    last_run = _last_run_times.get(task_name)
    if last_run is None:
        return True
    elapsed = (now - last_run).total_seconds()
    return elapsed >= interval_seconds


def _mark_task_run(task_name: str) -> None:
    """标记任务已运行"""
    _last_run_times[task_name] = datetime.now()


def _run_scheduler(app: Flask) -> None:
    logger = app.logger
    enterprise_id = 1  # 默认企业ID，实际应该从配置获取

    while True:
        try:
            with app.app_context():
                # 银行流水拉取（每15分钟）
                if _should_run_task("bank_pull", 15 * 60):
                    pull_bank_incremental(run_mode="scheduler", limit=20)
                    _mark_task_run("bank_pull")

                # 监控指标采集（每分钟）
                if _should_run_task("monitoring_metrics", 60):
                    collect_monitoring_metrics()
                    _mark_task_run("monitoring_metrics")

                # 告警检查（每5分钟）
                if _should_run_task("monitoring_alerts", 5 * 60):
                    check_monitoring_alerts()
                    _mark_task_run("monitoring_alerts")

                # OA系统同步（每15分钟）
                if _should_run_task("oa_sync", 15 * 60):
                    sync_oa_data(enterprise_id)
                    _mark_task_run("oa_sync")

                # 银行数据同步（每15分钟）
                if _should_run_task("bank_sync", 15 * 60):
                    sync_bank_data(enterprise_id)
                    _mark_task_run("bank_sync")

                # 财务系统同步（每小时）
                if _should_run_task("finance_sync", 60 * 60):
                    sync_finance_data(enterprise_id)
                    _mark_task_run("finance_sync")

                # HR系统同步（每天）
                if _should_run_task("hr_sync", 24 * 60 * 60):
                    sync_hr_data(enterprise_id)
                    _mark_task_run("hr_sync")

                # 风险趋势分析（每天）
                if _should_run_task("risk_analysis", 24 * 60 * 60):
                    analyze_risk_trends()
                    _mark_task_run("risk_analysis")

                # 规则效果评估（每周）
                if _should_run_task("rule_evaluation", 7 * 24 * 60 * 60):
                    evaluate_rule_effectiveness()
                    _mark_task_run("rule_evaluation")

        except Exception as exc:
            logger.exception("scheduler loop error: %s", exc)
        time.sleep(30)  # 每30秒检查一次


def start_scheduler(app: Flask) -> bool:
    global _scheduler_thread
    with _thread_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            return False

        thread = threading.Thread(
            target=_run_scheduler,
            args=(app,),
            name="deepaudit-scheduler",
            daemon=True,
        )
        thread.start()
        _scheduler_thread = thread
        app.logger.info("scheduler started")
        return True
