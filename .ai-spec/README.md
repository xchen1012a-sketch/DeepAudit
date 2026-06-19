# SpecForge

SpecForge 是一套 AI 项目协作规范模板，核心目标是：**让 AI 按需读取上下文，而不是每次小改动都从头读完整项目。**

它适合 Claude Code、Codex、Cursor、Copilot、Windsurf、Cline、Aider、Gemini 等能读取项目文件的 AI 工具。

## 核心亮点

- **动态省 token**：日常优先读 `business/quick-ref.md`，复杂任务才升级读取更多规范。
- **按任务风险加载**：L0-L4 控制上下文范围，小改动不加载完整规范。
- **按项目大小匹配**：tiny / small / medium / large / enterprise 自动选择加载策略。
- **轻量核心规范**：`core-lite/` 处理简单任务，避免常驻大文档。
- **完整工程约束**：高风险任务按需加载 `core/`、`contracts/`、`stacks/`。
- **接入时自动瘦身**：根据项目结构裁剪业务规则、技术栈规范和无关章节。
- **多项目版本同步**：父目录 `.specforge.json` 和子项目 `ai-spec.yaml` 记录 `templateVersion`，可用 `-Sync` 更新核心规范。
- **安全提交门禁**：提交前必须检查暂存区，过滤 `.env`、IDE 配置、本地设置、构建产物和真实凭证。

## 动态加载策略

| 场景 | 默认读取 |
| --- | --- |
| 快速恢复 / 状态确认 | `quick-ref.md` |
| 文案、样式、局部小改 | `quick-ref.md` + 目标文件 |
| 普通功能改动 | `quick-ref.md` + `project-map.md` + `core-lite/` |
| API / 权限 / 数据 / 跨端 | 按需加载 `core/`、`contracts/`、`stacks/` |
| 首次接入 / 审计 / 重构规划 | 允许完整扫描，但必须说明原因 |

## 快速安装

在目标项目根目录执行：

PowerShell：

```powershell
git clone https://github.com/xchen1012a-sketch/SpecForge.git .ai-spec; Remove-Item -Recurse -Force .ai-spec/.git
```

Bash：

```bash
git clone https://github.com/xchen1012a-sketch/SpecForge.git .ai-spec && rm -rf .ai-spec/.git
```

然后对 AI 说：

```text
请读取 .ai-spec/AI-START.md，并严格按启动协议接入当前项目。先完成只读识别和启动报告，不要直接修改业务代码。
```

## 安装器

安全复制，不覆盖已有文件：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -TargetRoot <项目目录> -Tools codex -Apply
```

完整接入，包含项目识别、quick-ref 初始化、多项目处理和动态瘦身：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -TargetRoot <项目目录> -Tools codex -Onboard -Apply
```

需要 Git 分支 / 初始基线 commit 时，显式开启：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -TargetRoot <项目目录> -Tools codex -Onboard -ManageGit -Apply
```

同步已安装项目的核心规范：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -TargetRoot <项目目录或父目录> -Sync -Apply
```

## 验证

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate.ps1
```

验证覆盖结构、链接、Skill 格式、动态路由 frontmatter、安装器行为和 Git 提交门禁。

## 详细文档

- [AI-START.md](AI-START.md)
- [使用指南](docs/使用指南.md)
- [配置示例](ai-spec.example.yaml)
