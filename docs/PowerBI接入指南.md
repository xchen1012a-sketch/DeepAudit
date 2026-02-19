# Power BI 接入指南

## 概述

DeepAudit Pro 提供了专门的 Power BI 数据接口，通过后端预聚合数据并以 Web API 形式输出 CSV/JSON，让 Power BI 可以轻松拉取数据进行可视化分析。

**架构优势：**
- ✅ 后端预聚合，避免 Power BI 直连业务库造成性能问题
- ✅ 支持 CSV/JSON 双格式输出
- ✅ 内置缓存机制（15 分钟），提升响应速度
- ✅ 业务库与分析库解耦，互不影响
- ✅ 支持 API Key 认证，保障数据安全

---

## API 接口列表

### 1. 每日指标接口

**接口地址：** `GET /api/pbi/metrics/daily`

**功能：** 按天聚合发票、风险事件、风险案例、银行交易等核心指标

**参数：**
- `start_date` (可选): 开始日期，格式 YYYY-MM-DD，默认 90 天前
- `end_date` (可选): 结束日期，格式 YYYY-MM-DD，默认今天
- `format` (可选): 输出格式，`json` 或 `csv`，默认 `json`
- `api_key` (可选): API 密钥（如果启用了认证）

**返回字段：**
- `date`: 日期
- `invoice_count`: 发票数量
- `invoice_amount`: 发票总金额
- `risk_event_count`: 风险事件数量
- `risk_case_count`: 风险案例数量
- `bank_txn_count`: 银行交易数量
- `bank_txn_amount`: 银行交易总金额
- `high_risk_count`: 高风险数量
- `medium_risk_count`: 中风险数量
- `low_risk_count`: 低风险数量

**示例：**
```
http://localhost:5000/api/pbi/metrics/daily?start_date=2026-01-01&end_date=2026-02-19&format=csv
```

---

### 2. 动作指标接口

**接口地址：** `GET /api/pbi/metrics/actions`

**功能：** 按动作类型聚合用户操作数据

**参数：** 同上

**返回字段：**
- `action_type`: 动作类型
- `action_count`: 动作次数
- `user_count`: 涉及用户数
- `department_count`: 涉及部门数

**示例：**
```
http://localhost:5000/api/pbi/metrics/actions?format=csv
```

---

### 3. 风险指标接口

**接口地址：** `GET /api/pbi/metrics/risks`

**功能：** 按风险等级和状态聚合发票数据

**参数：** 同上

**返回字段：**
- `risk_level`: 风险等级 (HIGH/MEDIUM/LOW)
- `status`: 状态
- `count`: 数量
- `total_amount`: 总金额
- `avg_amount`: 平均金额

**示例：**
```
http://localhost:5000/api/pbi/metrics/risks?format=csv
```

---

### 4. 部门指标接口

**接口地址：** `GET /api/pbi/metrics/departments`

**功能：** 按部门聚合发票和风险数据

**参数：** 同上

**返回字段：**
- `department`: 部门名称
- `invoice_count`: 发票数量
- `invoice_amount`: 发票总金额
- `high_risk_count`: 高风险数量

**示例：**
```
http://localhost:5000/api/pbi/metrics/departments?format=csv
```

---

### 5. 综合仪表板接口

**接口地址：** `GET /api/pbi/dashboard`

**功能：** 获取所有关键指标的汇总数据

**参数：** 同上（仅支持 JSON 格式）

**返回数据：**
```json
{
  "ok": true,
  "data": {
    "period": {
      "start_date": "2025-11-21",
      "end_date": "2026-02-19"
    },
    "invoices": {
      "total_count": 80,
      "total_amount": 405562.55,
      "avg_amount": 5069.53,
      "high_risk_count": 6,
      "medium_risk_count": 20,
      "low_risk_count": 54,
      "approved_count": 24,
      "rejected_count": 0
    },
    "risk_events": {
      "total_count": 40
    },
    "risk_cases": {
      "total_count": 20,
      "closed_count": 7,
      "close_rate": 35.0
    },
    "bank_transactions": {
      "total_count": 150,
      "total_amount": 1512919.36,
      "matched_count": 75,
      "match_rate": 50.0
    }
  }
}
```

---

## Power BI Desktop 配置步骤

### 步骤 1：启动 DeepAudit Pro 应用

确保应用正在运行：

```bash
# 方式 1：使用启动脚本
scripts\run_demo.bat

# 方式 2：手动启动
python app.py
```

应用默认运行在 `http://localhost:5000`

---

### 步骤 2：在 Power BI 中添加 Web 数据源

1. 打开 Power BI Desktop
2. 点击「获取数据」→「Web」
3. 在 URL 输入框中输入接口地址，例如：

```
http://localhost:5000/api/pbi/metrics/daily?format=csv
```

