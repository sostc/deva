---
name: naja-daily-review
description: Naja 市场每日复盘技能。汇总市场行情、热点题材、叙事信号、持仓状态等核心数据，生成结构化复盘报告并通过 iMessage 发送。
---

# Naja Daily Review Skill

市场每日复盘技能，汇总 Naja 系统核心数据生成结构化报告。

## 功能特性

- **市场行情**: A股+美股热点题材、热门股票
- **叙事信号**: Top5 叙事主题、注意力评分、趋势
- **持仓状态**: 组合汇总、流动性、和谐度
- **Bandit 状态**: 运行阶段、决策统计
- **知识库**: 最新因果知识、状态分布
- **注意力系统**: Manas 状态、信念验证、时机信号

## 触发词

- "复盘"
- "日报"
- "市场总结"
- "今日复盘"

## 输出格式

结构化 Markdown 报告，通过 iMessage 发送到用户手机：

```
📊 Naja 每日复盘 - YYYY-MM-DD

━━━━━━━━━━━━━━━━━━━━
📈 市场行情
━━━━━━━━━━━━━━━━━━━━
【美股热门题材】
• social_media 1.00
• ai_chip 0.97
...

【A股热门题材】
• DeepSeek 0.85
• ...

━━━━━━━━━━━━━━━━━━━━
🎯 Top5 叙事信号
━━━━━━━━━━━━━━━━━━━━
1️⃣ AI | 0.707 | 热度↓
• 英伟达暴涨5%
• ...

2️⃣ 地缘政治 | 0.691 | 热度↓
• ...

━━━━━━━━━━━━━━━━━━━━
💼 持仓状态
━━━━━━━━━━━━━━━━━━━━
• 和谐度: 0.28 (neutral)
• Bandit: running, phase=closed
• 流动性: 更新于 HH:MM:SS

━━━━━━━━━━━━━━━━━━━━
🧠 注意力系统
━━━━━━━━━━━━━━━━━━━━
• Manas: enabled
• 信念验证: 无数据
• 时机信号: unknown

━━━━━━━━━━━━━━━━━━━━
📚 知识库
━━━━━━━━━━━━━━━━━━━━
• 总知识: 2条
• validating: 1条
• observing: 1条
```

## 使用方法

### 通过 iMessage 触发

用户发送 "复盘" 或 "日报" 到 iMessage，Skill 自动生成并发送复盘报告。

### 通过 API 触发

```bash
# 获取认知记忆
curl -s http://localhost:8080/api/cognition/memory | jq '.data.narratives.summary'

# 获取市场热点
curl -s http://localhost:8080/api/market/hotspot | jq '.data'

# 获取和谐度
curl -s http://localhost:8080/api/attention/harmony | jq '.data'

# 获取 Bandit 状态
curl -s http://localhost:8080/api/bandit/stats | jq '.data'
```

## 数据来源

| API 端点 | 数据类型 |
|---------|---------|
| `/api/cognition/memory` | 叙事、用户关注、语义图谱 |
| `/api/market/hotspot` | A股+美股热点 |
| `/api/attention/harmony` | 和谐度 |
| `/api/attention/manas/state` | Manas 末那识状态 |
| `/api/bandit/stats` | Bandit 运行状态 |
| `/api/knowledge/stats` | 知识库统计 |

## 注意事项

- 非交易时段，市场热点数据可能为空
- 叙事信号基于最近事件流计算
- 知识库状态更新有延迟
- iMessage 发送需要 Mac OS 环境