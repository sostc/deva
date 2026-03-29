# 流动性预测体系

> Naja 注意力操作系统的扩展模块

---

## 一、核心理念

### 1.1 问题背景

在全球金融市场中，流动性变化往往具有以下特点：

1. **跨市场传染**：美股大跌 → A股跟跌 → 港股联动
2. **信号共振**：行情变化和舆论变化相互强化
3. **主题扩散**：美股芯片暴涨 → A股芯片板块跟涨

传统的交易系统是被动的——市场变化后才响应。但真正有效的系统应该能够：

1. **预判**：基于全球市场信号，预判对目标市场的影响
2. **共振检测**：识别行情信号和舆论信号的一致性
3. **验证**：盘中实时验证预判是否正确
4. **纠错**：根据验证结果动态调整/解除限制

### 1.2 核心思想

> **"天时地利，预测先行，共振放大，验证纠错"**

- **天时**：全球市场信号（美股、期货、新闻等）
- **共振**：行情信号和舆论信号的一致性检测
- **预判**：基于天时和共振预测市场流动性
- **验证**：盘中用实际数据验证预判
- **纠错**：预判错误时自动解除限制

---

## 二、系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           流动性预测体系                                            │
│                           Liquidity Prediction System                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          第一层：宏观流动性预测                            │   │
│  │                      Macro Liquidity Prediction                            │   │
│  │                                                                          │   │
│  │   ┌─────────────┐     ┌─────────────────┐     ┌─────────────────────┐   │   │
│  │   │ 行情信号    │────→│  信号共振检测   │────→│  流动性预测        │   │   │
│  │   │ MarketSignal│     │ ResonanceDetect │     │ LiquidityPredict   │   │   │
│  │   └─────────────┘     └─────────────────┘     └─────────────────────┘   │   │
│  │          │                    │                        │                │   │
│  │          │                    │                        ▼                │   │
│  │          │                    │              ┌─────────────────────┐   │   │
│  │          │                    └──────────────→│ 调整指令生成       │   │   │
│  │          │                               │ AdjustmentGen         │   │   │
│  │          │                               └─────────────────────┘   │   │
│  │          │                                                       │   │
│  │          │                    ┌─────────────────┐                 │   │
│  │          └──────────────────→│ 舆论信号        │                 │   │
│  │                               │ NarrativeSignal │                 │   │
│  │                               └─────────────────┘                 │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                              │                                                      │
│                              ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          第二层：主题扩散预测                                │   │
│  │                       Topic Spread Prediction                              │   │
│  │                                                                          │   │
│  │   ┌─────────────┐     ┌─────────────────┐     ┌─────────────────────┐   │   │
│  │   │ 美股板块   │────→│ 主题热度检测    │────→│ 板块扩散预测       │   │   │
│  │   │ US Sector  │     │ TopicHeatDetect │     │ SectorPrediction    │   │   │
│  │   └─────────────┘     └─────────────────┘     └─────────────────────┘   │   │
│  │          │                    │                        │                │   │
│  │          │                    │                        ▼                │   │
│  │          │                    │              ┌─────────────────────┐   │   │
│  │          │                    └──────────────→│ 板块调整指令      │   │   │
│  │          │                               │ SectorAdjustment   │   │   │
│  │          │                               └─────────────────────┘   │   │
│  │          │                                                       │   │
│  │          │                    ┌─────────────────┐                 │   │
│  │          └──────────────────→│ A股同名板块    │                 │   │
│  │                               │ CN SectorMap   │                 │   │
│  │                               └─────────────────┘                 │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                              │                                                      │
│                              ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    AttentionOrchestrator                                   │   │
│  │                                                                          │   │
│  │   宏观层影响 ──→ 市场整体流动性调整                                     │   │
│  │   主题层影响 ──→ 板块级注意力分配                                       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                              │                                                      │
│                              ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         Bandit / Strategy                                 │   │
│  │                                                                          │   │
│  │   执行交易：                                                              │   │
│  │   • 宏观流动性紧张 → 降低仓位                                            │   │
│  │   • 芯片主题火热 → 关注芯片股                                          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 信号共振检测矩阵