4. 点击「确定」

---

### 步骤 3：配置认证（如果启用了 API Key）

如果设置了环境变量 `PBI_API_KEY`，需要在 URL 中添加 API Key：

```
http://localhost:5000/api/pbi/metrics/daily?format=csv&api_key=your_api_key_here
```

或者在 Power BI 的「高级选项」中添加 HTTP 请求头：

```
X-API-Key: your_api_key_here
```

---

### 步骤 4：加载数据

1. Power BI 会自动解析 CSV 数据
2. 检查数据类型是否正确（日期、数字等）
3. 点击「加载」或「转换数据」

---

### 步骤 5：配置数据刷新

1. 在 Power BI Desktop 中，点击「主页」→「刷新」可手动刷新数据
2. 发布到 Power BI Service 后，可以配置定时刷新：
   - 进入数据集设置
   - 配置「计划刷新」
   - 建议刷新频率：每小时或每天

---

## 创建示例仪表板

### 推荐图表

#### 1. 每日趋势折线图
- **数据源：** `/api/pbi/metrics/daily`
- **X 轴：** date
- **Y 轴：** invoice_count, risk_event_count
- **图表类型：** 折线图

#### 2. 风险分布饼图
- **数据源：** `/api/pbi/metrics/daily`
- **图例：** risk_level
- **值：** high_risk_count, medium_risk_count, low_risk_count
- **图表类型：** 饼图

#### 3. 部门对比柱状图
- **数据源：** `/api/pbi/metrics/departments`
- **X 轴：** department
- **Y 轴：** invoice_amount
- **图表类型：** 柱状图

#### 4. 动作热力图
- **数据源：** `/api/pbi/metrics/actions`
- **行：** action_type
- **值：** action_count
- **图表类型：** 矩阵或热力图

#### 5. 案例处理漏斗图
- **数据源：** `/api/pbi/dashboard`
- **阶段：** 风险事件 → 风险案例 → 已关闭案例
- **图表类型：** 漏斗图

---

## 性能优化建议

### 1. 限制查询时间范围

默认查询最近 90 天数据，如果数据量大，建议缩短时间范围：

```
http://localhost:5000/api/pbi/metrics/daily?start_date=2026-02-01&end_date=2026-02-19&format=csv
```

### 2. 使用 CSV 格式

CSV 格式比 JSON 更轻量，适合大数据量场景：

```
format=csv
```

### 3. 利用缓存机制

接口内置 15 分钟缓存，相同参数的请求会直接返回缓存数据，无需重复计算。

### 4. 避免高频刷新

建议刷新频率：
- **开发环境：** 手动刷新
- **测试环境：** 每小时刷新
- **生产环境：** 每天早上 8:00 刷新

---

## 安全配置

### 启用 API Key 认证

1. 在 `.env` 文件中设置 API Key：

```env
PBI_API_KEY=your_secure_api_key_here
```

2. 重启应用使配置生效

3. 在 Power BI 中使用 API Key：

```
http://localhost:5000/api/pbi/metrics/daily?format=csv&api_key=your_secure_api_key_here
```

### 网络安全

- **内网部署：** 如果应用部署在内网，可以不启用 API Key
- **公网部署：** 必须启用 API Key 并使用 HTTPS
- **防火墙：** 限制只有 Power BI 服务器可以访问 API 端口

---

## 故障排查

### 问题 1：无法连接到 API

**解决方案：**
1. 确认应用正在运行：`http://localhost:5000/api/pbi/health`
2. 检查防火墙设置
3. 确认 URL 地址正确

### 问题 2：返回 401 错误

**解决方案：**
1. 检查是否设置了 `PBI_API_KEY` 环境变量
2. 确认 API Key 是否正确
3. 检查 URL 中是否包含 `api_key` 参数

### 问题 3：数据为空

**解决方案：**
1. 检查数据库中是否有数据
2. 确认日期范围参数是否正确
3. 运行数据生成脚本：`python scripts/seed_invoices.py`

### 问题 4：数据刷新失败

**解决方案：**
1. 检查应用是否持续运行
2. 检查网络连接
3. 查看 Power BI 错误日志

---

## 常见问题

### Q: 支持哪些数据库？
A: 当前支持 SQLite，未来可扩展支持 PostgreSQL、MySQL 等。

### Q: 可以直连数据库吗？
A: 不建议。直连会影响业务库性能，建议使用预聚合 API。

### Q: 数据延迟多久？
A: 由于缓存机制，数据最多延迟 15 分钟。

### Q: 支持实时数据吗？
A: 当前不支持实时推送，需要 Power BI 定时刷新。未来可通过 WebSocket 实现实时推送。

### Q: 如何清空缓存？
A: 重启应用即可清空所有缓存。

---

## 联系支持

如有问题，请联系技术支持或提交 Issue。

