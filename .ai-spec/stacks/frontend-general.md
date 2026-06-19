
---
appliesTo: [frontend, fullstack]
loadWhen: [L2, L3, frontend, ui, browser]
fallbackTo: core-lite/delivery-lite.md
---

# 前端通用编码规范（框架无关）

> 适用 React / Vue / Svelte / Solid / Angular。
> 框架特定补充：见各框架官方风格指南。

---

## 一、命名

| 类型 | 规范 | 示例 |
|---|---|---|
| 组件 | PascalCase | `OrderCard` `UserAvatar` |
| Hook / composable | camelCase + `use` 前缀 | `useOrder` `useAuth` |
| 工具函数 | camelCase | `formatDate` `parseQuery` |
| 常量 | UPPER_SNAKE_CASE | `MAX_FILE_SIZE` |
| CSS class | kebab-case 或 BEM | `order-card` `order-card__title` |
| 事件 handler | `on` + Subject + Action | `onOrderClick` `onUserSubmit` |
| 布尔 | `is`/`has`/`should`/`can` 前缀 | `isLoading` `hasError` |

---

## 二、组件设计

### 2.1 单一职责
- 一个组件只做一件事
- 同时承担"展示 + 数据 + 业务"的组件**必须拆**

### 2.2 组件分层

```
Container（容器组件）
  - 拿数据（fetch / query）
  - 管状态
  - 处理副作用
    ↓ props
Presentational（展示组件）
  - 纯渲染
  - 不拿数据
  - props 进、event 出
```

### 2.3 组件大小
- 单组件 < 200 行
- 超过就拆（子组件 / hooks / utils）

### 2.4 Props 设计
- Props 数量 ≤ 6 为宜，超过考虑聚合
- 必填 / 可选明确（TypeScript / PropTypes）
- Props 命名具体（`color` ❌ → `backgroundColor` / `textColor` ✅）

---

## 三、状态管理

### 3.1 状态分类

| 类型 | 工具 |
|---|---|
| **服务端状态** | TanStack Query / SWR / tRPC / Apollo |
| **客户端状态（全局）** | Zustand / Jotai / Redux Toolkit / Pinia |
| **URL 状态** | search params / route segments |
| **表单状态** | React Hook Form / VeeValidate / Formik |
| **局部 UI 状态** | useState / ref |

### 3.2 状态管理原则
- **不**把服务端数据复制到客户端 store（用 query 缓存即可）
- **不**派生冗余状态（能用现有数据算出来的不另存）
- URL 能装的状态就用 URL（刷新可恢复、可分享）
- 表单状态独立，不和全局状态混

---

## 四、数据获取

### 4.1 Stale-While-Revalidate
- 优先用框架内置的 SWR 策略（TanStack Query / SWR）
- 不要手写 fetch + useEffect + useState（坑多）

### 4.2 乐观更新
- 用户操作立即更新 UI
- 失败回滚 + 提示
- 例：点赞 → 立即 +1 → 失败回滚 -1 + toast

### 4.3 并行加载
- 独立数据**并行**请求，不要瀑布
- 用 `Promise.all` 或框架并行 query

### 4.4 加载 / 错误 / 空
每个数据展示必须有：
- **加载中**（骨架屏 / spinner）
- **错误**（重试按钮）
- **空数据**（友好提示，不是白屏）
- **数据**（实际内容）

---

## 五、性能

### 5.1 渲染优化
- 列表用 stable `key`
- 重计算用 memo（`useMemo` / `computed`）
- 重渲染用 callback memo（`useCallback` / `useCallback`）
- **不过度优化**——profile 找到真瓶颈

### 5.2 包大小
- 路由级懒加载（`React.lazy` / `defineAsyncComponent`）
- 大库按需引入（`import { debounce } from 'lodash-es'`）
- 监控 bundle size（CI 设预算）

### 5.3 资源
- 图片显式 `width` `height`（避免 CLS）
- 首屏图片 `loading="eager"` + `fetchpriority="high"`
- 非首屏 `loading="lazy"`
- 图片格式 WebP / AVIF + 降级

---

## 六、可访问性（a11y）

### 6.1 语义化
```html
<header><nav>...</nav></header>
<main>
  <section aria-labelledby="hero-h"><h1 id="hero-h">...</h1></section>
</main>
<footer>...</footer>
```
- 不用 `<div>` 替代语义元素
- 标题层级不跳（h1 → h2，不要 h1 → h3）

### 6.2 键盘导航
- 所有交互元素可 tab 到
- 焦点可见（`focus-visible` 样式）
- 模态框有焦点陷阱
- `Esc` 关闭模态 / 下拉

### 6.3 屏幕阅读器
- 图片有 `alt`（装饰性 `alt=""`）
- 表单有 `label`
- 错误用 `aria-live` 播报
- 图标按钮有 `aria-label`

---

## 七、表单

### 7.1 校验
- 客户端校验 + 服务端校验（客户端是体验，服务端是安全）
- 错误显示在字段下方
- 提交时禁用按钮防重复

### 7.2 体验
- 必填字段标记
- 密码强度提示
- 自动完成（`autocomplete` 属性）
- 大表单分步（wizard）

---

## 八、安全

### 8.1 XSS 防护
- 默认框架会转义（React `{value}` / Vue `{{ value }}`）
- 禁止 `dangerouslySetInnerHTML` / `v-html` 未净化使用
- 必须用 → 用 DOMPurify 净化

### 8.2 CSRF
- 写操作用 Token / SameSite Cookie

### 8.3 敏感数据
- 密码不明文显示
- 手机号 / 身份证默认脱敏（138****1234）
- 错误消息不泄露后端细节

### 8.4 第三方脚本
- 异步加载
- 用 SRI（subresource integrity）
- 定期审计

---

## 九、样式

### 9.1 方案选择
- **Tailwind / utility-first**：快速、一致
- **CSS Modules**：组件隔离
- **CSS-in-JS**（Emotion / styled-components）：动态样式
- **原生 CSS + BEM**：简单项目

选一种主用，不要混。

### 9.2 设计 token
- 颜色、间距、字号定义为变量（CSS custom properties / Tailwind config）
- 不在组件内硬编码 `color: #3b82f6`

### 9.3 响应式
- mobile-first
- 断点：sm 640 / md 768 / lg 1024 / xl 1280 / 2xl 1536
- 测试 320 / 768 / 1024 / 1440 / 1920

---

## 十、前端 Review 清单

- [ ] 组件职责单一、< 200 行
- [ ] Props 数量合理、命名具体
- [ ] 加载 / 错误 / 空 三态都有
- [ ] 列表有 stable key
- [ ] 表单有客户端校验 + 错误显示
- [ ] 所有交互可键盘操作
- [ ] 图片有 width/height + alt
- [ ] 无 XSS 风险（无未净化 v-html / dangerouslySetInnerHTML）
- [ ] 路由懒加载
- [ ] 设计 token 已用（无硬编码颜色 / 字号）
- [ ] 响应式至少测过 3 个断点
- [ ] 控制台无 warning / error
