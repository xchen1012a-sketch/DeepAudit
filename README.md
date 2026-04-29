# DeepAudit Pro

DeepAudit Pro 是一个面向企业财务审计与费用风控场景的智能审计系统，聚焦发票识别、单据核验、风险识别、审批流转、审计留痕与台账管理。项目当前以 Flask 为核心，提供可运行的 Web 原型，适合继续扩展为内部审计、财务合规和税务风险预警平台。

## 项目定位

传统财务审计依赖大量人工核对：发票、合同、付款记录、凭证、账表之间要反复比对，既耗时又容易漏掉异常。DeepAudit Pro 的目标是把这类高频、规则明确但仍需要综合判断的工作自动化，帮助审计人员把更多精力放在复核和决策上。

## 核心能力

- 发票采集与 OCR 识别，支持图片和 PDF 上传
- 发票验真与税务校验，支持 mock / provider 模式切换
- 风险规则识别与分级，覆盖重复报销、异常付款、字段不一致等场景
- 审批中心与审计工作台，支持状态流转和多角色处理
- 审计链路与日志留痕，便于追溯关键操作
- 权限、角色、数据范围治理，支持后台 IAM 管理
- 风险案例、监控看板、知识中心等扩展模块

## 系统结构

项目采用较清晰的分层结构：

- `core/`：应用工厂、配置、扩展初始化、日志
- `routes/`：页面与 API 路由
- `services/`：业务逻辑，包括审批、台账、风险、集成服务
- `integrations/`：税务、银行、ERP、OA 等外部集成适配
- `providers/`：Provider 抽象与 mock 实现
- `templates/`：Jinja2 页面模板
- `static/`：前端静态资源
- `scripts/`：初始化、诊断、数据填充、自检脚本
- `tests/`：核心权限、审批、台账、治理能力测试

## 技术栈

- Python 3.10+
- Flask
- SQLAlchemy
- SQLite（默认，可通过环境变量切换）
- Jinja2 + Bootstrap
- pytest

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
copy .env.example .env
```

至少需要配置：

- `SECRET_KEY`

常用配置项：

- `DATABASE_URL`
- `DATA_PROVIDER`
- `ENABLE_CSRF_PROTECTION`
- `DASHSCOPE_API_KEY`
- `LLM_MODEL_NAME`
- `FLASK_HOST`
- `FLASK_PORT`
- `FLASK_DEBUG`

### 3. 初始化数据库

```bash
python scripts/init_db_keep_admin01.py --yes
```

### 4. 启动应用

```bash
python app.py
```

默认访问地址：

```text
http://127.0.0.1:5000
```

## 测试

运行项目测试：

```bash
pytest -q
```

建议优先关注以下回归测试：

- `tests/test_admin_roles_permissions.py`
- `tests/test_approval_role_guardrails.py`
- `tests/test_ledger_record_state.py`
- `tests/test_governance_rules.py`

## 部署说明

- 开发环境默认使用 SQLite，本地即可快速启动
- 生产环境建议切换独立数据库并使用更强的 `SECRET_KEY`
- 可结合 `gunicorn_config.py` 与 `nginx.conf` 部署
- 所有真实密钥请通过环境变量注入，不要写入仓库

## 仓库说明

本仓库仅保留项目运行与开发所需文件，不包含本地数据库、日志、上传文件、环境密钥及个人工具配置。推送公开仓库前，应确保 `.env`、`.secrets/`、数据库文件和临时产物未被纳入版本控制。

## License

MIT
