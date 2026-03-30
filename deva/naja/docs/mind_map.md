# 系统架构与佛学层次对照

> "五识感市场，意识了分明，末那识决断，阿赖耶识收藏，舌识尝苦乐，业力证因果，MetaManas 观照轮回。"

---

## 完整架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                           心 (Mind)                              │
│                    整体系统 / 最高层觉知                          │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│   五识 (Senses) │      │   意识 (识)   │      │ 末那识 (Manas) │
│   感官输入层    │      │   认知层      │      │   决策层      │
├───────────────┤      ├───────────────┤      ├───────────────┤
│               │      │               │      │               │
│ 目 → MarketData│      │ NewsMind      │      │ ManasEngine   │
│ 耳 → News     │      │ Strategy      │      │               │
│ 鼻 →Liquidity │      │               │      │ 决策判断       │
│ 舌 →Taste     │      │ 记忆/分析     │      │               │
│ 身 →Scanner   │      │               │      │               │
│               │      │               │      │               │
└───────────────┘      └───────────────┘      └───────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     阿赖耶识 (Alaya/藏)                          │
│                         记忆 / 种子存储                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐          ┌─────────────────┐             │
│  │ AttentionMemory │          │   ValueSystem   │             │
│  │   (藏/Storehouse)│          │   (种子/Seeds) │             │
│  │                 │          │                 │             │
│  │ • 事件记忆       │          │ • 价值观种子     │             │
│  │ • 时间衰减       │          │ • 策略偏好       │             │
│  │ • 熏习强化       │          │ • alignment     │             │
│  └─────────────────┘          └─────────────────┘             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       舌识 / 业力层                               │
│                     尝受 / 因果反馈                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐          ┌─────────────────┐             │
│  │ BanditTracker  │          │ Attention      │             │
│  │ (舌识/Taste)   │          │ FeedbackLoop   │             │
│  │                 │          │ (业力/Karma)   │             │
│  │ • 平仓尝受     │          │ • 在线学习     │             │
│  │ • 盈亏记录     │          │ • 策略更新     │             │
│  │ • 实时反馈     │          │ • 注意力强化   │             │
│  └─────────────────┘          └─────────────────┘             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 详细对照表

| 佛学层次 | 系统组件 | 类名/文件名 | 功能说明 |
|---------|---------|-------------|---------|
| **心 (Mind)** | 整体系统 | `Mind` | 最高层觉知，协调所有子系统 |
| **五识 (Senses)** | 感官输入 | | |
| ├─ 目 | 行情数据 | `MarketDataFeed` | 辨色，识价格涨跌 |
| ├─ 耳 | 新闻资讯 | `NewsFetcher` | 听声，感市场情绪 |
| ├─ 鼻 | 流动性 | `LiquidityDetector` | 嗅息，察资金流向 |
| ├─ 舌 | 尝受 | `TasteTracker` | 品味，验盈亏得失 |
| └─ 身 | 市场扫描 | `GlobalMarketScanner` | 触境，知宏观状态 |
| **意识 (识)** | 认知/注意 | | |
| ├─ 识 | 注意力中枢 | `AttentionKernel` | 了别，觉知当前焦点 |
| ├─ 想 | 认知引擎 | `NewsMindStrategy` | 取相，识别市场主题 |
| └─ 思 | 策略分析 | `StrategyManager` | 思辨，推演未来可能 |
| **末那识 (Manas)** | 决策判断 | | |
| ├─ 执 | ManasEngine | `ManasEngine` | 我执，持续判断是否行动 |
| ├─ 时机 | TimingEngine | `TimingEngine` | 天时，是否该动 |
| ├─ 环境 | RegimeEngine | `RegimeEngine` | 地势，顺风还是逆风 |
| ├─ 自信 | ConfidenceEngine | `ConfidenceEngine` | 人谋，策略适配度 |
| ├─ 风险 | RiskEngine | `RiskEngine` | 胆识，能承受多少 |
| └─ 观照 | MetaManas | `MetaManas` | 觉知，检测偏差纠偏 |
| **阿赖耶识 (藏)** | 记忆存储 | | |
| ├─ 藏 | 注意力记忆 | `AttentionMemory` | 藏识，存储事件记忆 |
| └─ 种 | 价值观 | `ValueSystem` | 种子，伏藏善恶习气 |
| **舌识 (尝)** | 尝受反馈 | `BanditTracker` | 舌识，尝受平仓盈亏 |
| **业力 (因果)** | 反馈学习 | `AttentionFeedbackLoop` | 业力，行动后果记录 |

---

## 决策信息流

```
五识输入 (感知)
    ↓
意识处理 (认知)
    ↓
末那识决策 (判断)
    ↓
┌─────────────────────────────────────┐
│  ManasEngine.compute()             │
│                                     │
│  manas_score =                     │
│      0.4 * timing +                │
│      0.3 * regime +               │
│      0.3 * confidence              │
│                                     │
│  输出:                              │
│    • should_act (是否行动)          │
│    • alpha (置信度)                │
│    • temperature (风险温度)         │
│    • bias_state (偏差状态)          │
└─────────────────────────────────────┘
    ↓
阿赖耶识存储 (记忆)
    ↓
舌识尝受 + 业力反馈 (因果)
    ↓
MetaManas 观照 (觉知偏差)
```

---

## 系统中的"觉知"层次

| 层次 | 组件 | 觉知什么 |
|------|------|---------|
| **当下** | `AttentionKernel` | 此刻市场在发生什么 |
| **执持** | `ManasEngine` | 我是否该行动 |
| **观照** | `MetaManas` | 我是否在贪/惧 |
| **因果** | `FeedbackLoop` | 我的决策对不对 |

---

## ManasEngine 核心公式

```
manas_score = 0.4 * timing + 0.3 * regime + 0.3 * confidence

α = confidence * manas_score * bias_correction
T = base_T / (1 + manas_score)

偏差纠偏:
    • 连赢 → 检测到"贪" → bias_correction = 0.7
    • 连亏 → 检测到"惧" → bias_correction = 0.5
```

---

## 文件位置

| 组件 | 文件路径 |
|------|---------|
| ManasEngine | `deva/naja/attention/kernel/manas_engine.py` |
| ManasManager | `deva/naja/attention/kernel/manas_manager.py` |
| AttentionKernel | `deva/naja/attention/kernel/kernel.py` |
| AttentionMemory | `deva/naja/attention/kernel/memory.py` |
| ValueSystem | `deva/naja/attention/values/system.py` |
| BanditTracker | `deva/naja/bandit/tracker.py` |
| FeedbackLoop | `deva/naja/attention/intelligence/feedback_loop.py` |
