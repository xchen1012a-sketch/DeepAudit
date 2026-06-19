# 移动端通用编码规范

> 适用 iOS / Android / React Native / Flutter / Kotlin Multiplatform / Swift Multiplatform。
> 框架特定补充：见各平台官方指南。

---

## 一、命名

| 类型 | 规范 |
|---|---|
| 类 / 接口 | PascalCase |
| 方法 / 变量 | camelCase |
| 常量 | UPPER_SNAKE_CASE |
| 资源文件 | snake_case（Android） / kebab-case（iOS） |
| 包 / module | 全小写 |

---

## 二、架构

### 2.1 推荐分层

```
UI（View / Composable / Widget）
  ↓ 不含业务逻辑
ViewModel / Presenter / Bloc
  ↓ 状态管理 + 业务编排
UseCase / Interactor
  ↓ 单一业务能力
Repository
  ↓ 数据访问抽象
DataSource（Remote / Local / Cache）
```

### 2.2 推荐模式
- iOS：**MVVM + Combine** / **TCA**（The Composable Architecture）
- Android：**MVVM + Flow** / **MVI**
- Flutter：**BLoC** / **Riverpod** / **Provider**
- React Native：**Zustand** / **Redux Toolkit**

### 2.3 禁止
- UI 层直接调网络 / DB
- UI 层硬编码业务规则
- ViewModel 持有 View 引用（防内存泄漏）

---

## 三、状态管理

- 单一数据源（Single Source of Truth）
- UI 是状态的映射（`UI = f(state)`）
- 状态变更可追溯（时间旅行调试）
- 不同生命周期：
  - UI 状态（按钮点击）→ 局部
  - 业务状态（用户登录）→ 全局
  - 持久状态（设置）→ 本地存储

---

## 四、性能

### 4.1 列表
- 长列表用虚拟化（RecyclerView / LazyColumn / LazyVStack / ListView.builder）
- 列表项 stable key
- 复杂列表项做差异比较（DiffUtil / equatable）

### 4.2 渲染
- 60 FPS 目标（避免卡顿）
- 重计算用 memo
- 图片用 cache + 占位 + 渐进式加载
- 避免在 build / render 周期做重活

### 4.3 启动
- 冷启动 ≤ 2 秒
- 延迟初始化非首屏依赖
- 启动阶段不做 IO

### 4.4 包大小
- iOS： ≤ 50 MB（蜂窝下载限制）
- Android： ≤ 100 MB（Play 限制）
- 用 App Bundle / App Thinning 减包

---

## 五、网络

### 5.1 必有
- 超时（连接 / 读 / 写）
- 重试（指数退避、最大次数）
- 缓存（HTTP cache + 离线缓存）
- 错误分类（网络 / 服务端 / 业务）

### 5.2 离线
- 弱网 / 断网可降级
- 写操作支持队列重试（用户操作先存本地，恢复后同步）

---

## 六、本地存储

| 数据类型 | 工具 |
|---|---|
| 简单 K-V | SharedPreferences / UserDefaults / MMKV |
| 结构化 | SQLite / Room / CoreData / Realm |
| 文件 | 沙盒 / Documents 目录 |
| 敏感（Token） | Keychain（iOS）/ Keystore（Android）/ Secure Storage |

**敏感数据禁止明文存 SharedPreferences**。

---

## 七、安全

### 7.1 反编译防护
- 代码混淆（ProGuard / R8 / Flutter obfuscate）
- 敏感逻辑下沉后端，不在客户端
- 不在客户端硬编码 API Secret

### 7.2 通信
- 强制 HTTPS（ATS / Network Security Config）
- 证书绑定（高安全场景）
- API 签名防篡改

### 7.3 设备
- 越狱 / Root 检测（金融类）
- 防截屏（密码输入界面）
- 不在系统剪贴板留敏感数据

### 7.4 用户隐私
- 权限按需申请（用前才弹）
- 摄像头 / 麦克风 / 位置等明确告知用途
- 隐私政策可见

---

## 八、用户体验

### 8.1 启动体验
- 启动屏 ≤ 1 秒
- 首屏数据用骨架屏，不空白
- 失败可重试

### 8.2 反馈
- 按钮点击有反馈（动画 / 触感）
- 加载中显示 loading
- 错误用 toast / 对话框，不崩溃

### 8.3 手势
- 左滑返回（iOS）/ 系统返回键（Android）
- 模态可下滑关闭
- 列表支持下拉刷新 + 上拉加载

### 8.4 通知
- 推送需用户授权
- 静默推送不滥用
- 通知有深度链接

---

## 九、平台适配

### 9.1 iOS
- 适配深色模式 / 浅色模式
- SafeArea（刘海 / 底部条）
- 不同屏幕尺寸（iPhone SE → iPad）
- Dynamic Type（字体大小）

### 9.2 Android
- 适配 Material You / 动态颜色
- 系统返回手势 / 三按钮
- 不同屏幕密度（mdpi → xxxhdpi）
- Foldable / 大屏适配

---

## 十、移动端 Review 清单

- [ ] UI 层无业务逻辑 / 网络调用
- [ ] 状态单一数据源
- [ ] 长列表虚拟化
- [ ] 网络有超时 + 重试 + 缓存
- [ ] 写操作支持离线重试
- [ ] 敏感数据加密存储
- [ ] 权限按需申请
- [ ] 启动 ≤ 2 秒
- [ ] 深色 / 浅色模式适配
- [ ] 不同屏幕尺寸测试
- [ ] 代码混淆已开启
- [ ] 隐私政策可见
