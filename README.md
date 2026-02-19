# DeepAudit Pro

企业级智能审计系统，基于 AI 驱动的财务审计与风险管理平台。

## 快速启动

### 方式一：演示模式（推荐用于演示和测试）

双击运行演示模式启动脚本，自动创建演示数据库并生成演示数据：

```cmd
scripts\run_demo.bat
```

**演示模式特点：**
- 每次启动自动删除并重建 `database_demo.db`
- 自动生成演示数据（审计日志、风险事件、发票台账）
- 数据完全隔离，不影响 `database.db`

### 方式二：纯净模式（推荐用于开发和生产）

双击运行纯净模式启动脚本，创建空白数据库：

```cmd
scripts\run_clean.bat
```

**纯净模式特点：**
- 每次启动自动删除并重建 `database_clean.db`（空白数据库）
- 不生成任何演示数据
- 数据完全隔离，不影响 `database.db`

### 导出真实数据库给 Navicat

如需在 Navicat 中查看真实数据库（非 demo/clean），双击运行导出脚本：

```cmd
scripts\export_real_db.bat
```

脚本会自动识别真实数据库并导出到 `exports/database_real_for_navicat.db`，然后在 Navicat 中选择该文件即可打开。

### 数据库隔离说明

本项目采用严格的数据库隔离策略：

| 数据库文件 | 用途 | 启动方式 | 数据内容 |
|-----------|------|---------|---------|
| `database_demo.db` | 演示环境 | `scripts\run_demo.bat` | 自动生成演示数据 |
| `database_clean.db` | 开发环境 | `scripts\run_clean.bat` | 空白数据库 |
| `database.db` | 生产环境 | 手动配置 | **绝不会被脚本删除** |

**安全保证：**
- 启动脚本只操作各自的目标数据库（`database_demo.db` 或 `database_clean.db`）
- 绝对不会删除或覆盖 `database.db`
- 每次启动前都会显示确认提示

## 手动安装（可选）

如果需要手动配置环境：

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境（Windows）
.venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.lock.txt

# 4. 设置环境变量（可选）
set DATABASE_URL=sqlite:///database.db
set FLASK_APP=app.py
set FLASK_DEBUG=1

# 5. 初始化数据库
flask db upgrade
# 或
python -c "from core.app_factory import create_app; from utils.db import init_db; app = create_app(); app.app_context().push(); init_db()"

# 6. 启动应用
flask run
```

## 技术栈

- **后端框架**: Flask 3.0
- **数据库**: SQLite + SQLAlchemy ORM
- **数据库迁移**: Flask-Migrate (Alembic)
- **认证**: Flask-Login
- **AI 集成**: 通义千问 (DashScope)
- **数据处理**: Pandas, OpenPyXL

## 核心功能

- ✅ 智能发票识别与验真
- ✅ AI 驱动的风险评估
- ✅ 完整的审计日志系统
- ✅ 风险事件管理
- ✅ 多级审批流程
- ✅ 数据可视化与报表
- ✅ Power BI 数据接口（预聚合 + Web API）

## Power BI 接入

DeepAudit Pro 提供专门的 Power BI 数据接口，支持 CSV/JSON 双格式输出。

### 快速开始

1. 启动应用后，访问 Power BI API：
```
http://localhost:5000/api/pbi/health
```

2. 在 Power BI Desktop 中添加 Web 数据源：
```
http://localhost:5000/api/pbi/metrics/daily?format=csv
```

3. 查看完整文档：[Power BI 接入指南](docs/PowerBI接入指南.md)

### 可用接口

- `/api/pbi/metrics/daily` - 每日指标（发票、风险、交易）
- `/api/pbi/metrics/actions` - 动作指标（用户操作统计）
- `/api/pbi/metrics/risks` - 风险指标（按等级和状态）
- `/api/pbi/metrics/departments` - 部门指标（部门对比）
- `/api/pbi/dashboard` - 综合仪表板数据

### 特性

- ✅ 后端预聚合，避免直连业务库
- ✅ 支持 CSV/JSON 双格式
- ✅ 内置缓存机制（15 分钟）
- ✅ 支持 API Key 认证
- ✅ 默认查询最近 90 天数据

## 项目结构

```
DeepAudit_Pro/
├── core/               # 核心模块（应用工厂、配置、扩展）
├── models/             # ORM 模型定义
├── routes/             # 路由蓝图
│   ├── pbi_api.py      # Power BI API 路由
│   └── ...
├── services/           # 业务逻辑层
│   ├── pbi_aggregation_service.py  # Power BI 数据聚合服务
│   └── ...
├── utils/              # 工具函数
│   ├── pbi_cache.py    # Power BI 缓存工具
│   └── ...
├── scripts/            # 启动脚本和工具脚本
│   ├── run_demo.bat    # 演示模式启动脚本
│   ├── export_real_db.bat  # 数据库导出脚本
│   ├── seed_invoices.py    # 发票数据生成
│   ├── seed_risk_events.py # 风险事件数据生成
│   ├── seed_risk_cases.py  # 风险案例数据生成
│   ├── seed_bank_transactions.py  # 银行交易数据生成
│   └── validate_data.py    # 数据验证脚本
├── templates/          # HTML 模板
├── static/             # 静态资源
├── migrations/         # 数据库迁移文件
├── exports/            # 数据库导出目录
└── docs/               # 项目文档
    ├── PowerBI接入指南.md
    ├── 数据库导出功能说明.md
    └── ...
```

## 环境变量配置

创建 `.env` 文件配置环境变量（可选）：

```env
# 数据库配置（支持 SQLAlchemy 格式）
DATABASE_URL=sqlite:///database.db

# Flask 配置
FLASK_APP=app.py
FLASK_DEBUG=1
FLASK_ENV=development
SECRET_KEY=your-secret-key-here

# 开发模式（允许不安全的密钥）
DEV_ALLOW_INSECURE=1

# AI 配置
DASHSCOPE_API_KEY=your-dashscope-api-key
LLM_MODEL_NAME=qwen-turbo

# Power BI API 配置（可选）
PBI_API_KEY=your-pbi-api-key

# 应用模式（demo/clean/production）
APP_MODE=production
```

## 开发说明

### 数据库迁移

```bash
# 生成迁移脚本
flask db migrate -m "描述"

# 应用迁移
flask db upgrade

# 回滚迁移
flask db downgrade
```

### 生成测试数据

项目提供了完整的测试数据生成脚本：

```bash
# 生成发票数据（80 条）
python scripts/seed_invoices.py

# 生成风险事件数据（40 条）
python scripts/seed_risk_events.py

# 生成风险案例数据（20 条）
python scripts/seed_risk_cases.py

# 生成银行交易数据（150 条）
python scripts/seed_bank_transactions.py

# 验证数据完整性
python scripts/validate_data.py
```

### Power BI 开发

1. 启动应用：`python app.py`
2. 测试 API：访问 `http://localhost:5000/api/pbi/health`
3. 查看数据：访问 `http://localhost:5000/api/pbi/metrics/daily?format=json`
4. 配置 Power BI Desktop 连接到 Web 数据源

## 许可证

本项目仅供学习和演示使用。

## 联系方式

如有问题，请提交 Issue 或联系项目维护者。
