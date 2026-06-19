# AI 双工具全栈开发操作手册

> 本手册是给人看的操作说明，不是新的规则源。真正规则源是各子项目的 `.ai-spec/README.md`。

## 1. 一句话理解

AI 工具只是执行者，不是项目状态源。真正稳定项目开发的是：

```text
Git 分支 + .ai-spec 规范 + docs/contracts 接口契约 + Handoff 交接记录 + 验证结果
```

一个 AI 不能继续时，另一个 AI 不接聊天记忆，而是接可读取的文件和 Git 状态。

## 2. 目录角色

```text
workspace/              # 全栈工作区，只做协调，不做 Git 提交
├── CLAUDE.md / AGENTS.md  # AI 入口
├── backend/            # 后端独立 git 仓库
└── frontend/           # 前端独立 git 仓库
```

关键原则：
- 父目录只做全栈协调，**禁止**在父目录执行 `git add` / `git commit` / `git push`
- 后端 Git 操作只在 `backend/` 执行
- 前端 Git 操作只在 `frontend/` 执行

## 3. AI 分工建议

| 场景 | 推荐工具 |
|---|---|
| 业务方案、架构拆解、接口契约初稿 | Claude |
| 代码实现、修 bug、验证、提交整理 | Codex |
| Claude 额度不足 | Codex 根据 Handoff 接手 |
| Codex 遇到复杂业务判断 | Claude 根据 Handoff 接手 |

无论哪个 AI 开发，都必须遵守 `.ai-spec`。

## 4. 标准全栈开发流程

### 第一步：先读规范，不改代码

```text
这是全栈任务。请先读取各子项目的 AI 入口和 .ai-spec/README.md。
不要改代码，先分析后端/前端落点、接口契约、权限码、风险和验证方式。
```

### 第二步：先定接口契约

```text
先进入契约阶段，不要改代码。
请输出接口契约：路径、方法、请求参数、响应字段、错误码、权限码、
数据库影响、前端页面落点、验证方式。
```

契约放在：`backend/docs/contracts/{feature}.md` 和 `frontend/docs/contracts/{feature}.md`

### 第三步：后端先实现

```text
按已确认契约实现后端第一阶段。
只改 backend/，不改前端。
遵守 backend/.ai-spec。
完成后给出验证结果、未验证内容、风险和回滚方案。
```

### 第四步：前端再适配

```text
按后端契约适配前端页面和 API。
只改 frontend/，不改后端。
写 API 前先对齐接口文档。
完成后给出 build/lint/联调结果、未验证内容、风险和回滚方案。
```

### 第五步：真实联调

```text
进行真实后端联调，不要使用 mock 作为完成依据。
检查接口字段、权限码、菜单、页面进入、浏览器 console。
```

### 第六步：分仓提交

全栈任务前后端使用同名分支：`feature/xxx`

### 第七步：创建 MR

固定顺序：后端 MR → 前端 MR，两个 MR 互相引用，后端先合，前端后合。

## 5. AI 切换流程

### 当前 AI 停手前

```text
请根据 Handoff 模板生成本阶段交接记录。
写清当前分支、已完成内容、修改文件、接口契约、权限码、
验证结果、未验证风险、回滚方案和下一步。
不要继续改代码。
```

全栈任务后端和前端分别写：`backend/docs/handoff-{feature}.md` / `frontend/docs/handoff-{feature}.md`

### 新 AI 接手时

```text
请先读取 AI 入口、.ai-spec/README.md、相关 docs/contracts 和 Handoff。
不要改代码，先执行 git status，确认当前分支、未提交文件、已完成内容、剩余 TODO 和风险。
```

接手后第一步不是写代码，而是确认状态。

## 6. Handoff 必须写清

```text
Task：任务目标
Repo / Branch：仓库和分支
Current State：已完成内容
Contract：接口、请求、响应、错误码、权限码
Modified Files：修改文件
Remaining TODO：剩余任务
Verification：已验证 / 未验证
Risks：风险
Rollback：回滚方案
Next AI Instruction：下个 AI 第一件事
```

有未提交改动时额外写清：哪些文件完整 / 未完成 / 不要提交 / 下一步应先检查什么。

## 7. 常用指令模板

### 只分析，不改代码

```text
先读取相关 AI 入口和 .ai-spec，不要改代码。
请分析需求落点、涉及文件、接口契约、权限码、风险和验证方式。
```

### 后端开发

```text
只改 backend/。遵守 backend/.ai-spec。不要改前端。
完成后给出验证、未验证、风险、回滚。
```

### 前端开发

```text
只改 frontend/。遵守 frontend/.ai-spec。不要改后端。
完成后给出 build/lint/联调结果、未验证、风险、回滚。
```

### 全栈开发

```text
这是全栈任务。先定契约，不要直接写代码。
后端和前端按两个独立 git 仓库处理。
父目录只做协调，不允许在父目录做 git 操作。
```

### 提交前检查

```text
请分别检查各子项目的 git status。
确认每个文件的归属仓库，不要在父目录提交。
```

## 8. 高风险动作必须先确认

遇到以下事项，AI 必须先停下来说明方案，等人确认：

- 修改 KPI、财务、客户归属、订单统计口径
- 修改登录、认证、权限、数据权限
- 删除表、删字段、清空数据
- 操作生产数据库或生产服务器
- 修改核心框架或共享包
- 新增生产依赖
- 批量发送消息或批量写入数据
- push / 创建 MR / 执行部署

## 9. 完成定义

一个任务不能只说"完成了"，必须满足：

```text
代码改动完成
契约同步完成
权限码说明清楚
数据库影响说明清楚
验证命令执行并记录结果
未验证内容说明原因和风险
回滚方案明确
前后端 Git 状态清楚
必要时 Handoff 已生成
```

## 10. 最重要的使用习惯

每次对 AI 下开发指令，都带上这句话：

```text
严格遵守 .ai-spec。先读规范和相关代码，不要发散，不改无关文件。
按契约先行、小步实施、真实验证、分仓提交、交付报告的流程完成。
```

## 11. 多 AI 并行协作

允许多个 AI 同时开发，但**禁止同时改同一个文件**。

### 如何让 AI 发现对方

AI 改代码前会自动检查 `.ai-spec/sessions/` 目录（协议见 `AI-START.md §1.7`）。每个活跃的 AI 会在这里留一个 session 文件，声明自己正在改哪些文件。

### 推荐工作方式

```text
# 同时启动两个 AI，分别开发不同模块：

窗口 A（Claude）：
  只改 backend/src/service/PaymentService.java 和 PaymentController.java
  不要碰订单模块的任何文件

窗口 B（Codex）：
  只改 backend/src/service/OrderService.java 和 OrderController.java
  不要碰支付模块的任何文件
```

### 冲突时怎么办

如果一个 AI 报告文件冲突，说明另一个 AI 正在改那些文件。你需要：
- 等对方完成后再继续
- 或者手动删除 `.ai-spec/sessions/` 中对端文件（确认对方已停止后）
- 或者缩小自己的范围，只改未被占用的文件

### 文件结构

```text
.ai-spec/sessions/
├── claude-code-20260619T153000.md   # Claude 的活跃声明
└── codex-20260619T153500.md         # Codex 的活跃声明
```

这些文件不入 git，是纯运行时的协调标记。
