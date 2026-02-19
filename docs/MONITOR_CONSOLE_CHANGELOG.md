# 系统监控页面重做 - 改动清单

## 概述

将【系统监控】重做为运维/治理控制台，不再复用首页业务看板布局与指标。目标：可用性/性能/错误/作业/依赖/安全，一页定位问题与钻取日志。

## 改动清单

### 1. 模板

| 文件 | 变更 |
|------|------|
| `templates/monitoring/monitoring_dashboard.html` | **重做**：P0 布局（顶部态势条、四个面板、底部日志与追踪）、时间窗切换、日志详情抽屉、全链路中文 |
| `templates/layout/base.html` | 侧边栏「系统监控」链接改为 `/monitoring/dashboard`；`_show_monitor_system` 改为依赖 `_can_manage_system`；`_monitor_system_active` 判断路径 `/monitoring/dashboard` |

### 2. CSS

| 文件 | 变更 |
|------|------|
| `templates/monitoring/monitoring_dashboard.html` | 内联 `<style>`：态势条、面板、健康状态灯、日志表格、抽屉、筛选栏 |

### 3. 接口

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/monitor/summary` | GET | 顶部态势条：请求量、错误率、P95、失败作业、DB 状态、未处理告警；参数 `window`=15m/1h/24h |
| `/api/monitor/health` | GET | 服务健康：web/api/db/tax/bank/erp 状态灯 + 最近检查时间 |
| `/api/monitor/errors` | GET | 性能与错误：延迟趋势、Top 错误、最近错误；参数 `window`, `limit` |
| `/api/monitor/jobs` | GET | 作业与流水线：OCR/验真/规则评估/风险评分/审批流；参数 `window` |
| `/api/monitor/logs` | GET | 日志与追踪；参数 `time_from`, `time_to`, `level`, `module`, `request_id`, `user`, `limit` |

### 4. 权限

- **页面** `/monitoring/dashboard`：仅 `MANAGE_SYSTEM` 或 `MANAGE_SETTINGS` 可访问
- **API** `/api/monitor/*`：同上，无权限返回 403，`message` 为中文「您无权访问系统监控，仅治理/系统管理员可访问」
- `utils/permission_meta.py`：`monitor_system` 菜单项权限改为 `["MANAGE_SYSTEM", "MANAGE_SETTINGS"]`
- `FORBIDDEN_ROUTE_HINTS` 增加 `/monitoring` 提示

### 5. 服务层

| 文件 | 变更 |
|------|------|
| `services/monitoring_service.py` | 新增 `get_monitor_summary`, `get_monitor_health`, `get_monitor_errors`, `get_monitor_jobs`, `list_monitor_logs`；从 `db_metrics`、`audit_logs`、`audit_log`、`invoices`、`risk_events` 聚合 |

### 6. 路由

| 文件 | 变更 |
|------|------|
| `routes/monitoring.py` | 新增 `/api/monitor/summary`、`/api/monitor/health`、`/api/monitor/errors`、`/api/monitor/jobs`、`/api/monitor/logs`；页面与 API 使用 `_has_monitor_permission()` 校验，返回 403 中文 |

---

## 关键实现点

### 聚合统计

- **summary**：`audit_logs` 活动估算请求量/错误；`invoices` 验真/审批失败数；`check_alerts()` 未处理告警
- **health**：DB 连接探测推断 web/api/db；外部依赖 tax/bank/erp 暂为 unknown
- **errors**：`audit_logs` 中 `LOGIN_FAIL`、`LOGIN_LOCK` 及含 ERROR/失败/403/500 的 detail
- **jobs**：`invoices` 验真/审批统计；`risk_events` 规则评估/风险评分
- **logs**：`audit_logs` + `audit_log`（按 `trace_id` 补充），支持时间、模块、request_id、用户筛选

### 筛选与钻取

- 日志支持 `time_from`、`time_to`、`level`、`module`、`request_id`、`user`
- 点击「详情」打开右侧抽屉，展示完整记录；技术信息（JSON）可折叠

### 时间窗

- 支持 15m / 1h / 24h，参数 `window` 传给 summary、errors、jobs

---

## 回归用例

| 用例 | 说明 |
|------|------|
| 权限 403 | 非治理/系统管理员访问 `/api/monitor/summary` 返回 403，`message` 含「无权」 |
| 接口正常 | 有权限时 `/api/monitor/summary`、`/api/monitor/health` 等返回 200，`ok: true` |
| 时间窗切换 | `get_monitor_summary(time_window="15m"|"1h"|"24h")` 返回正确 `time_window` |
| 健康结构 | `get_monitor_health()` 返回 `services` 列表和 `checked_at` |
| 作业结构 | `get_monitor_jobs()` 返回 `jobs` 和 `failed_top_reasons` |
| 日志筛选 | `list_monitor_logs(limit=5)` 返回 `logs`、`total`，条数不超过 limit |

运行：`python -m pytest tests/test_monitor_console.py -v`
