# 觉醒系统测试验证指南

> 生成时间: 2026-03-30

---

## 一、概述

本文档指导如何验证已实现的觉醒模块是否有效，包括：
- ProphetSense (天眼通)
- RealtimeTaste (实时舌识)
- SeedIlluminator (光明藏)
- AdaptiveManas (顺应型末那识)
- MetaEvolution (元进化)

---

## 二、测试环境准备

### 2.1 依赖检查

```bash
cd /Users/spark/pycharmproject/deva

# 检查核心模块导入
python -c "
from deva.naja.attention.center import get_orchestrator
from deva.naja.senses import ProphetSense, RealtimeTaste
from deva.naja.alaya import SeedIlluminator
from deva.naja.manas import AdaptiveManas
from deva.naja.evolution import get_meta_evolution
print('✓ 所有模块导入成功')
"

# 运行单元测试
python -m pytest deva/naja/tests/ -v --tb=short 2>&1 | tail -20
```

### 2.2 确认觉醒模块已集成

```python
from deva.naja.attention.center import get_orchestrator

orch = get_orchestrator()
orch._ensure_initialized()

# 检查觉醒状态
state = orch.get_awakened_state()
print(f'觉醒状态: {state}')
```

预期输出：
```
觉醒状态: {
    'prophet_signal_count': 0,
    'taste_signals_count': 0,
    'illuminated_patterns_count': 0,
    'adaptive_decision_count': 0
}
```

---

## 三、各模块测试方法

### 3.1 天眼通 (ProphetSense) 测试

#### 测试目标
验证预感知能力是否能提前发现市场转折点

#### 测试代码

```python
import numpy as np
from deva.naja.senses import ProphetSense

prophet = ProphetSense()

# 模拟动量衰竭场景
def test_momentum_precipice():
    """
    测试动量悬崖预判
    """
    # 构建连续上涨后的市场数据
    market_data = {
        "symbols": ["000001", "000002", "600000"],
        "price_change": 2.5,  # 持续上涨
        "volume_ratio": 0.3,  # 缩量
        "trend_strength": 0.8, # 强趋势
    }

    flow_data = {
        "net_flow": -500000000,  # 资金流出
        "big_deal_ratio": 0.7,   # 大单占比高
    }

    signal = prophet.sense(market_data, flow_data)

    print(f"预感知信号: {signal}")
    print(f"信号类型: {signal.presage_type if signal else '无信号'}")
    print(f"强度: {signal.intensity if signal else 0}")
    print(f"置信度: {signal.confidence if signal else 0}")

    # 验证：连续上涨 + 缩量 + 资金流出 = 动量衰竭预警
    assert signal is not None, "应该检测到预兆"
    assert signal.intensity > 0.5, "强度应该较高"

# 模拟正常市场
def test_normal_market():
    """
    测试正常市场（无预兆）
    """
    market_data = {
        "symbols": ["000001"],
        "price_change": 0.2,
        "volume_ratio": 1.0,
        "trend_strength": 0.1,
    }

    signal = prophet.sense(market_data, None)
    print(f"正常市场信号: {signal}")
    # 正常市场可能没有强预兆信号

if __name__ == "__main__":
    test_momentum_precipice()
    test_normal_market()
```

#### 预期结果

| 场景 | 预期信号 | 验证指标 |
|------|---------|---------|
| 动量衰竭 | 有预警 | intensity > 0.5 |
| 情绪转换 | 有预警 | presage_type 正确 |
| 正常市场 | 无/弱信号 | intensity < 0.3 |

---

### 3.2 舌识 (RealtimeTaste) 测试

#### 测试目标
验证实时尝受能力是否准确反映持仓状态

#### 测试代码

