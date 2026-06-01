# DeepAudit

DeepAudit 是一个面向企业财务审计、费用风控和票据核验场景的智能审计系统。项目基于 Flask 构建，提供发票上传识别、单据核验、风险规则识别、审批流转、审计留痕、台账管理和后台权限治理等能力，适合作为内部审计、财务合规和税务风险预警平台的原型。

## 功能特性

- 发票图片和 PDF 上传、OCR 识别与结构化处理
- 发票验真、税务核验和 mock / real provider 模式切换
- 重复报销、异常付款、字段不一致等风险规则识别
- 审批中心、审计工作台、状态流转和多角色处理
- 审计链路、操作日志和关键动作追踪
- 用户、角色、权限、数据范围等 IAM 管理
- 风险案例、监控看板、知识中心和企业集成扩展模块

## 技术栈

- Python 3.10+
- Flask
- SQLAlchemy / Flask-SQLAlchemy
- SQLite 默认本地数据库，可通过 `DATABASE_URL` 切换
- Jinja2 + Bootstrap

## 项目结构

```text
core/              应用工厂、扩展初始化、配置和日志
routes/            页面路由和 API 路由
services/          审批、台账、风控、集成等业务服务
integrations/      税务、银行、ERP、OA 等外部集成适配
providers/         数据 provider 抽象和 mock 实现
models/            数据模型
templates/         Jinja2 页面模板
static/            前端静态资源
scripts/           数据库初始化脚本
data/              mock 数据
```

## 快速开始

1. 创建虚拟环境并安装依赖：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. 创建本地环境配置：

```bash
copy .env.example .env
```

至少需要配置：

```env
SECRET_KEY=replace-with-a-random-secret-key
```

本地开发可以保持 `DATA_PROVIDER=mock`。如果需要调用真实 OCR、LLM 或税务服务，请在 `.env` 中配置相应 API Key 和 provider 参数。

3. 初始化数据库：

```bash
python scripts/init_db_keep_admin01.py --yes
```

4. 启动应用：

```bash
python app.py
```

默认访问地址：

```text
http://127.0.0.1:5000
```

## 常用命令

```bash
# 启动应用
python app.py
```

## 配置说明

主要环境变量：

- `SECRET_KEY`：Flask 会话密钥，生产环境必须使用强随机值
- `DATABASE_URL`：数据库连接，默认 `sqlite:///database.db`
- `DATA_PROVIDER`：数据源模式，支持 `mock` / `real`
- `ENABLE_CSRF_PROTECTION`：是否启用 CSRF 防护
- `DASHSCOPE_API_KEY`：DashScope / Qwen 相关能力的 API Key
- `LLM_MODEL_NAME`：LLM 模型名称，默认 `qwen-turbo`
- `FLASK_HOST`、`FLASK_PORT`、`FLASK_DEBUG`：本地服务配置

## 上传到 GitHub 前的注意事项

仓库已配置 `.gitignore`，默认不会提交以下本地文件：

- `.env`、`.env.production`、`.secrets/`
- `.venv/`、`venv/` 等虚拟环境
- `database.db`、`*.sqlite3` 等本地数据库
- `uploads/` 中的上传文件，保留 `uploads/.gitkeep`
- `instance/`、日志、缓存、测试截图和 HTML 产物

推送前建议检查：

```bash
git status --short
git remote -v
```

目标仓库：

```text
https://github.com/xchen1012a-sketch/DeepAudit
```

## License

MIT
