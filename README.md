# DeepAudit Pro

企业级智能审计与费用风控系统，覆盖发票采集、OCR识别、风控评估、审批流转、台账管理、权限治理与审计留痕。

仓库地址：`https://github.com/xchen1012a-sketch/DeepAudit_Pro.git`  
最后更新：`2026-02-22`

## 1. 核心能力

- 发票采集与识别：支持图片/PDF上传，自动提取关键字段
- 风险识别与分级：规则引擎 + 风险指标聚合
- 审批中心：支持多级审批、退回、转派和批量处理
- 台账中心：按状态流转管理单据，支持检索与导出
- 权限与数据域：角色、权限、数据范围（ALL/DEPT/SELF 等）
- 审计追踪：关键操作全链路日志与审计记录
- 集成能力：税务/银行/ERP/OA 的 mock 与 real provider 架构

## 2. 技术栈

- 后端：Python + Flask
- 数据层：SQLAlchemy + SQLite（可通过 `DATABASE_URL` 切换）
- 前端：Jinja2 + Bootstrap + JavaScript
- 任务与扩展：Scheduler、Provider Registry、可插拔服务层
- 测试：pytest

## 3. 项目结构

```text
DeepAudit_pro/
|- app.py
|- core/                 # 应用工厂、配置、日志、扩展初始化
|- routes/               # 各业务模块路由
|- services/             # 业务服务层
|- utils/                # 数据访问、安全、审计、通用能力
|- integrations/         # 外部系统接入实现
|- providers/            # Provider 抽象与注册
|- templates/            # 页面模板
|- static/               # 静态资源（JS/CSS）
|- scripts/              # 初始化、自检、修复、数据脚本
|- tests/                # 自动化测试
|- docs/                 # 项目文档
|- artifacts/            # 演示与快照资源
```

## 4. 快速启动

### 4.1 环境要求

- Python `3.10+`（建议）
- pip 可用

### 4.2 安装依赖

```bash
pip install -r requirements.txt
```

### 4.3 配置环境变量

推荐以 `.env.example` 为模板：

```bash
copy .env.example .env
```

必须至少配置：

- `SECRET_KEY`

常用配置：

- `DATABASE_URL`（默认 `sqlite:///database.db`）
- `DATA_PROVIDER`（`mock` 或 `real`）
- `ENABLE_CSRF_PROTECTION`
- `DASHSCOPE_API_KEY`
- `LLM_MODEL_NAME`

### 4.4 初始化数据库

```bash
python scripts/init_db_keep_admin01.py --yes
```

说明：

- 脚本会清理业务数据并保留 `admin01` 账号结构
- 若未设置 `ADMIN_INIT_PASSWORD`，系统可能生成一次性初始密码（以控制台日志为准）

### 4.5 启动系统

```bash
python app.py
```

默认访问地址：

- `http://127.0.0.1:5000`

Windows 也可直接使用脚本：

- `一键启动.bat`
- `快速启动.bat`

## 5. 测试与质量

运行全部测试：

```bash
pytest -q
```

建议优先关注：

- 审批与权限相关测试：`tests/test_admin_roles_permissions.py`
- 台账状态守卫测试：`tests/test_ledger_record_state.py`
- 权限生效回归：`tests/test_permission_grant_effective.py`

## 6. 生产部署建议

- 使用 `gunicorn_config.py` 配置 WSGI 进程
- 结合 `nginx.conf` 反向代理
- 生产环境务必设置：
  - 强随机 `SECRET_KEY`
  - 独立数据库与最小权限账户
  - 关闭 `DEV_ALLOW_INSECURE`
  - 轮换 API 密钥（如 `DASHSCOPE_API_KEY`）

## 7. 常用脚本

- `scripts/init_db_keep_admin01.py`：数据库重置并保留管理员账号
- `scripts/seed_demo.py`：演示数据初始化
- `scripts/selfcheck_providers.py`：Provider 自检
- `scripts/verify_init.py`：初始化验证
- `scripts/db_smoke.py`：数据库冒烟检查

## 8. 许可证

本项目使用 `MIT` 许可证，详见 `LICENSE`。

## 9. 本次仓库同步说明（2026-02-22）

- 同步了当前工作目录下的最新代码与资源（遵循 `.gitignore`）
- 更新了 `README.md`，与当前项目结构和启动流程对齐