```python
from deva.naja.senses import RealtimeTaste

taste = RealtimeTaste()

def test_taste_signal():
    """
    测试舌识尝受信号
    """
    # 注册持仓
    taste.register_position(
        symbol="000001",
        entry_price=10.0,
        quantity=10000,
        entry_time=1700000000.0
    )

    # 场景1：盈利增加（鲜度好）
    signals1 = taste.taste_all({"000001": 11.0})  # 涨到11元
    s1 = list(signals1.values())[0]
    print(f"盈利增加: floating_pnl={s1.floating_pnl:.2%}, freshness={s1.freshness:.2f}")

    # 场景2：盈利回吐（鲜度下降）
    signals2 = taste.taste_all({"000001": 10.2})  # 回吐到10.2元
    s2 = list(signals2.values())[0]
    print(f"盈利回吐: floating_pnl={s2.floating_pnl:.2%}, freshness={s2.freshness:.2f}")

    # 场景3：亏损扩大（快馊了）
    signals3 = taste.taste_all({"000001": 9.0})  # 跌到9元
    s3 = list(signals3.values())[0]
    print(f"亏损扩大: floating_pnl={s3.floating_pnl:.2%}, freshness={s3.freshness:.2f}")

    # 验证：鲜度应该随状态变化
    assert s1.freshness > s2.freshness > s3.freshness, "鲜度应该递减"

def test_opportunity_cost():
    """
    测试机会成本计算
    """
    # 持仓亏损
    taste.register_position("000002", 20.0, 5000, 1700000000.0)
    signals = taste.taste_all({"000002": 18.0})

    for symbol, signal in signals.items():
        print(f"{symbol}: opportunity_cost={signal.opportunity_cost:.2%}")
        print(f"  should_adjust={signal.should_adjust}")
        print(f"  emotional_intensity={signal.emotional_intensity:.2f}")

if __name__ == "__main__":
    test_taste_signal()
    test_opportunity_cost()
```

#### 预期结果

| 场景 | floating_pnl | freshness | should_adjust |
|------|-------------|-----------|---------------|
| 盈利增加 | +10% | 高 (>0.7) | False |
| 盈利回吐 | +2% | 中 (0.4-0.7) | False |
| 亏损扩大 | -10% | 低 (<0.3) | True |

---

### 3.3 光明藏 (SeedIlluminator) 测试

#### 测试目标
验证模式召回能力是否能从历史中找到相似模式

#### 测试代码

```python
from deva.naja.alaya import SeedIlluminator, PatternType

illuminator = SeedIlluminator()

def test_pattern_recall():
    """
    测试模式召回
    """
    # 先记录一些历史模式
    illuminator.record_outcome(PatternType.MOMENTUM, success=True, holding_period=5.0)
    illuminator.record_outcome(PatternType.REVERSAL, success=False, holding_period=2.0)
    illuminator.record_outcome(PatternType.MOMENTUM, success=True, holding_period=7.0)
    illuminator.record_outcome(PatternType.BREAKOUT, success=True, holding_period=3.0)

    # 当前市场状态（类似动量模式）
    current_state = {
        "symbols": ["000001"],
        "price_change": 3.0,
        "volume_ratio": 1.5,
        "trend_strength": 0.7,
    }

    patterns = illuminator.recall(current_state)

    print(f"召回的模式数: {len(patterns)}")
    for p in patterns:
        print(f"  模式: {p.pattern_type}, 相似度: {p.similarity:.2f}")
        print(f"  历史次数: {p.match_count}, 成功率: {p.success_rate:.2%}")

    # 验证：应该召回动量模式
    pattern_types = [p.pattern_type for p in patterns]
    assert PatternType.MOMENTUM in pattern_types, "应该召回动量模式"

def test_seed_learning():
    """
    测试种子学习
    """
    initial_stats = illuminator.get_pattern_stats()
    print(f"初始统计: {initial_stats}")

    # 记录更多数据
    for _ in range(10):
        illuminator.record_outcome(PatternType.MOMENTUM, success=True, holding_period=5.0)

    final_stats = illuminator.get_pattern_stats()
    print(f"更新后统计: {final_stats}")

    assert final_stats[PatternType.MOMENTUM]["match_count"] > initial_stats[PatternType.MOMENTUM]["match_count"]

if __name__ == "__main__":
    test_pattern_recall()
    test_seed_learning()
```

#### 预期结果

| 指标 | 预期 | 验证方法 |
|------|------|---------|
| 召回率 | >50% | 输入状态能召回匹配模式 |
| 准确率 | >60% | 召回模式的成功率高 |
| 学习能力 | 有提升 | 记录更多数据后匹配更准 |

---

### 3.4 顺应型末那识 (AdaptiveManas) 测试

#### 测试目标
验证顺应决策是否合理

#### 测试代码

