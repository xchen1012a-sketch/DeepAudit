---
appliesTo: [frontend, backend, fullstack, mobile, cli, library-sdk, data-platform, ai-llm, generic]
loadWhen: [L2, simple-change, validation]
fallbackTo: core/testing-standard.md
---

# 轻量验证规则

用于小改动的最低验证策略。需要质量门禁、覆盖率、端到端链路时读取完整 `core/testing-standard.md`。

## 验证选择

- 文案/样式：检查目标文件 diff，必要时截图或运行 UI。
- 配置常量：运行相关 lint/typecheck/build，或说明为何不可运行。
- 局部 Bug：优先运行最小相关测试；没有测试时给出可复现检查。
- 重构：至少运行受影响模块测试或静态检查。

## 交付说明

- 写明验证命令和真实结果。
- 写明未跑的测试及原因。
- 不用“未验证但看起来没问题”冒充完成。