```
┌─────────────────────────────────────────────────────────────────────┐
│                        共振类型矩阵                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│           行情 ↑    │    行情 ↓    │    行情平稳               │
│  ────────────────────────────────────────────────────────────────  │
│ 舆论 ↑  │ 高共振   │   中共振    │   低共振                │
│         │ (权重1.0) │  (权重0.5)  │  (权重0.3)              │
│  ────────────────────────────────────────────────────────────────  │
│ 舆论 ↓  │ 中共振   │   高共振    │   低共振                │
│         │ (权重0.5) │  (权重1.0)  │  (权重0.3)              │
│  ────────────────────────────────────────────────────────────────  │
│ 舆论平稳│ 低共振   │   低共振    │   无信号                │
│         │ (权重0.3) │  (权重0.3)  │  (权重0.0)              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**共振检测逻辑**：
- 行情和舆论**同向**且**都较强** → 高共振（权重1.0）
- 行情和舆论**同向**但**一方较弱** → 低共振（权重0.3-0.5）
- 行情和舆论**反向** → 背离（权重0.3）
- 任一信号太弱（<0.2） → 低共振

### 2.3 市场影响矩阵

| 信号来源 | → A股 | → 港股 | → 美股 |
|----------|-------|--------|--------|
| **美股** | 0.5 | 0.8 | - |
| **港股** | 0.6 | - | 0.4 |
| **A股** | - | 0.7 | 0.3 |
| **期货** | 0.6 | 0.5 | 0.5 |

### 2.4 主题扩散映射

| 主题 | 美股板块 | A股目标板块 | 传染概率 |
|------|----------|-------------|----------|
| **芯片** | SOX | 半导体、集成电路 | 0.7 |
| **AI** | AI | 人工智能、软件服务 | 0.6 |
| **新能源** | XLE | 锂电池、光伏 | 0.5 |
| **电动车** | TSLA | 新能源汽车 | 0.4 |
| **云计算** | CLOUD | 云计算、数据中心 | 0.5 |

---

## 三、数据结构

### 3.1 LiquiditySignalType - 市场标识

```python
class LiquiditySignalType(Enum):
    CHINA_A = "china_a"       # A股
    HONG_KONG = "hk"           # 港股
    US = "us"                  # 美股
    FUTURES = "futures"        # 期货
    CRYPTO = "crypto"         # 加密货币
```

### 3.2 LiquidityPrediction - 流动性预测

```python
@dataclass
class LiquidityPrediction:
    target_market: LiquiditySignalType   # 预测目标市场
    source_signals: List[str]            # 信号来源描述
    signal: float                        # 预测值 0-1 (< 0.4 紧张, > 0.6 宽松)
    confidence: float                    # 置信度 0-1
    timestamp: float                      # 预测时间
    valid_until: float                   # 预测有效期（秒）
    adjustment: dict                    # 调整指令
```

### 3.3 共振检测结果

```python
@dataclass
class ResonanceResult:
    resonance_level: str      # "high"/"medium"/"low"/"divergent"/"none"
    confidence: float         # 置信度 0-1
    alignment: float         # 对齐度 0-1
    weight: float            # 最终权重
    market_signal: float     # 行情信号
    narrative_signal: float  # 舆论信号
```

---

## 四、核心方法

### 4.1 信号共振检测

```python
def detect_resonance(market_signal: float, narrative_signal: float) -> ResonanceResult:
    """
    检测行情信号和舆论信号的共振程度

    Args:
        market_signal: 行情信号 (-1 to 1, 负=跌，正=涨)
        narrative_signal: 舆论信号 (-1 to 1, 负=利空，正=利多)

    Returns:
        ResonanceResult: 共振检测结果
    """

    # 信号太弱（<0.2） → 低共振
    if abs(market_signal) < 0.2 or abs(narrative_signal) < 0.2:
        return ResonanceResult(
            resonance_level="low",
            confidence=0.4,
            ...
        )

    # 同向且都较强 → 高共振
    if market_signal * narrative_signal > 0 and \
       abs(market_signal) >= 0.2 and abs(narrative_signal) >= 0.2:
        return ResonanceResult(
            resonance_level="high",
            confidence=0.9,
            ...
        )

    # 反向 → 背离
    return ResonanceResult(
        resonance_level="divergent",
        confidence=0.5,
        ...
    )
