---
appliesTo: [frontend, backend, fullstack, mobile, cli, library-sdk, data-platform, ai-llm, generic]
loadWhen: [L2, simple-change, security-baseline]
fallbackTo: core/security-standard.md
---

# 轻量安全规则

用于普通小改动的安全底线。命中高风险条件时读取完整 `core/security-standard.md`。

## 必守底线

- 不读取、输出、提交密钥、Token、私钥、证书、真实生产凭证。
- 不绕过认证、授权、数据隔离、审计逻辑。
- 不把 mock、临时开关、调试日志留进生产路径。
- 不扩大任务范围去重构无关安全代码。

## 升级条件

- 改动登录、权限、租户、角色、数据范围。
- 改动请求签名、Webhook 鉴权、支付/回调校验。
- 发现疑似凭证或敏感数据泄露。
