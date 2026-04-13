---
name: naja-api
description: 提供 naja 系统 API 端点的调用能力，方便用户通过 curl 或其他工具获取系统数据和状态。
---

# Naja API Skill

提供 naja 系统各模块 API 端点的调用能力，方便用户通过 curl 或其他工具获取系统数据和状态。

## 功能特性

- **认知系统 API**: 记忆报告、主题信号、注意力提示、思想报告
- **注意力系统 API**: Manas 末那识状态、和谐度、决策、信念验证、时机信号、持仓汇总、持仓指标、跟踪统计、关注焦点、融合信号、盲区发现、流动性、策略 Top 股票/题材、注意力上下文
- **知识库 API**: 知识列表、知识统计、知识详情、交易决策知识
- **市场热点 API**: 市场状态、热点详情、双市场热点（A股+美股）
- **系统监控 API**: 系统状态、模块状态
- **雷达系统 API**: 雷达事件
- **Bandit 系统 API**: 决策统计（运行状态、当前阶段）
- **数据源和策略 API**: 数据源列表、策略列表
- **智慧系统 API**: 阿那亚觉醒状态

## API 端点列表

### 认知系统

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/cognition/memory` | GET | 获取认知系统记忆报告（叙事、用户关注、语义图谱） |
| `/api/cognition/topics` | GET | 获取认知系统主题信号 |
| `/api/cognition/attention` | GET | 获取认知系统注意力提示 |
| `/api/cognition/thought` | GET | 获取龙虾思想雷达报告 |

### 注意力系统

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/attention/manas/state` | GET | Manas 末那识状态（enabled、last_output） |
| `/api/attention/harmony` | GET | 和谐度（state、strength、should_act） |
| `/api/attention/context` | GET | 注意力上下文（awakening、volatility、contradiction） |
| `/api/attention/decision` | GET | 决策信号 |
| `/api/attention/conviction` | GET | 信念验证 |
| `/api/attention/conviction/timing` | GET | 时机信号 |
| `/api/attention/conviction/should-add` | GET | 是否应该加仓 |
| `/api/attention/portfolio/summary` | GET | 持仓汇总 |
| `/api/attention/position/metrics` | GET | 持仓指标（收益率、波动率） |
| `/api/attention/tracking/hotspot` | GET | 跟踪热点 |
| `/api/attention/tracking/stats` | GET | 跟踪统计（胜率、平均收益） |
| `/api/attention/focus` | GET | 关注焦点 |
| `/api/attention/fusion` | GET | 融合信号 |
| `/api/attention/blind-spots` | GET | 盲区发现 |
| `/api/attention/liquidity` | GET | 流动性（总资产、现金、持仓、日盈亏） |
| `/api/attention/strategy/top-symbols` | GET | 策略 Top 股票 |
| `/api/attention/strategy/top-blocks` | GET | 策略 Top 题材 |
| `/api/attention/report` | GET | 注意力报告 |
| `/api/attention/lab/status` | GET | 实验室状态 |

### 知识库

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/knowledge/list` | GET | 知识列表（支持 status、category、limit、offset 筛选） |
| `/api/knowledge/stats` | GET | 知识统计（按状态/分类分布、平均置信度） |
| `/api/knowledge/detail` | GET | 知识详情（?id=xxx） |
| `/api/knowledge/trading` | GET | 可用于交易决策的知识（qualified + validating） |
| `/api/knowledge/action` | POST | 知识操作（标注、笔记等） |

### 市场热点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/market/state` | GET | 获取市场状态 |
| `/api/market/hotspot` | GET | 获取双市场热点（A股+美股） |
| `/api/market/hotspot/details` | GET | 获取市场热点详情 |

### 系统监控

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/system/status` | GET | 获取系统状态（10/10 模块健康） |
| `/api/system/modules` | GET | 获取系统模块状态 |
| `/api/health` | GET | 健康检查 |

### 其他

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/radar/events` | GET | 获取雷达事件 |
| `/api/bandit/stats` | GET | 获取 Bandit 运行状态（running、phase、intervals） |
| `/api/datasource/list` | GET | 获取数据源列表 |
| `/api/strategy/list` | GET | 获取策略列表 |
| `/api/alaya/status` | GET | 获取阿那亚觉醒状态 |

## 使用方法

### 1. 基本 curl 调用

```bash
# 获取系统状态
curl -s http://localhost:8080/api/system/status | jq '.data.overall'

# 获取认知记忆（含叙事、用户关注）
curl -s http://localhost:8080/api/cognition/memory | jq '.data.narratives.summary'

# 获取知识库列表
curl -s http://localhost:8080/api/knowledge/list | jq '.data.entries[:5]'

# 获取 Manas 末那识状态
curl -s http://localhost:8080/api/attention/manas/state | jq '.data'

# 获取和谐度
curl -s http://localhost:8080/api/attention/harmony | jq '.data'
```

### 2. 带参数调用

```bash
# 知识库筛选（按状态）
curl -s "http://localhost:8080/api/knowledge/list?status=qualified&limit=10"

# 知识库筛选（按分类）
curl -s "http://localhost:8080/api/knowledge/list?category=ai_infra"

# 知识详情
curl -s "http://localhost:8080/api/knowledge/detail?id=abc12345"

# 认知主题信号（指定回溯数量）
curl -s "http://localhost:8080/api/cognition/topics?lookback=100"
```

### 3. 全景数据采集

```bash
# 一键采集所有关键数据
curl -s http://localhost:8080/api/system/status | jq '.data.overall'
curl -s http://localhost:8080/api/cognition/memory | jq '.data.narratives.summary'
curl -s http://localhost:8080/api/attention/manas/state | jq '.data.enabled'
curl -s http://localhost:8080/api/attention/harmony | jq '.data'
curl -s http://localhost:8080/api/knowledge/list | jq '.data.total'
curl -s http://localhost:8080/api/knowledge/stats | jq '.data'
curl -s http://localhost:8080/api/bandit/stats | jq '.data'
```

### 4. Python 客户端

```bash
python3 scripts/api_client.py system-status
python3 scripts/api_client.py knowledge-list --status qualified
python3 scripts/api_client.py manas-state
python3 scripts/api_client.py harmony
```

## 响应格式

所有 API 端点返回统一的 JSON 格式：

```json
{
  "timestamp": 1713000000.0,
  "datetime": "2026-04-13 12:00:00",
  "success": true,
  "data": {
    // 具体数据内容
  }
}
```

## 知识库数据结构

知识条目以**因果关系**为核心结构：

```json
{
  "id": "abc12345",
  "cause": "美联储加息",
  "effect": "美元走强",
  "confidence": 0.70,
  "source": "reuters",
  "original_title": "美联储宣布加息25个基点",
  "extracted_at": "2026-04-13T12:00:00",
  "category": "macro",
  "status": "observing",
  "evidence_count": 1,
  "quality_score": 0.70,
  "mechanism": "利率上升吸引国际资本流入",
  "timeframe": "短期"
}
```

知识状态生命周期：`observing`（观察7天）→ `validating`（验证7天）→ `qualified`（正式参与决策）→ `expired`（60天无更新过期）

## 注意事项

- 注意力系统的高级端点（conviction、focus、fusion、blind-spots、strategy/top-*）为懒加载，需要交易时段事件触发后才会初始化
- Manas 末那识需要市场周期触发 compute 后才会有输出
- 知识库的 qualified 状态知识会注入认知系统影响决策
- 非交易时段，市场热点和持仓数据为空是正常现象
