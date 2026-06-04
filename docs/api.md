# API 接口文档

Base URL: `http://127.0.0.1:8000`

所有响应均为 JSON 格式，编码 UTF-8。

---

## GET /api/health

健康检查。

**响应示例：**

```json
{
  "status": "ok",
  "service": "基金决策辅助分析",
  "version": "2.0.0"
}
```

---

## GET /api/macro

获取宏观一览数据（全球指数、汇率、商品、SHIBOR）。

轻量接口，不依赖基金代码，不运行完整分析流程。

**无请求参数。**

**响应示例：**

```json
{
  "success": true,
  "macro": {
    "status": "ok",
    "summary": "海外市场风险偏好上升，美元走强对人民币资产形成扰动，国内流动性环境保持宽松...",
    "macro_summary": {
      "risk_appetite": "risk-on",
      "overseas_direction": "bullish",
      "forex_pressure": "有一定贬值压力",
      "commodity_disturbance": "黄金上涨",
      "liquidity": "loose"
    },
    "risk_factors": [
      "美元指数走强，人民币贬值压力上升",
      "原油价格上涨，输入性通胀风险"
    ],
    "global_indices": [
      { "name": "纳斯达克", "latest": 18500.50, "change_pct": 1.23, "source": "akshare", "as_of": "2025-01-15" }
    ],
    "forex": [
      { "name": "美元/人民币", "latest": 7.25, "source": "akshare", "as_of": "2025-01-15" }
    ],
    "commodities": [
      { "name": "黄金(SGE)", "latest": 480.50, "source": "akshare", "as_of": "2025-01-15" }
    ],
    "interbank_rates": [
      { "name": "SHIBOR隔夜", "latest": 1.45, "change": -5, "source": "akshare", "as_of": "2025-01-15" }
    ],
    "as_of": "2025-01-15"
  }
}
```

**错误响应：**

```json
{
  "success": false,
  "macro": null,
  "error": "宏观数据获取失败：AKShare 连接超时"
}
```

---

## GET /api/analyze

分析单只基金（无持仓信息）。

**请求参数（Query）：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 基金代码，5-6 位数字，如 161725 |

**请求示例：**

```
GET /api/analyze?code=161725
```

**响应示例：**

```json
{
  "success": true,
  "code": "161725",
  "fund": {
    "code": "161725",
    "name": "招商中证白酒指数(LOF)",
    "type": "指数型-股票",
    "company": "招商基金"
  },
  "fund_profile": {
    "fund_type": "指数型-股票",
    "fund_manager": "侯昊",
    "risk_level": "R4",
    "data_quality": "good"
  },
  "metrics": {
    "data_days": 120,
    "return_7d_calendar": -1.23,
    "return_30d_calendar": 5.67,
    "volatility_annual": 0.25,
    "max_drawdown": -0.35,
    "sharpe_ratio": -0.12
  },
  "risk": {
    "risk_score": 58.2,
    "risk_level": "偏高"
  },
  "forecast": {
    "forecast_1d": { "direction": "偏弱" },
    "forecast_7d": { "direction": "偏弱" },
    "forecast_30d": { "direction": "不确定" }
  },
  "prediction": {
    "status": "ok",
    "quality": "low",
    "summary": "当前没有发现稳定跑赢简单基线的上涨预测优势，应主要作为低置信参考。",
    "periods": {
      "7d": {
        "predicted_direction": "uncertain",
        "direction_label": "不确定",
        "up_probability": 48.6,
        "down_or_flat_probability": 51.4,
        "historical_hit_rate": 52.38,
        "baseline_hit_rate": 55.24,
        "edge_vs_baseline": -2.86,
        "confidence": "低"
      }
    }
  },
  "analysis": {
    "conclusion": "中性",
    "summary_7d": "短线震荡",
    "summary_30d": "中期偏弱"
  },
  "datasource_status": {
    "akshare": { "available": true },
    "efinance": { "available": false }
  }
}
```

**错误响应：**

```json
{
  "success": false,
  "code": "000000",
  "error": "未找到基金代码 000000 对应的基金"
}
```

---

## POST /api/analyze

分析单只基金（可附带持仓信息）。

**请求体（JSON）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 基金代码 |
| position | object | 否 | 持仓信息 |

**position 字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| cost_nav | float | 持仓成本净值 |
| holding_amount | float | 持有金额 |
| holding_units | float | 持有份额 |
| is_dca | bool | 是否定投 |
| holding_horizon | string | 持有期限 |
| risk_preference | string | 风险偏好 |

**请求示例：**

```json
{
  "code": "161725",
  "position": {
    "cost_nav": 1.25,
    "holding_amount": 5000,
    "is_dca": false,
    "holding_horizon": "1年以上",
    "risk_preference": "平衡"
  }
}
```

响应格式同 GET /api/analyze，增加了持仓相关的风险维度。

---

## GET /api/my-funds

获取个人基金列表。

**响应示例：**

```json
{
  "funds": [
    {
      "code": "161725",
      "holding_amount": 5000,
      "note": "定投中"
    },
    {
      "code": "110022",
      "holding_amount": 3000,
      "note": ""
    }
  ],
  "count": 2
}
```

---

## POST /api/my-funds

新增或更新一只基金。按 `code` 去重，已存在则更新，不存在则新增。

**请求体（JSON）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 基金代码 |
| cost_nav | float | 否 | 持仓成本 |
| holding_amount | float | 否 | 持有金额 |
| note | string | 否 | 备注 |

**请求示例：**

```json
{
  "code": "161725",
  "holding_amount": 5000,
  "note": "招商白酒定投"
}
```

**响应示例：**

```json
{
  "success": true,
  "code": "161725",
  "count": 1
}
```

---

## DELETE /api/my-funds/{code}

删除一只基金。

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| code | string | 基金代码 |

**响应示例（成功）：**

```json
{
  "success": true,
  "code": "161725",
  "count": 0
}
```

**响应示例（不存在）：**

HTTP 404 — `{"detail": "基金 161725 不在列表中"}`

**响应示例（无效代码）：**

HTTP 422 — `{"detail": "基金代码长度为 5-6 位数字"}`

---

## POST /api/my-funds/analyze

批量分析个人基金列表。顺序执行，单只失败不阻塞其他。

**无请求体。**

**响应示例：**

```json
{
  "success": true,
  "total": 2,
  "results": [
    {
      "code": "161725",
      "success": true,
      "fund": { "name": "招商中证白酒指数(LOF)" },
      "risk": { "risk_score": 58.2 },
      "analysis": { "conclusion": "中性" }
    },
    {
      "code": "110022",
      "success": false,
      "error": "无法获取该基金的历史净值数据"
    }
  ]
}
```
