
---
appliesTo: [backend, fullstack]
loadWhen: [L2, L3, backend, service, api]
fallbackTo: core-lite/delivery-lite.md
---

# 后端通用编码规范（语言无关）

> 适用任何后端（Java/Spring、Go、Node、Python、Rust、.NET）。
> 语言特定补充：见各语言官方风格指南 / 项目内 `.editorconfig`。

---

## 一、命名

| 类型 | 规范 | 示例 |
|---|---|---|
| 包 / 模块 | 全小写、不缩写 | `order` `payment` |
| 类 / 接口 | PascalCase | `OrderService` `PaymentGateway` |
| 方法 / 变量 | camelCase 或 snake_case（按语言） | `createOrder` / `create_order` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| 布尔 | `is`/`has`/`should`/`can` 前缀 | `isActive` `hasPermission` |
| 私有字段 | 按语言习惯 | `_name` 或 `name` |
| 文件名 | 按语言习惯 | `order_service.py` / `OrderService.java` |

**禁止**：
- 拼音命名（`dingdan` ❌）
- 单字母（除循环计数 `i j k`）
- 缩写到看不懂（`usr_lst` ❌ → `userList` ✅）
- 否定布尔（`isNotEnabled` ❌ → `isDisabled` ✅）

---

## 二、分层职责

### 2.1 Controller / Route Handler（入口层）
- **只做**：参数校验、权限注解、调用 Service、组装返回
- **不做**：复杂业务逻辑、直接操作 DB / 外部 API、跨服务编排

### 2.2 Service / Application（应用层）
- 业务规则、状态流转、事务边界
- 幂等校验、权限范围判断
- 跨 Repository 编排
- **可复用计算逻辑**拆到 calculator / helper / strategy 子包

### 2.3 Domain（领域层，可选）
- 领域模型 + 领域规则
- 不依赖任何框架 / DB

### 2.4 Repository / Gateway（基础设施层）
- 数据访问（DB / 外部 API / 文件 / MQ）
- 只做"存取"，不做"决策"
- 跨模块访问对方表 = **禁止**（通过对方 Service / API）

---

## 三、参数校验

### 3.1 入口处必验
所有 HTTP / RPC 入参必须校验：
- 类型（前端传 `"abc"` 你不能直接当 int 用）
- 必填（缺字段立即拒绝）
- 长度 / 范围（手机号 11 位、密码 ≥ 8 位）
- 格式（邮箱、URL、UUID）
- 业务合法性（订单状态是否允许此操作）

### 3.2 Fail Fast
- 校验失败立即返回，不要继续执行
- 错误信息**具体**到字段：`{"field": "email", "msg": "格式不正确"}`

### 3.3 校验位置
- **入口层**：基础校验（类型 / 必填 / 格式）—— 用框架注解
- **Service 层**：业务校验（状态 / 权限 / 范围）—— 手写

---

## 四、错误处理

### 4.1 不吞异常
```python
# 反例
try:
    do_something()
except Exception:
    pass  # 吞了

# 正例
try:
    do_something()
except SpecificError as e:
    logger.warning("...", error=str(e))
    raise UserFacingError("操作失败，请稍后重试")
```

### 4.2 区分错误类型
- **业务错误**：可预期，返回用户友好消息（订单状态不允许、库存不足）
- **系统错误**：不可预期，记录完整 stack，返回通用错误（500）
- **第三方错误**：分类记录（超时 / 拒绝 / 协议错误），决定重试或降级

### 4.3 错误响应
- 用统一错误信封（见 `../contracts/api-contract-standard.md`）
- 错误消息**不泄露**系统细节（不告诉用户 SQL 错了、堆栈是什么）

---

## 五、事务

### 5.1 事务边界
- 一个业务操作 = 一个事务
- 事务范围**最小化**（不含远程调用 / 长时间操作）
- 跨服务用 Saga / TCC / 本地消息表，不用分布式 XA

### 5.2 事务失败
- 默认 rollback，不留中间状态
- 事务内的 DB 写操作必须支持幂等（失败重试不污染）

---

## 六、缓存

### 6.1 缓存策略
- **Cache Aside**（推荐）：读 → 先查缓存，未命中查 DB，回写缓存
- **Write Through**：写 DB 同时写缓存
- **Write Behind**：异步写 DB（高吞吐，但可能丢数据）