```

### 4.2 主题扩散预测

```python
TOPIC_SECTOR_MAPPING = {
    "芯片": {"a_share_sectors": ["半导体", "集成电路"], "us_sector": "SOX"},
    "AI": {"a_share_sectors": ["人工智能", "软件服务"], "us_sector": "AI"},
    "新能源": {"a_share_sectors": ["锂电池", "光伏"], "us_sector": "XLE"},
}

CROSS_MARKET_PROB = {
    "芯片": 0.7,
    "AI": 0.6,
    "新能源": 0.5,
}

def update_topic_heat(topic: str, change_pct: float, volume_ratio: float = 1.0):
    """更新主题热度"""
    heat_score = abs(change_pct) * volume_ratio
    topic_heat[topic].append(heat_score)

def predict_topic_spread(topic: str, us_sector_change: float) -> dict:
    """
    预测主题扩散

    Returns:
        {
            "target_sectors": ["半导体", "集成电路"],
            "spread_probability": 0.7,
            "expected_change": 2.1,
            "heat_score": 4.5,
        }
    """
    heat_history = topic_heat.get(topic, [])
    heat_score = mean(heat_history)

    base_prob = CROSS_MARKET_PROB[topic]
    heat_factor = min(heat_score / 5.0, 1.5)
    spread_prob = base_prob * heat_factor

    return {
        "target_sectors": TOPIC_SECTOR_MAPPING[topic]["a_share_sectors"],
        "spread_probability": spread_prob,
        "expected_change": us_sector_change * spread_prob,
        "heat_score": heat_score,
    }
```

---

## 五、调整指令格式

### 5.1 宏观层调整（流动性紧张）

```python
{
    "sector_attention_factor": 0.8,      # 降低高波动板块权重
    "strategy_budget": {
        "AnomalySniper": 0.2,           # 增加异常关注
        "MomentumTracker": -0.2,         # 减少趋势追踪
    },
    "frequency_factor": 1.3,              # 减少高频交易
}
```

### 5.2 主题层调整（热门主题）

```python
{
    "attention_weight_factor": 1.3,      # 板块权重上调
    "hot_topic_score": 6.5,               # 话题热度
    "spread_confidence": 0.7,             # 传染置信度
    "topics": ["芯片"],                   # 相关主题
}
```

---

## 六、使用场景

### 6.1 场景一：美股大跌 + 新闻唱空（高共振）

```
输入：
  行情信号: -0.8 (美股大跌 4%)
  舆论信号: -0.7 (新闻唱空流动性)

共振检测：
  等级: HIGH (同向且都强)
  权重: 1.0
  最终信号: -0.8

预测：
  → A股流动性: 0.20 (极度紧张)
  → 港股流动性: 0.32 (紧张)

调整：
  高波动板块权重 × 0.8
  减少趋势追踪
  减少高频交易
```

### 6.2 场景二：行情平稳 + 新闻热议（低共振）

```
输入：
  行情信号: +0.1 (美股小涨 0.5%)
  舆论信号: +0.7 (新闻热议AI)

共振检测：
  等级: LOW (行情太弱)
  权重: 0.3
  最终信号: +0.03

预测：
  → A股流动性: 0.50 (几乎无影响)
  → 主题扩散: AI主题 热度6.0 传染概率54%

调整：
  AI相关板块权重 × 1.2
  其他板块无影响
```

### 6.3 场景三：行情涨 + 新闻唱空（背离）

```
输入：
  行情信号: +0.6 (美股上涨 3%)
  舆论信号: -0.5 (新闻担忧通胀)

共振检测：
  等级: DIVERGENT (反向)
  权重: 0.3
  最终信号: +0.18

调整：
  保持谨慎
  权重降低
