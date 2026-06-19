# AI 工具适配器

`AI-START.md` 是唯一规范入口。适配器只解决不同工具的自动发现方式，不复制安全、架构、测试或交付规则。

## 当前适配

| 工具 | 模板 | 推荐落点 |
|---|---|---|
| Claude Code | `claude-code/CLAUDE.md.template` | 项目根 `CLAUDE.md` |
| Claude Code 权限 | `claude-code/settings.json.template` | `.claude/settings.json`，合并前逐项审查 |
| Codex | `codex/AGENTS.md.template` | 项目根 `AGENTS.md` |
| Cursor | `cursor/ai-spec.mdc.template` | `.cursor/rules/ai-spec.mdc` |
| GitHub Copilot | `github-copilot/copilot-instructions.md.template` | `.github/copilot-instructions.md` |
| 其它工具 | `generic/START-PROMPT.md` | 直接作为启动提示词 |

## 兼容规则

- 安装前检查目标文件是否存在；存在则语义合并，不覆盖。
- 工具版本改变自动发现格式时，只更新适配器，不修改规范内核。
- 未列出的工具直接读取 `AI-START.md`，不得因为没有专用适配器而拒绝接入。
- Skills 的权威源是 `skills/<name>/SKILL.md`。按工具需要复制或链接到其项目级 Skill 目录。
- 权限配置不得简单取并集；新增权限必须逐项说明能力和风险。

