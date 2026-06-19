
---
appliesTo: [frontend, backend, fullstack, mobile, cli, library-sdk, data-platform, ai-llm, generic]
loadWhen: [L3, testing, coverage, quality-gate, ci]
fallbackTo: core-lite/testing-lite.md
---

# 测试规范

> 测试不是可选项。没有测试的代码无法安全重构，无法验证交付。

---

## 一、测试金字塔

```
            /\
           /  \           E2E（少量，慢，覆盖关键流程）
          /----\
         /      \         集成测试（适量，覆盖 API + DB）
        /--------\
       /          \       单元测试（大量，快，覆盖业务逻辑）
      /____________\
```

| 层级 | 占比 | 速度 | 覆盖什么 |
|---|---|---|---|
| 单元测试 | ≥ 70% | 毫秒级 | 函数 / 类 / 纯业务逻辑 |
| 集成测试 | ≈ 20% | 秒级 | API + 真实 DB / 真实组件 |
| E2E 测试 | ≤ 10% | 分钟级 | 关键用户流程（登录、下单、审批） |

**比例反了是反模式**（大量 E2E + 少量单元 → 又慢又脆）。

---

## 二、覆盖率门槛

| 代码类型 | 建议目标（最终以 `ai-spec.yaml` 为准） |
|---|---|
| 业务核心（订单、支付、KPI、权限） | 高覆盖 + 关键不变量、边界和故障路径测试 |
| 一般业务 | 风险驱动，由项目设定覆盖率目标 |
| 工具 / 辅助 | 优先覆盖公共行为和历史缺陷 |
| 入口层（Controller / Route） | 由集成测试覆盖 |
| 整体合并门槛 | 新项目可设较高基线；老项目采用不恶化基线 + 变更代码覆盖目标 |

> 覆盖率只是风险信号，不等于测试质量。低覆盖率需要解释和补偿控制，不能单独证明代码质量差。

---

## 三、AAA 模式（测试结构）

```typescript
test('returns empty array when no orders match filter', async () => {
  // Arrange（准备）
  const filter = { status: 'shipped', dateFrom: '2026-01-01' };

  // Act（执行）
  const result = await orderService.list(filter);

  // Assert（断言）
  expect(result).toEqual([]);
});
```

---

## 四、测试命名（描述行为，不描述实现）

**好命名**（说行为）：
- `returns empty array when no orders match filter`
- `throws when user lacks permission`
- `falls back to cache when DB is unavailable`

**坏命名**（说实现）：
- `test1` / `testOrder`
- `works correctly`（什么叫 correctly？）
- `test the function`（哪个 function？）

---

## 五、TDD 流程（推荐用于新功能 / Bug 修复）

1. **RED**：写一个失败的测试，描述期望行为
2. **GREEN**：写最少代码让测试通过
3. **REFACTOR**：在不改行为前提下优化代码
4. 重复

> 可稳定复现的 Bug 应先写失败测试，再修复并保留回归测试。无法自动复现时记录原因，并提供可重复的替代验证步骤。

---

## 六、测试隔离

- 每个测试**独立可运行**，不依赖其它测试的执行顺序
- 每个测试**自己准备自己的数据**（setup / teardown）
- 测试间**不共享可变状态**
- 集成测试用**事务回滚**或**独立 schema** 隔离，不留垃圾数据

---

## 七、禁止事项

- **不**为通过测试而 mock 掉业务逻辑（mock 边界，不 mock 内部）
- **不**写"永远通过"的测试（`expect(true).toBe(true)`）
- **不**在测试里硬编码时间（`new Date()` → 用 clock mock）
- **不**依赖外部网络（外部 API 必须用 mock server / VCR）
- **不**测试私有实现（测公共行为，不测内部方法）
- **不**为覆盖率写无意义测试（每个测试必须有断言价值）

---

## 八、测试数据

- 用 fixture / factory 生成，不手写大块 JSON
- 敏感数据（手机号 / 身份证 / 密码）**用假数据**，不复制真实用户
- 大数据量测试用 in-memory DB 或 testcontainers，不依赖生产数据快照

---

## 九、CI 中的测试

- 每个 MR/PR 必须跑受影响测试；高风险改动、发布候选或项目配置要求时跑全量测试
- 测试失败**阻塞合并**（不强制通过）
- E2E 可单独 job 跑，允许有条件 retry（≤ 2 次）
- 失败的测试必须**立即修**或** quarantine**（带 issue 编号），不允许删

---

## 十、测试 Review 清单

提交 MR 前自检：

- [ ] 新功能有对应测试
- [ ] 测试覆盖正常路径 + 至少一个边界（空 / 越界 / 异常）
- [ ] 测试命名描述行为，不描述实现
- [ ] 测试独立可运行（不依赖顺序）
- [ ] 覆盖率不低于门槛
- [ ] 没有"永远通过"的空测试
- [ ] 测试速度符合项目基线；慢测试已分层并可观测
