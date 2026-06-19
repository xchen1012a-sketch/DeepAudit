---
appliesTo: [frontend, backend, fullstack, mobile, cli, library-sdk, data-platform, ai-llm, generic]
loadWhen: [L2, simple-change, delivery]
fallbackTo: core/delivery-standard.md
---

# 轻量交付规则

用于小改动、局部 Bug 修复、视觉/文案/配置调整。若涉及业务规则、API、权限、数据迁移、安全边界，升级读取完整规范。

## 最低要求

- 说明改了什么，范围控制在哪些文件。
- 给出实际验证命令或可复查的检查方式。
- 明确未验证项，不用“应该可以”代替结果。
- 给出回滚方式：还原文件、撤销配置、或回退分支。

## 不需要升级的例子

- typo、注释、格式化。
- 单个按钮文案、颜色、间距、图标替换。
- 不改变行为的常量命名或小范围重命名。

## 必须升级的例子

- 业务逻辑、状态机、金额、库存、KPI。
- API schema、事件、权限、认证、租户、数据范围。
- 数据库 schema、迁移、批量写入。