### 6.2 缓存陷阱
- **缓存穿透**：查不存在的 key → 用空值缓存 / 布隆过滤器
- **缓存击穿**：热 key 过期 → 互斥锁 / 永不过期 + 异步刷新
- **缓存雪崩**：大量 key 同时过期 → 过期时间加随机抖动

### 6.3 缓存失效
- 改包名 / 类名后**必须清缓存**（否则反序列化失败）
- 缓存 key 设计含版本前缀（`v2:user:123`），方便整体失效

---

## 七、并发

### 7.1 共享状态
- 默认无状态，避免共享可变状态
- 必须共享时用：原子操作 / 锁 / 通道 / actor 模型
- 锁粒度**最小化**，避免大锁

### 7.2 幂等
- 写操作必须可重试不产生副作用
- 实现方式：唯一约束 / 状态机 / 版本号 / 分布式锁

### 7.3 异步
- IO 密集用异步（async/await / goroutine / coroutine）
- 异步任务**可观测**（进度、状态、失败原因）
- 异步任务**可重试**（指数退避、最大次数）

---

## 八、性能

### 8.1 查询
- 禁止 N+1（用 JOIN / IN / 批量预加载）
- 大查询分页（必有 LIMIT）
- 慢查询监控（> 100ms 记录）

### 8.2 资源
- 连接池大小合理
- 文件 / 网络流用完即关
- 大对象用流式处理，不一次性加载到内存

### 8.3 不做过度优化
- YAGNI 原则：性能问题没出现就别提前优化
- 优化前先 profile，找到真瓶颈

---

## 九、代码风格

### 9.1 文件大小
- 文件 200-400 行为宜，**800 行硬上限**
- 函数 50 行为宜，**100 行硬上限**
- 嵌套 ≤ 4 层，超过用 early return

### 9.2 不可变性
- 默认不可变（const / final / readonly）
- 必须可变时，集中变更点，避免散布

### 9.3 注释
- **默认不写注释**（好命名 + 简单逻辑自解释）
- 必须写注释的场景：
  - 隐藏约束（"这里必须先 lock 再 query，否则...")
  - 反直觉的 workaround（"框架 bug，等升级到 vX 修复"）
  - 业务规则的非显然来源（"按财务 PRD 第 3.2 节"）
- **不**写废话注释（`// 创建订单` 在 `createOrder()` 上）

---

## 十、后端 Review 清单

提交 MR 前自检：

- [ ] 命名清晰、无拼音、无单字母
- [ ] 函数 < 50 行、文件 < 800 行、嵌套 < 4 层
- [ ] 入参校验完整（类型 / 必填 / 范围 / 业务）
- [ ] 错误处理完整（不吞异常、错误信息友好）
- [ ] 事务边界合理
- [ ] 写操作幂等
- [ ] 无 N+1 查询、无未分页大查询
- [ ] 缓存 key 设计合理、有失效策略
- [ ] 日志结构化、含 trace_id、不泄露敏感信息
- [ ] 无硬编码 ID / 密钥 / 阈值
- [ ] 单元测试覆盖核心逻辑
- [ ] 无"为通过编译注释掉逻辑"的痕迹

---

## 十一、已知陷阱（JVM / Spring）

### 11.1 Maven BOM 依赖管理
- **现象**：本地能跑、CI 跑不起来（或反之）
- **原因**：父 POM `<dependencyManagement>` 中的 BOM 版本与子模块实际依赖版本不一致，或 `mvn dependency:tree` 看到的传递依赖版本与预期不符
- **解决**：每次改依赖立即 commit `pom.xml`；CI 校验 `mvn dependency:tree` 一致性

### 11.2 SPI / 反射 / 注解处理器
- **现象**：编译通过但运行时报 `ServiceConfigurationError` / `ClassNotFoundException` / 注解不生效
- **原因**：SPI 的 `META-INF/services` 文件未更新；注解处理器未注册；反射调用的类被混淆或移除
- **解决**：改包名/类名后全局搜索 `META-INF/services` 和 `@AutoService` 注册；注解处理器用 `annotationProcessor` scope 声明