```

---

## 七、预测有效期配置（动态 TTL）

> **重要更新**：预测有效期改为**动态 TTL**，基于市场交易时段计算，不再是固定值。

### 7.1 动态 TTL 计算规则

```
市场开盘中 → TTL = 距当前交易时段结束的剩余时间
市场未开盘 → TTL = 距下一个交易时段结束的完整时间
市场已收盘 → TTL = 明天交易时段长度
```

### 7.2 各市场交易时段

| 市场 | 交易时段 | 动态 TTL 范围 |
|------|----------|---------------|
| A股 | 9:30-11:30 + 13:00-15:00（共4小时） | 盘中实时计算 |
| 港股 | 9:30-12:00 + 13:00-16:00（共4.5小时） | 盘中实时计算 |
| 美股 | 9:30-16:00 EST（共6.5小时） | 盘中实时计算 |

### 7.3 设计原理

为什么不用固定 TTL？

- **5分钟太短**：盘中4小时内信号持续有效，5分钟就被清除
- **30分钟太长**：如果美股收盘后检测到信号，30分钟后第二天市场已变
- **动态 TTL**：信号有效期 = 一个完整的交易时段，确保盘中信号不被过早清除

---

## 八、完整闭环机制

### 8.1 闭环设计

流动性预测体系采用**预测 → 验证 → 解除**的完整闭环设计，确保每个市场的预测都能得到验证和正确处理：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        完整闭环流程                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     预测阶段                                  │   │
│  │                                                              │   │
│  │  predict_liquidity(source_market, signals)                 │   │
│  │       │                                                     │   │
│  │       ├── 计算源市场流动性信号                               │   │
│  │       ├── 对每个目标市场生成预测                             │   │
│  │       │    • signal: 0-1                                   │   │
│  │       │    • confidence: 置信度                            │   │
│  │       │    • valid_until: TTL（300秒）                      │   │
│  │       │    • adjustment: 调整指令                          │   │
│  │       └── 存储到 _predictions                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                        │
│                              ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     验证阶段                                  │   │
│  │                                                              │   │
│  │  verify_liquidity(target_market, actual_data)              │   │
│  │       │                                                     │   │
│  │       ├── 积累数据点（需要5个）                             │   │
│  │       ├── 计算实际流动性信号                                 │   │
│  │       ├── 比较：|avg_actual - expected|                    │   │
│  │       │                                                     │   │
│  │       └── diff > 0.25 → should_relax = True (预判错误)      │   │
│  │           diff ≤ 0.25 → should_relax = False (预判正确)     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                        │
│                              ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     解除阶段                                  │   │
│  │                                                              │   │
│  │  get_liquidity_adjustment(target_market)                    │   │
│  │       │                                                     │   │
│  │       ├── 检查：time.time() > valid_until（预测过期）       │   │
│  │       ├── 检查：should_relax（验证失败）                    │   │
│  │       │                                                     │   │
│  │       └── 任一条件满足 → 返回解除限制指令                     │   │
│  │                        │                                     │   │
│  │                        ▼                                     │   │
│  │               _generate_relaxation_adjustment()            │   │
│  │                        │                                     │   │
│  │                        ▼                                     │   │
│  │               板块权重回调 × 1.2                           │   │
│  │               策略预算恢复正常                               │   │
│  │               交易频率恢复                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 多市场闭环

所有预测的市场都有独立的验证和解除机制：

```
┌─────────────────────────────────────────────────────────────────────┐
│                      多市场闭环支持                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  预测: predict_liquidity(US, signals)                               │
│       │                                                              │
│       ├── → A股: signal=0.24, TTL=300s                            │
│       ├── → 港股: signal=0.38, TTL=300s                           │
│       └── → 美股: (如果有对美股的预测)                              │
│                                                                      │
│  验证: verify_liquidity(market, actual_data)                        │
│       │                                                              │
│       ├── A股: 5个数据点 → 保持/解除                               │
│       ├── 港股: 5个数据点 → 保持/解除                               │
│       └── 美股: 5个数据点 → 保持/解除                               │
│                                                                      │
│  解除: get_liquidity_adjustment(market)                             │
│       │                                                              │
│       ├── A股: 过期/失败 → 解除                                    │
│       ├── 港股: 过期/失败 → 解除                                    │
│       └── 美股: 过期/失败 → 解除                                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.3 便捷方法

系统提供了多个便捷方法支持不同场景：

