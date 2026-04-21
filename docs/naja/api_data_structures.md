# Naja 数据结构 API 文档

## 概述

本文档描述了 Naja 系统中暴露的重要数据结构的 API 端点，这些端点允许外部系统（如相关技能）读取系统运行状态。

## API 端点列表

所有端点都支持 CORS（跨域资源共享），返回 JSON 格式的响应。

### 1. 单例注册表状态

**端点**: `/api/registry/status`

**方法**: `GET`

**描述**: 获取所有已注册的单例组件的状态

**响应示例**:
```json
{
  "timestamp": 1713700000.0,
  "datetime": "2026-04-20 12:00:00",
  "success": true,
  "data": {
    "attention_os": {
      "status": "ready",
      "has_instance": true,
      "deps": ["attention_integration"],
      "error": null
    },
    "query_state": {
      "status": "ready",
      "has_instance": true,
      "deps": [],
      "error": null
    }
  }
}
```

---

### 2. 查询状态

**端点**: `/api/query/state`

**方法**: `GET`

**描述**: 获取系统当前的查询状态，包括注意力焦点、市场状态、价值观等

**响应示例**:
```json
{
  "timestamp": 1713700000.0,
  "datetime": "2026-04-20 12:00:00",
  "success": true,
  "data": {
    "summary": { ... },
    "market_regime": {
      "type": "trend_up",
      "timestamp": 1713700000.0,
      "up_ratio": 0.6,
      "down_ratio": 0.2,
      "avg_change": 1.5,
      "change_std": 0.8
    },
    "attention_focus": {
      "AI概念": 0.9,
      "芯片": 0.8
    },
    "risk_bias": 0.6,
    "macro_liquidity_signal": 0.7,
    "narrative_state": { ... },
    "cognitive_insights": { ... },
    "liquidity_state": { ... },
    "economic_cycle": { ... },
    "active_value_type": "trend",
    "last_decision_reason": "..."
  }
}
```

---

### 3. 系统状态

**端点**: `/api/system/state`

**方法**: `GET`

**描述**: 获取系统持久化状态，包括活跃时间、任务执行历史等

**响应示例**:
```json
{
  "timestamp": 1713700000.0,
  "datetime": "2026-04-20 12:00:00",
  "success": true,
  "data": {
    "summary": {
      "last_active_time": "2026-04-20T11:55:00",
      "last_sleep_time": null,
      "last_wake_time": "2026-04-20T10:00:00",
      "sleep_duration_hours": 0.0,
      "needs_wake_sync": false,
      "task_count": 5
    },
    "state": {
      "version": "1.0",
      "last_active_time": "2026-04-20T11:55:00",
      "system_uptime_start": "2026-04-20T10:00:00",
      "task_execution_records": { ... }
    }
  }
}
```

---

### 4. 事件查询

**端点**: `/api/events/query`

**方法**: `GET`

**描述**: 查询历史事件，支持多种过滤条件

**查询参数**:
- `event_type`: 事件类型（如 `StrategySignalEvent`、`TradeDecisionEvent`）
- `symbol`: 股票代码
- `direction`: 方向（`buy` 或 `sell`）
- `min_confidence`: 最小置信度
- `max_confidence`: 最大置信度
- `start_time`: 开始时间戳
- `end_time`: 结束时间戳
- `limit`: 返回数量限制（默认 100）
- `offset`: 偏移量（默认 0）

**响应示例**:
```json
{
  "timestamp": 1713700000.0,
  "datetime": "2026-04-20 12:00:00",
  "success": true,
  "data": {
    "events": [ ... ],
    "count": 50,
    "query": {
      "event_type": "StrategySignalEvent",
      "symbol": "000001",
      "limit": 100,
      "offset": 0
    }
  }
}
```

---

### 5. 事件统计

**端点**: `/api/events/stats`

**方法**: `GET`

**描述**: 获取事件的统计信息

**查询参数**:
- `event_type`: 事件类型（默认 `StrategySignalEvent`）
- `days`: 统计天数（默认 30）

**响应示例**:
```json
{
  "timestamp": 1713700000.0,
  "datetime": "2026-04-20 12:00:00",
  "success": true,
  "data": {
    "event_type": "StrategySignalEvent",
    "days": 30,
    "stats": {
      "total_events": 250,
      "buy_signals": 150,
      "sell_signals": 100,
      "avg_confidence": 0.75,
      "max_confidence": 0.95,
      "min_confidence": 0.55,
      "timeline": {
        "2026-04-19": 10,
        "2026-04-18": 12
      }
    }
  }
}
```

---

### 6. 应用容器状态

**端点**: `/api/app/container`

**方法**: `GET`

**描述**: 获取应用容器的状态和启动报告

**响应示例**:
```json
{
  "timestamp": 1713700000.0,
  "datetime": "2026-04-20 12:00:00",
  "success": true,
  "data": {
    "startup_report": {
      "load_counts": {
        "datasource": 10,
        "task": 5,
        "strategy": 8,
        "dictionary": 3
      },
      "load_errors": { ... },
      "restore_results": { ... },
      "restore_errors": { ... }
    },
    "components_assembled": true
  }
}
```

---

## 使用示例

### Python 使用示例

```python
import requests
import json

BASE_URL = "http://localhost:8080"

# 获取注册表状态
response = requests.get(f"{BASE_URL}/api/registry/status")
if response.ok:
    data = response.json()
    print("注册表状态:", json.dumps(data, ensure_ascii=False, indent=2))

# 获取查询状态
response = requests.get(f"{BASE_URL}/api/query/state")
if response.ok:
    data = response.json()
    print("查询状态:", json.dumps(data, ensure_ascii=False, indent=2))

# 查询事件
params = {
    "event_type": "StrategySignalEvent",
    "symbol": "000001",
    "days": 7,
    "limit": 50
}
response = requests.get(f"{BASE_URL}/api/events/query", params=params)
if response.ok:
    data = response.json()
    print("事件查询结果:", json.dumps(data, ensure_ascii=False, indent=2))

# 获取事件统计
params = {
    "event_type": "StrategySignalEvent",
    "days": 30
}
response = requests.get(f"{BASE_URL}/api/events/stats", params=params)
if response.ok:
    data = response.json()
    print("事件统计:", json.dumps(data, ensure_ascii=False, indent=2))
```

### JavaScript 使用示例

```javascript
const BASE_URL = "http://localhost:8080";

// 获取注册表状态
fetch(`${BASE_URL}/api/registry/status`)
  .then(response => response.json())
  .then(data => console.log("注册表状态:", data));

// 获取查询状态
fetch(`${BASE_URL}/api/query/state`)
  .then(response => response.json())
  .then(data => console.log("查询状态:", data));

// 查询事件
const params = new URLSearchParams({
  event_type: "StrategySignalEvent",
  symbol: "000001",
  limit: 50
});
fetch(`${BASE_URL}/api/events/query?${params}`)
  .then(response => response.json())
  .then(data => console.log("事件查询结果:", data));
```

---

## 现有 API 端点参考

除了新添加的端点外，Naja 系统还提供了以下现有 API：

- `/api/health` - 健康检查
- `/api/hotspot` - 市场热点
- `/api/system/status` - 系统状态
- `/api/system/modules` - 系统模块
- `/api/attention/*` - 注意力系统相关 API
- `/api/cognition/*` - 认知系统相关 API
- `/api/knowledge/*` - 知识库相关 API
- `/api/datasource/list` - 数据源列表
- `/api/strategy/list` - 策略列表
- `/api/bandit/stats` - Bandit 统计
- `/api/radar/events` - 雷达事件

更多详细信息请参考系统的完整 API 文档。