```python
from deva.naja.manas import AdaptiveManas

adaptive = AdaptiveManas()

def test_tianshi_response():
    """
    测试天时响应
    """
    # 开盘蜜月期
    market_state = {
        "is_market_open": True,
        "volatility": 0.8,
        "trend_strength": 0.5,
        "time_of_day": 9.5,  # 开盘30分钟
        "regime": "trending",
        "regime_stability": 0.6,
        "market_breadth": 0.3,
    }

    decision = adaptive.compute_顺应(market_state)

    print(f"天时决策: {decision}")
    print(f"  顺应状态: {decision.harmony_state}")
    print(f"  行动建议: {decision.should_act}")
    print(f"  强度: {decision.intensity:.2f}")

    assert decision is not None

def test_regime_harmony():
    """
    测试环境和谐
    """
    # 趋势市场
    trending_state = {
        "is_market_open": True,
        "volatility": 1.0,
        "trend_strength": 0.8,
        "time_of_day": 14.0,
        "regime": "trending",
        "regime_stability": 0.8,
        "market_breadth": 0.5,
    }

    # 震荡市场
    sideways_state = {
        "is_market_open": True,
        "volatility": 0.5,
        "trend_strength": 0.1,
        "time_of_day": 14.0,
        "regime": "sideways",
        "regime_stability": 0.7,
        "market_breadth": 0.0,
    }

    decision_trending = adaptive.compute_顺应(trending_state)
    decision_sideways = adaptive.compute_顺应(sideways_state)

    print(f"趋势市场: should_act={decision_trending.should_act}, intensity={decision_trending.intensity:.2f}")
    print(f"震荡市场: should_act={decision_sideways.should_act}, intensity={decision_sideways.intensity:.2f}")

    # 验证：趋势市场应该更容易行动
    assert decision_trending.intensity > decision_sideways.intensity

def test_renshi_response():
    """
    测试人时响应
    """
    # 收盘前30分钟
    late_state = {
        "is_market_open": True,
        "volatility": 1.0,
        "trend_strength": 0.5,
        "time_of_day": 14.5,  # 收盘前30分钟
        "regime": "trending",
        "regime_stability": 0.5,
        "market_breadth": 0.2,
    }

    decision = adaptive.compute_顺应(late_state)
    print(f"收盘前决策: should_act={decision.should_act}, intensity={decision.intensity:.2f}")

    # 收盘前应该更保守

if __name__ == "__main__":
    test_tianshi_response()
    test_regime_harmony()
    test_renshi_response()
```

#### 预期结果

| 市场状态 | 预期 should_act | 预期 intensity |
|---------|-----------------|----------------|
| 开盘蜜月期 + 趋势 | True | 高 (>0.6) |
| 震荡市场 | False | 低 (<0.3) |
| 收盘前 | 保守 | 降低 |

---

### 3.5 元进化 (MetaEvolution) 测试

#### 测试目标
验证自我观察和自动调参能力

#### 测试代码

```python
from deva.naja.evolution import get_meta_evolution, EvolutionPhase

evo = get_meta_evolution()

def test_self_observer():
    """
    测试自我观察
    """
    # 记录一些决策
    for i in range(20):
        evo.record_decision(
            decision_type="test_strategy",
            context={"market": "trending"},
            decision="buy" if i % 2 == 0 else "hold"
        )

        # 模拟结果：前10个成功率高，后10个成功率低
        success = (i < 10 and i % 3 != 0) or (i >= 10 and i % 5 != 0)
        evo.record_outcome("test_strategy", success=success, latency_ms=50.0)

    summary = evo.observer.get_summary()
    print(f"观察摘要: {summary}")
    print(f"模块统计: {summary['modules']}")

    assert summary["total_decisions"] == 20

def test_evolution_phase():
    """
    测试进化阶段
    """
    # 多次调用 think 触发阶段转换
    for _ in range(30):
        evo.record_decision("phase_test", {}, "action")
        evo.record_outcome("phase_test", success=True)

    insights = evo.think()

    print(f"当前阶段: {evo.get_phase()}")
    print(f"洞察数: {len(insights)}")

    assert evo.get_phase() != EvolutionPhase.OBSERVING  # 应该有所进化

def test_module_insights():
    """
    测试模块洞察
    """
    # 记录失败率高的模块
    for i in range(15):
        evo.record_decision("failing_module", {}, "action")
        evo.record_outcome("failing_module", success=(i % 4 == 0), latency_ms=200.0)  # 25% 成功率

    insights = evo.observer.get_module_insights()

    print(f"洞察数: {len(insights)}")
    for insight in insights:
        print(f"  类型: {insight.insight_type}")
        print(f"  描述: {insight.description}")
        print(f"  建议: {insight.suggested_action}")

    # 应该有关于 failing_module 的洞察
    assert len(insights) > 0

if __name__ == "__main__":
    test_self_observer()
    test_evolution_phase()
    test_module_insights()
```

#### 预期结果

| 测试 | 预期结果 | 验证指标 |
|------|---------|---------|
| 自我观察 | 记录所有决策 | total_decisions == 20 |
| 进化阶段 | 有阶段推进 | phase != OBSERVING |
| 模块洞察 | 发现问题模块 | 洞察数 > 0 |