```python
# 方法1：获取指定市场的调整（可同时验证）
adjustment = scanner.get_liquidity_adjustment(
    LiquiditySignalType.CHINA_A,
    actual_data={'change_pct': -1.5, 'volume_ratio': 0.8}
)

# 方法2：获取所有市场的调整
all_adjustments = scanner.get_all_market_adjustments()
# {'china_a': {...}, 'hk': {...}, ...}

# 方法3：自动验证所有预测的市场
scanner.auto_verify_all_predictions({
    LiquiditySignalType.CHINA_A: {'change_pct': -1.5, 'volume_ratio': 0.8},
    LiquiditySignalType.HONG_KONG: {'change_pct': -1.0, 'volume_ratio': 0.9},
})

# 方法4：一键完成预测+验证
predictions = scanner.predict_and_auto_verify(
    source_market=LiquiditySignalType.US,
    signals={'change_pct': -3.0, 'volume_ratio': 0.7},
    market_data_map={
        LiquiditySignalType.CHINA_A: {'change_pct': -2.0, 'volume_ratio': 0.6},
        LiquiditySignalType.HONG_KONG: {'change_pct': -1.5, 'volume_ratio': 0.7},
    }
)
```

---

## 九、双维度决策框架：大盘宏观 vs 定价检测

> **核心洞察**：大盘下跌 = 流动性不足（宏观、持续）；个股/板块下跌 = 定价问题（微观、一次性）。

### 9.1 两个维度的区分

| | 大盘宏观流动性 | 定价检测 |
|---|---|---|
| **问的是** | 市场整体流动性是松还是紧？ | 这个信息有没有被市场消化？ |
| **信号来源** | 所有市场平均涨跌 | 源市场信号方向 vs 目标市场开盘方向 |
| **性质** | **持续状态** | **一次性事件** |
| **典型场景** | 大盘平均跌3% | 特斯拉财报后股价直接跌10% |
| **是否干预** | **无条件降仓** | 精细化操作（要不要追热点） |
| **影响** | 仓位、频率、策略预算 | 板块级注意力分配 |

### 9.2 定价检测逻辑

```python
_check_if_priced(target, source_signal, source_market) -> (is_priced, reason, priced_at_open)
```

| 情况 | 判定 | 说明 |
|------|------|------|
| 源市场信号方向 = 目标市场开盘方向 | **已定价** | 信息已被消化，干预意义不大 |
| 源市场信号方向 ≠ 目标市场开盘方向 | **未定价** | 可以反向操作 |
| 目标市场几乎平开 | **未定价** | 完全没消化，高价值信号 |
| 信号太弱（\|signal-0.5\| ≤ 0.15） | 无法判断 | 保守处理 |

### 9.3 定价检测5种情况

| Case | 美股信号 | A股开盘 | 判定 | 干预价值 |
|------|----------|---------|------|----------|
| **1** | 暴跌-3% | 低开-1.5%（同向） | ✅ 已定价 | 低（半山腰降仓意义不大） |
| **2** | 暴跌-3% | 几乎平开+0.05% | ❌ 未定价 | **高**（可以提前布局） |
| **3** | 暴跌-3% | 高开+0.5%（反向） | ❌ 未定价 | 中（反向操作机会） |
| **4** | 小跌-1%（信号弱） | -0.5% | ⚠️ 无法判断 | 保守处理 |
| **5** | 财报后直接跌10% | A股相关板块直接跟跌 | ✅ 已定价 | 低（一次性事件） |

### 9.4 最终干预链路

```
市场数据变化
    │
    ├── 大盘平均涨跌 → AttentionOrchestrator._update_macro_liquidity_from_scanner()
    │                        │
    │                        ├── 计算 avg_change（所有市场平均）
    │                        ├── 计算 raw_signal = f(avg_change, phase_factor)
    │                        ├── raw_signal < 0.4 → 流动性紧张
    │                        │
    │                        └── 无条件执行：
    │                             _apply_liquidity_to_sector_attention()
    │                             _apply_liquidity_to_strategy_budget()
    │                             _apply_liquidity_to_frequency()
    │
    └── 板块级精细化 → _check_if_priced()（定价检测）
                              ├── is_priced=True → 跳过
                              └── is_priced=False → SectorHunter 可以追热点

关键点：大盘宏观流动性判断独立于定价检测。无论定价与否，大盘跌了就要降仓。
```

