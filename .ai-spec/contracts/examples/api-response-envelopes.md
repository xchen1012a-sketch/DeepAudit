# API 响应信封示例

## 统一响应信封

```json
{
  "code": 0,
  "data": { ... },
  "msg": "success"
}
```
- `code = 0` 表示成功，非 0 表示业务错误
- `data` 成功时为数据，失败时为 null
- `msg` 成功时为提示，失败时为错误描述

## 分页

```json
{
  "code": 0,
  "data": {
    "list": [...],
    "total": 100,
    "page": 1,
    "limit": 20
  }
}
```

## 错误信封

```json
{
  "code": 40001,
  "data": null,
  "msg": "参数错误：邮箱格式不正确",
  "details": [
    { "field": "email", "issue": "invalid format" }
  ]
}
```
