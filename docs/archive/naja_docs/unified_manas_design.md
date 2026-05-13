# UnifiedManas 整合方案

> 日期: 2026-03-31
> 目标: 统一 ManasEngine + AdaptiveManas 为单一决策框架

## 一、背景

现有两套 Manas：
1. **ManasEngine** (`attention/kernel/manas_engine.py`) - AttentionKernel 的决策模块
2. **AdaptiveManas** (`manas/adaptive_manas.py`) - AwakenedSystem 的顺应决策

两套系统各自发展，职责重叠，数据割裂。

## 二、整合目标

```
持仓数据 ──→ UnifiedManas ──→ attention_focus (止盈/止损/再平衡)
                    │
                    ├──→ Attention Kernel (Q 塑造)
                    ├──→ AwakenedAlaya (顿悟触发)
                    └──→ FeedbackLoop (闭环学习)
```

## 三、架构设计

### 3.1 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **UnifiedManas** | `unified_manas.py` | 统一决策中枢 |
| **UnifiedManasOutput** | `output.py` | 统一输出数据类 |
| **PortfolioDrivenEventRecall** | `event_recall.py` | 持仓驱动事件召回 |
| **ManasFeedbackLoop** | `feedback_loop.py` | 完整闭环反馈 |
| **AwakeningEngine** (扩展) | `alaya/epiphany_engine.py` | 持仓顿悟触发 |

### 3.2 UnifiedManasOutput 统一输出

```python
@dataclass
class UnifiedManasOutput:
    # ===== 基础分数 =====
    manas_score: float = 0.5           # 综合分数
    timing_score: float = 0.5          # 时机分数
    regime_score: float = 0.0          # 环境分数 [-1, 1]
    confidence_score: float = 0.5      # 自信分数

    # ===== Attention Kernel 用 =====
    attention_focus: str = "watch"      # watch/stop_loss/take_profit/rebalance
    alpha: float = 1.0                 # 置信度因子
    risk_temperature: float = 1.0       # 风险温度

    # ===== Awakened System 用 =====
    harmony_state: str = "neutral"      # resonance/neutral/resistance
    harmony_strength: float = 0.5       # 和谐程度
    action_type: str = "hold"           # hold/act_fully/act_carefully/act_minimally

    # ===== 决策 =====
    should_act: bool = False
    bias_state: str = "neutral"         # neutral/greed/fear
    bias_correction: float = 1.0

    # ===== 持仓状态 =====
    portfolio_signal: str = "none"      # none/stop_loss/take_profit/rebalance/accumulate
    portfolio_loss_pct: float = 0.0
    market_deterioration: bool = False
```

### 3.3 PortfolioDrivenEventRecall

```python
class PortfolioDrivenEventRecall:
    def recall(
        self,
        manas_output: UnifiedManasOutput,
        portfolio_state: Dict,
        market_data: Dict
    ) -> List[AttentionEvent]:
        """
        根据 ManasOutput 的 attention_focus 召回相关事件

        focus=stop_loss: 召回高亏损持仓 + 市场恶化事件
        focus=take_profit: 召回高盈利持仓 + 市场转弱事件
        focus=rebalance: 召回板块偏离事件
        """
```

### 3.4 ManasFeedbackLoop

```python
class ManasFeedbackLoop:
    def record(
        self,
        decision: UnifiedManasOutput,
        recalled_events: List[AttentionEvent],
        outcome: Dict[str, Any]  # pnl, market_state, etc.
    ):
        """
        记录决策→召回→结果的完整闭环
        用于 MetaManas 学习优化
        """

    def get_focus_effectiveness(self, focus: str) -> float:
        """
        获取某种 attention_focus 的历史有效性
        """
```

## 四、数据流

```
1. Market Data + Portfolio Data 输入
         ↓
2. UnifiedManas.compute()
   - TimingEngine: 时机判断
   - RegimeEngine: 环境判断
   - ConfidenceEngine: 自信判断
   - RiskEngine: 风险温度
   - TianShiResponse: 天时响应
   - RegimeHarmony: 环境和谐
   - RenShiResponse: 人时响应
   - MetaManas: 偏差检测
         ↓
3. UnifiedManasOutput
   - attention_focus → 事件召回
   - harmony_state → 顿悟触发
   - should_act → 交易执行
         ↓
4. PortfolioDrivenEventRecall.recall()
   - 根据 focus 召回相关事件
         ↓
5. AttentionKernel.process()
   - 处理召回事件
         ↓
6. 交易执行 → 结果反馈
         ↓
7. ManasFeedbackLoop.record()
   - 记录闭环
   - MetaManas 学习优化
```

## 五、文件清单

| 操作 | 文件路径 |
|------|---------|
| 新建 | `deva/naja/manas/unified_manas.py` |
| 新建 | `deva/naja/manas/output.py` |
| 新建 | `deva/naja/manas/event_recall.py` |
| 新建 | `deva/naja/manas/feedback_loop.py` |
| 修改 | `deva/naja/manas/adaptive_manas.py` |
| 修改 | `deva/naja/alaya/epiphany_engine.py` |
| 修改 | `deva/naja/alaya/awakened_alaya.py` |
| 修改 | `deva/naja/attention/kernel/kernel.py` |
| 修改 | `deva/naja/manas/__init__.py` |
| 修改 | `deva/naja/alaya/__init__.py` |

## 六、兼容性

- 保留 `ManasEngine` 和 `AdaptiveManas` 的外部接口
- 新增 `UnifiedManas` 作为主入口
- 通过适配器模式逐步迁移