---

## 十、AttentionOrchestrator 集成

### 10.1 数据流

```
GlobalMarketScanner
       │
       ├── predict_liquidity(US, us_signals)
       │        │
       │        ↓
       │   [LiquidityPrediction for CHINA_A]
       │
       ├── detect_resonance(market_signal, narrative_signal)
       │        │
       │        ↓
       │   [ResonanceResult]
       │
       ├── verify_liquidity(CHINA_A, a_share_data)
       │        │
       │        ↓
       │   [LiquidityVerification]
       │
       └── get_liquidity_adjustment(CHINA_A)
                │
                ↓
        AttentionOrchestrator
                │
                ├── _apply_liquidity_to_sector_attention()
                ├── _apply_liquidity_to_strategy_budget()
                └── _apply_liquidity_to_frequency()
```

---

## 十、监控与调试

### 10.1 获取状态

```python
scanner = get_global_market_scanner()
status = scanner.get_liquidity_status()
```

### 10.2 输出示例

```python
{
    "predictions": {
        "china_a": {
            "signal": 0.25,
            "confidence": 0.5,
            "source_signals": ["us: 0.5"],
            "is_valid": True
        }
    },
    "verifications": {
        "china_a": {
            "expected": 0.25,
            "verification_count": 7,
            "verified": True,
            "should_relax": False
        }
    },
    "resonance": {
        "level": "high",
        "confidence": 0.9,
        "alignment": 0.95,
        "weight": 1.0,
        "market_signal": -0.8,
        "narrative_signal": -0.7
    },
    "topic_predictions": {
        "芯片": {
            "target_sectors": ["半导体", "集成电路"],
            "spread_probability": 0.7,
            "expected_change": 2.1,
            "heat_score": 4.5
        }
    }
}
```

---

## 十一、扩展性设计

### 11.1 新增市场

只需在 `LiquiditySignalType` 和传染概率矩阵中添加：

```python
class LiquiditySignalType(Enum):
    # ... 现有 ...
    JAPAN = "japan"          # 日股
    EUROPE = "europe"       # 欧股
```

### 11.2 新增主题

只需在主题映射和传染概率中添加：

```python
TOPIC_SECTOR_MAPPING = {
    # ... 现有 ...
    "机器人": {"a_share_sectors": ["机器人", "自动化"], "us_sector": "BOTZ"},
}

CROSS_MARKET_PROB = {
    # ... 现有 ...
    "机器人": 0.5,
}
```

---

## 十二、注意事项

### 12.1 信号太弱的处理

- 当行情信号或舆论信号太弱（<0.2）时，判定为低共振
- 这是为了避免单方面信号误导

### 12.2 验证时机

- A股市场必须积累 **5 个数据点**后才能验证
- 这是为了避免单日数据的偶然性

### 12.3 误判处理

- 如果预判错误（实际与预期差异 > 0.25），立即解除限制
- 这是系统的自我纠错机制

---

## 十三、总结

流动性预测体系是 Naja 注意力操作系统的重要组成部分，实现了：

1. **信号共振检测**：行情和舆论一致时权重最高，背离时权重降低
2. **宏观流动性预测**：基于全球市场信号预测各市场流动性
3. **主题扩散预测**：基于美股热门板块预测A股同名板块联动
4. **完整闭环机制**：预测 → 验证 → 解除，对所有市场独立执行
5. **多市场支持**：A股、港股、美股、期货等市场独立预测和验证
6. **自我纠错**：预判错误或预测过期时自动解除限制
7. **灵活扩展**：易于添加新市场和新主题

### 核心优势

| 特性 | 说明 |
|------|------|
| **闭环自动化** | 预测、验证、解除全程自动执行，无需人工干预 |
| **多市场独立** | 每个市场有独立的验证状态，互不干扰 |
| **失效保护** | 预测过期自动解除，避免过时信息影响决策 |
| **自我纠错** | 验证失败自动解除，避免错误预判持续影响 |

通过这个体系，Naja 能够更好地适应全球金融市场的联动效应，提前调整交易策略，提高交易质量。

---

*文档版本：3.0*
*最后更新：2026-03-30*
