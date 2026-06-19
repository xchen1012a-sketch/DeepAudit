# 业务快速参考（AI 实时维护）

> 日常启动唯一入口：已接入项目的普通会话先读本文件，不读 `AI-START.md` 全文。
> 状态: TEMPLATE_PLACEHOLDER
> dailyEntry: true
> dynamicContextGate: true
> projectSize: auto
> sizeStrategy: auto
> 生成后改为 GENERATED；只有 GENERATED 才能作为快速恢复入口。TEMPLATE_PLACEHOLDER 只能说明项目尚未完成业务摘要生成。
> 来源：由 `business-rules.md` 和 `project-map.md` 浓缩生成；业务规则变更时同步更新。

---

## 项目定位

- 一句话定位：（待生成）
- 项目类型：（待生成）
- 项目规模：auto
- 规模策略：auto
- 主要入口：（待生成）

## 核心业务域（≤5 个）

| 业务域 | 一句话说明 | 涉及模块 |
|---|---|---|
| （待填充） |  |  |

## 关键不变量（≤5 条）

- （待填充）

## 动态上下文门禁

| 任务等级 | 默认读取 | 升级条件 |
|---|---|---|
| L0 状态确认/简单问答 | 仅本文件 | 定位不清时读 `business/project-map.md` |
| L1 机械/文案/样式小改 | 本文件 + 命中文件片段 | 影响行为时升 L2 |
| L2 简单代码改动 | 本文件 + `core-lite/delivery-lite.md` + 相关源码 | 涉及安全/测试时加对应 core-lite |
| L3 业务/API/权限/数据 | 本文件 + `business/business-rules.md` + 相关 contracts/core | 命中高风险即读完整规范 |
| L4 接入/审计/重构 | `AI-START.md` + 必要规范 | 用户明确要求完整分析 |