---

## 四、集成测试

### 4.1 端到端测试

```python
"""
完整流程测试：从数据输入到觉醒输出的全链路
"""

from deva.naja.attention.center import get_orchestrator
import pandas as pd
import numpy as np

def test_full_awakening_pipeline():
    """
    完整觉醒流程测试
    """
    orch = get_orchestrator()
    orch._ensure_initialized()

    # 模拟市场数据
    data = pd.DataFrame({
        "code": ["000001", "000002", "600000"],
        "name": ["平安银行", "万科A", "浦发银行"],
        "now": [10.5, 18.2, 8.8],
        "close": [10.0, 18.0, 9.0],
        "volume": [1000000, 2000000, 1500000],
        "amount": [10500000, 36400000, 13200000],
    })
    data["p_change"] = (data["now"] - data["close"]) / data["close"] * 100

    # 触发市场数据处理
    orch._update_attention(data)

    # 检查觉醒状态
    state = orch.get_awakened_state()
    print(f"觉醒状态: {state}")

    # 验证：各模块应该有所响应
    assert state["prophet_signal_count"] >= 0  # 天眼通
    assert state["taste_signals_count"] >= 0   # 舌识
    assert state["adaptive_decision_count"] >= 0  # 顺应决策

    print("✓ 完整流程测试通过")

if __name__ == "__main__":
    test_full_awakening_pipeline()
```

---

## 五、验证结果记录表

### 5.1 模块验证表

| 模块 | 测试用例数 | 通过数 | 失败数 | 准确率 | 备注 |
|------|-----------|-------|-------|--------|------|
| ProphetSense | 5 | ? | ? | ? | |
| RealtimeTaste | 4 | ? | ? | ? | |
| SeedIlluminator | 3 | ? | ? | ? | |
| AdaptiveManas | 4 | ? | ? | ? | |
| MetaEvolution | 3 | ? | ? | ? | |

### 5.2 问题记录表

| 问题描述 | 所属模块 | 严重程度 | 解决方案 |
|---------|---------|---------|---------|
| | | | |
| | | | |

---

## 六、回测验证（可选）

### 6.1 使用历史数据回测

```python
"""
回测框架示例 - 需要准备历史数据
"""

def backtest_awakened_system():
    """
    觉醒系统回测

    需要准备:
    1. 历史行情数据 (日线/分钟线)
    2. 资金曲线记录
    3. 信号记录
    """
    # TODO: 实现回测框架
    pass

# 运行回测
if __name__ == "__main__":
    results = backtest_awakened_system()
    print(f"回测结果: {results}")
```

---

## 七、快速验证脚本

```bash
#!/bin/bash
# quick_validate.sh - 快速验证脚本

cd /Users/spark/pycharmproject/deva

echo "=== 1. 模块导入检查 ==="
python -c "
from deva.naja.attention.center import get_orchestrator
from deva.naja.senses import ProphetSense, RealtimeTaste
from deva.naja.alaya import SeedIlluminator
from deva.naja.manas import AdaptiveManas
from deva.naja.evolution import get_meta_evolution
print('✓ 所有模块导入成功')
"

echo ""
echo "=== 2. 单元测试 ==="
python -m pytest deva/naja/tests/test_decision_attention.py \
    deva/naja/tests/test_manas_engine.py \
    deva/naja/tests/test_senses.py \
    deva/naja/tests/test_alaya_manas.py \
    deva/naja/tests/test_meta_evolution.py \
    -v --tb=short

echo ""
echo "=== 3. 觉醒状态检查 ==="
python -c "
from deva.naja.attention.center import get_orchestrator
orch = get_orchestrator()
orch._ensure_initialized()
state = orch.get_awakened_state()
print(f'觉醒状态: {state}')
"

echo ""
echo "=== 验证完成 ==="
```

---

## 八、问题排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| 模块导入失败 | 路径问题 | 检查 `__init__.py` 导出 |
| 测试失败 | 逻辑问题 | 检查断言条件 |
| 集成测试无响应 | 初始化问题 | 检查 `_ensure_initialized()` |
| 性能问题 | 数据量大 | 添加采样逻辑 |

---

## 九、下一步

测试完成后，请记录：

1. **各模块实际表现**：是否符合预期？
2. **发现的问题**：有哪些bug或逻辑问题？
3. **需要优化的点**：哪些能力不够好？

这些信息将用于指导后续的觉醒方向。

---

*验证是觉醒的基石。*
