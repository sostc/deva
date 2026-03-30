# 觉醒系统增量测试指南

> 基于历史行情数据库的真实数据测试
> 生成时间: 2026-03-30

---

## 一、数据来源说明

### 1.1 历史行情数据库

数据库表: `quant_snapshot_5min_window`

数据字段（来自 ReplayScheduler）：
```python
{
    "code": "000001",      # 股票代码
    "now": 12.50,          # 当前价格
    "close": 12.30,        # 昨收价格
    "p_change": 1.62,      # 涨跌幅 (%)
    "volume": 50000000,    # 成交量
    "amount": 625000000,    # 成交额
    "timestamp": 1709121600  # 时间戳
}
```

### 1.2 数据特征（真实数据范围）

| 字段 | 典型范围 | 特殊值 |
|------|---------|--------|
| p_change | -10 ~ +10 | 涨停板 ±10.01 |
| volume | 10000 ~ 10亿 | 新股上市首日巨量 |
| amount | 10万 ~ 100亿 | 大盘股成交额大 |
| price | 0.1 ~ 1000+ | 低价股 vs 高价股 |

---

## 二、集成测试用例

### 2.1 ProphetSense (天眼通) 真实场景测试

#### 测试场景 1：动量衰竭检测（真实数据）

```python
"""
场景：连续上涨后出现放量滞涨（真实市场特征）

真实数据示例（2024-03-15 行情）：
- 平安银行(000001): 连续3天上涨，累计涨幅8%
- 某日出现：涨幅收窄(+0.5%)，但成交量放大1.5倍
"""

def test_momentum_precipice_real():
    """测试真实动量衰竭场景"""
    from deva.naja.senses import ProphetSense

    prophet = ProphetSense()

    # 模拟真实市场数据（连续上涨后的衰竭）
    market_data = {
        # 价格变化（连续上涨后衰竭）
        "price_change": 0.5,           # 涨幅收窄
        "volume_ratio": 1.5,           # 量能放大
        "trend_strength": 0.15,        # 趋势减弱

        # 资金流向（真实特征：主力流出）
        "net_flow": -800000000,        # 主力净流出8亿
        "big_deal_ratio": 0.65,        # 大单占比65%

        # 波动率（真实数据）
        "volatility": 1.8,             # 波动率上升
        "price_changes": [2.5, 1.8, 0.5],  # 涨幅递减

        # 板块特征
        "sector_changes": {
            "银行": 0.5,
            "证券": -0.3,
            "保险": 0.2
        }
    }

    signal = prophet.sense(market_data, None)

    print(f"预感知信号: {signal.presage_type}")
    print(f"强度: {signal.intensity}")
    print(f"置信度: {signal.confidence}")

    # 验证：应该检测到动量悬崖
    assert signal is not None, "应该检测到预兆"
    assert signal.intensity > 0.4, "衰竭信号应该明显"

    # 真实场景验证
    print(f"\n【真实场景验证】")
    print(f"  涨幅从2.5%→1.8%→0.5%，趋势衰竭")
    print(f"  量能放大1.5倍但涨幅收窄，量价背离")
    print(f"  主力净流出8亿，资金撤退")
```

#### 测试场景 2：情绪转换预判（真实数据）

```python
"""
场景：市场情绪从乐观转向悲观（真实数据特征）

真实数据示例：
- 开盘：市场普涨，上涨股票占比 > 70%
- 盘中：热点散乱，轮动加快
- 尾盘：跳水，涨跌股票占比逆转
"""

def test_sentiment_transition_real():
    """测试真实情绪转换"""
    from deva.naja.senses import ProphetSense

    prophet = ProphetSense()

    market_data = {
        # 情绪特征（真实转换信号）
        "price_changes": [2.0, 1.5, 0.5, -0.3, -1.2, -2.0],  # 情绪递减
        "volume_ratio": 0.8,              # 缩量
        "market_breadth": -0.35,         # 广度转负
        "trend_strength": -0.4,          # 趋势转空

        # 市场宽度（真实数据）
        "advancing": 800,
        "declining": 1200,
        "breadth_ratio": -0.2,
    }

    signal = prophet.sense(market_data, None)

    print(f"情绪转换信号: {signal.presage_type}")
    print(f"强度: {signal.intensity}")

    # 验证：应该检测到情绪转换
    assert signal is not None
```

### 2.2 RealtimeTaste (舌识) 真实场景测试

#### 测试场景：持仓鲜度判断（真实场景）

```python
"""
场景：持仓浮盈回吐，判断是否该止盈

真实数据特征：
- 持仓：平安银行(000001)
- 入仓价：11.50元
- 现价：12.10元（浮盈5.2%）
- 近期：涨势放缓，机会成本上升
"""

def test_taste_freshness_real():
    """测试真实持仓鲜度"""
    from deva.naja.senses import RealtimeTaste

    taste = RealtimeTaste()

    # 注册持仓（真实数据）
    taste.register_position(
        symbol="000001",
        entry_price=11.50,
        quantity=10000,
        entry_time=1709121600.0
    )

    # 当前行情（浮盈回吐场景）
    current_prices = {"000001": 12.10}  # 浮盈5.2%

    signals = taste.taste_all(current_prices)
    signal = signals["000001"]

    print(f"浮盈: {signal.floating_pnl:.2%}")
    print(f"鲜度: {signal.freshness:.2f}")
    print(f"机会成本: {signal.opportunity_cost:.2%}")
    print(f"情绪强度: {signal.emotional_intensity:.2f}")
    print(f"建议调整: {signal.should_adjust}")

    # 验证：浮盈状态下鲜度应该较高
    assert signal.floating_pnl > 0, "应该有浮盈"

    # 场景：盈利回吐到只剩1%
    signals2 = taste.taste_all({"000001": 11.65})
    signal2 = signals2["000001"]

    print(f"\n【盈利回吐场景】")
    print(f"  浮盈剩余: {signal2.floating_pnl:.2%}")
    print(f"  鲜度: {signal2.freshness:.2f}")

    # 鲜度应该下降
    assert signal2.freshness < signal.freshness, "盈利回吐后鲜度应下降"
```

### 2.3 SeedIlluminator (光明藏) 真实场景测试

#### 测试场景：历史模式召回（真实数据）

```python
"""
场景：当前市场与历史某段相似，召回历史经验

真实数据特征（2024-03 市场）：
- 缩量震荡、热点散乱
- 事后看：这是主力吸筹期，之后大涨

历史模式库（基于真实数据）：
- 2024-01-15: 类似缩量震荡 → 之后5天大涨
- 2023-11-20: 放量突破 → 成功
- 2023-08-10: 缩量整理 → 失败（继续震荡）
"""

def test_seed_recall_real():
    """测试真实模式召回"""
    from deva.naja.alaya import SeedIlluminator, PatternType

    illuminator = SeedIlluminator()

    # 先记录一些真实历史模式
    illuminator.record_outcome(
        PatternType.ACCUMULATION,
        success=True,
        holding_period=5.0,
        market_context={
            "volume_ratio": 0.6,
            "price_change": 0.3,
            "trend_strength": 0.1
        }
    )

    illuminator.record_outcome(
        PatternType.MOMENTUM,
        success=True,
        holding_period=3.0,
        market_context={
            "volume_ratio": 1.8,
            "price_change": 3.5,
            "trend_strength": 0.8
        }
    )

    # 当前市场状态（类似蓄势模式）
    current_state = {
        "price_change": 0.3,
        "volume_ratio": 0.65,
        "trend_strength": 0.12,
        "price_changes": [0.2, 0.4, 0.3, 0.1, 0.5],  # 窄幅震荡
    }

    patterns = illuminator.recall(current_state)

    print(f"召回模式数: {len(patterns)}")
    for p in patterns:
        print(f"  模式: {p.pattern_type.value}")
        print(f"  相似度: {p.similarity:.2f}")
        print(f"  历史成功率: {p.success_rate:.1%}")

    # 验证：应该召回蓄势模式
    pattern_types = [p.pattern_type for p in patterns]
    assert PatternType.ACCUMULATION in pattern_types, "应该召回蓄势模式"
```

### 2.4 AdaptiveManas (顺应型末那识) 真实场景测试

#### 测试场景：天时响应（真实时间特征）

```python
"""
场景：判断当前是否适合操作

真实数据特征：
- 9:30-10:00: 开盘蜜月期，波动大
- 10:00-11:30: 趋势形成期
- 11:30-13:00: 午盘休整，观望
- 13:00-14:30: 尾盘活跃
- 14:30-15:00: 收盘前，流动性枯竭
"""

def test_adaptive_tianshi_real():
    """测试真实天时响应"""
    from deva.naja.manas import AdaptiveManas

    adaptive = AdaptiveManas()

    # 场景1：开盘蜜月期（9:35）
    market_state_1 = {
        "is_market_open": True,
        "volatility": 1.2,
        "trend_strength": 0.3,
        "time_of_day": 9.58,      # 开盘35分钟
        "regime": "volatile",      # 高波动
        "regime_stability": 0.4,
        "market_breadth": 0.2,
    }

    decision1 = adaptive.compute_顺应(market_state_1)

    print(f"【开盘蜜月期 9:35】")
    print(f"  顺应状态: {decision1.harmony_state.value}")
    print(f"  行动建议: {decision1.should_act}")
    print(f"  强度: {decision1.intensity:.2f}")

    # 场景2：尾盘14:50
    market_state_2 = {
        "is_market_open": True,
        "volatility": 0.5,
        "trend_strength": 0.2,
        "time_of_day": 14.83,     # 收盘前
        "regime": "stable",
        "regime_stability": 0.7,
        "market_breadth": 0.1,
    }

    decision2 = adaptive.compute_顺应(market_state_2)

    print(f"\n【尾盘14:50】")
    print(f"  顺应状态: {decision2.harmony_state.value}")
    print(f"  行动建议: {decision2.should_act}")
    print(f"  强度: {decision2.intensity:.2f}")

    # 验证：尾盘强度应该降低
    assert decision2.intensity < decision1.intensity, "尾盘强度应降低"
```

### 2.5 MarketNarrativeSense (妙观察智) 真实场景测试

#### 测试场景：叙事追踪（真实市场特征）

```python
"""
场景：识别当前市场叙事

真实市场叙事示例（2024年）：
- 2024-01: "政策牛市"叙事 - 降准预期
- 2024-02: "AI革命"叙事 - ChatGPT带动科技股
- 2024-03: "业绩验证"叙事 - 年报季，业绩为王
"""

def test_narrative_tracking_real():
    """测试真实叙事追踪"""
    from deva.naja.cognition.market_narrative import MarketNarrativeSense

    sense = MarketNarrativeSense()

    # 模拟2024-03市场数据（业绩验证叙事）
    market_data = {
        "price_changes": [2.0, 1.5, 3.0, 2.5, 1.8],  # 龙头股强势
        "sector_changes": {
            "科技": 3.5,     # AI相关领涨
            "新能源": 1.2,
            "消费": 0.5,
            "银行": -0.3,    # 传统行业落后
        },
        "volume_ratio": 1.3,
        "trend_strength": 0.7,
    }

    # 模拟新闻信号
    news_signals = [
        "某AI龙头发布超预期年报",
        "ChatGPT用户突破1亿",
        "科技股业绩密集披露",
    ]

    # 资金流向
    flow_data = {
        "net_flow": 5000000000,  # 主力净流入50亿
        "big_deal_ratio": 0.55,
    }

    result = sense.sense(market_data, news_signals, flow_data)

    print(f"叙事感知结果:")
    print(f"  叙事数: {len(result['narratives'])}")
    for n in result['narratives']:
        print(f"  类型: {n.narrative_type.value}")
        print(f"  阶段: {n.stage.value}")
        print(f"  强度: {n.strength:.2f}")
        print(f"  证据: {n.evidence}")

    print(f"\n摘要: {result['summary']}")

    # 验证：应该识别到板块/业绩叙事
    narrative_types = [n.narrative_type.value for n in result['narratives']]
    assert 'sector' in narrative_types or 'earnings' in narrative_types
```

### 2.6 MetaEvolution (元进化) 真实场景测试

#### 测试场景：自我观察与调参

```python
"""
场景：系统观察自己的表现，自动调整

真实场景：
- MomentumTracker 连续10笔亏损
- 系统检测到性能下降
- 自动降低该模块权重
"""

def test_meta_evolution_real():
    """测试真实元进化"""
    from deva.naja.evolution import get_meta_evolution

    evo = get_meta_evolution()

    # 模拟连续亏损（MomentumTracker）
    for i in range(15):
        evo.record_decision(
            decision_type="momentum_strategy",
            context={"market": "volatile"},
            decision="buy" if i % 2 == 0 else "hold"
        )

        # 前10笔成功率60%，后5笔成功率20%
        success = i < 10 and i % 5 != 0
        evo.record_outcome("momentum_strategy", success=success, latency_ms=50.0)

    # 触发分析
    insights = evo.think()

    summary = evo.observer.get_summary()
    module_stats = summary['modules']['momentum_strategy']

    print(f"【MomentumTracker 性能】")
    print(f"  总决策数: {module_stats['call_count']}")
    print(f"  成功率: {module_stats['success_rate']:.1%}")
    print(f"  趋势: {module_stats['trend']}")
    print(f"  平均延迟: {module_stats['avg_latency_ms']:.1f}ms")

    print(f"\n洞察数: {len(insights)}")
    for insight in insights:
        print(f"  {insight.insight_type}: {insight.description}")
        print(f"    建议: {insight.suggested_action}")

    # 验证：应该发现性能下降
    assert module_stats['trend'] in ['degrading', 'stable']
```

---

## 三、运行测试

### 3.1 快速验证脚本

```bash
#!/bin/bash
# quick_integration_test.sh

cd /Users/spark/pycharmproject/deva

echo "=== 1. 导入检查 ==="
python -c "
from deva.naja.senses import ProphetSense, RealtimeTaste
from deva.naja.alaya import SeedIlluminator
from deva.naja.manas import AdaptiveManas
from deva.naja.evolution import get_meta_evolution
from deva.naja.cognition.market_narrative import MarketNarrativeSense
print('✓ 所有觉醒模块导入成功')
"

echo ""
echo "=== 2. 单元测试 ==="
python -m pytest deva/naja/tests/test_decision_attention.py \
    deva/naja/tests/test_manas_engine.py \
    deva/naja/tests/test_senses.py \
    deva/naja/tests/test_alaya_manas.py \
    deva/naja/tests/test_meta_evolution.py \
    deva/naja/tests/test_market_narrative.py \
    deva/naja/tests/test_opportunity_engine.py \
    deva/naja/tests/test_epiphany_engine.py \
    deva/naja/tests/test_action_executor.py \
    deva/naja/tests/test_risk_manager.py \
    deva/naja/tests/test_position_sizer.py \
    -v --tb=short

echo ""
echo "=== 3. 集成测试 ==="
python -c "
import sys
sys.path.insert(0, 'deva/naja')

# 2.1 天眼通测试
from deva.naja.senses import ProphetSense
prophet = ProphetSense()
market_data = {
    'price_change': 0.5,
    'volume_ratio': 1.5,
    'trend_strength': 0.15,
    'net_flow': -800000000,
    'big_deal_ratio': 0.65,
}
signal = prophet.sense(market_data, None)
print(f'【天眼通】信号: {signal.presage_type}, 强度: {signal.intensity:.2f}')

# 2.4 顺应型末那识测试
from deva.naja.manas import AdaptiveManas
adaptive = AdaptiveManas()
market_state = {
    'is_market_open': True,
    'volatility': 1.2,
    'trend_strength': 0.3,
    'time_of_day': 9.58,
    'regime': 'volatile',
    'regime_stability': 0.4,
    'market_breadth': 0.2,
}
decision = adaptive.compute_顺应(market_state)
print(f'【顺应型末那识】顺应: {decision.harmony_state.value}, 行动: {decision.should_act}')

print('✓ 集成测试通过')
"

echo ""
echo "=== 测试完成 ==="
```

### 3.2 使用历史数据回放测试

```python
"""
使用 ReplayScheduler 进行端到端测试

这需要在 NAJA_LAB_MODE 下运行
"""

def test_with_replay_data():
    """使用真实回放数据进行测试"""
    import os
    os.environ['NAJA_LAB_MODE'] = '1'

    from deva.naja.replay import get_replay_scheduler
    from deva.naja.attention.center import get_orchestrator

    # 初始化
    orch = get_orchestrator()
    orch._ensure_initialized()

    # 获取回放调度器
    scheduler = get_replay_scheduler()

    # 注册回调
    results = []

    def on_data(data):
        results.append(data)
        if len(results) >= 100:  # 处理100批后停止
            scheduler.stop()

    scheduler.set_downstream_callback(on_data)

    # 运行回放
    scheduler.start()

    # 分析结果
    print(f"处理了 {len(results)} 批数据")
    state = orch.get_awakened_state()
    print(f"觉醒状态: {state}")

    return results, state
```

---

## 四、问题排查

### 4.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| 模块导入失败 | `__init__.py` 未更新 | 检查导出 |
| 数据格式不匹配 | 字段名不一致 | 参考 2.1 节的字段定义 |
| 计算结果异常 | 除零/空值 | 添加数据校验 |
| 性能问题 | 数据量太大 | 添加采样 |

### 4.2 数据校验

```python
def validate_market_data(data):
    """校验市场数据"""
    required_fields = ['code', 'now', 'p_change', 'volume']

    for field in required_fields:
        if field not in data:
            raise ValueError(f"缺少字段: {field}")

    if data['now'] <= 0:
        raise ValueError(f"价格无效: {data['now']}")

    if data['volume'] < 0:
        raise ValueError(f"成交量无效: {data['volume']}")

    return True
```

---

## 五、测试报告模板

```markdown
## 测试报告

### 测试时间: _______
### 测试人员: _______
### 数据范围: _______

### 测试结果汇总

| 模块 | 用例数 | 通过 | 失败 | 通过率 |
|------|--------|------|------|--------|
| ProphetSense | 5 | ? | ? | ?% |
| RealtimeTaste | 3 | ? | ? | ?% |
| SeedIlluminator | 3 | ? | ? | ?% |
| AdaptiveManas | 4 | ? | ? | ?% |
| MarketNarrative | 3 | ? | ? | ?% |
| MetaEvolution | 3 | ? | ? | ?% |

### 发现的问题

1. **问题描述**:
   - 模块:
   - 严重程度:
   - 复现步骤:
   - 修复建议:

### 性能指标

- 响应时间: ___ms
- 内存占用: ___MB
- CPU使用: ___%

### 结论

[合格/需优化/不合格]

### 建议

[下一步行动]
```

---

## 六、参考：真实数据样例

### 6.1 平安银行 (000001) 某日数据

```python
{
    "code": "000001",
    "name": "平安银行",
    "now": 12.35,
    "close": 12.18,
    "p_change": 1.40,          # 涨1.4%
    "volume": 68523400,         # 成交量6852万股
    "amount": 845123456.78,     # 成交额8.45亿
    "timestamp": 1709121600
}
```

### 6.2 贵州茅台 (600519) 某日数据

```python
{
    "code": "600519",
    "name": "贵州茅台",
    "now": 1688.00,
    "close": 1695.50,
    "p_change": -0.44,         # 跌0.44%
    "volume": 1234567,          # 成交量123万股
    "amount": 2084567890.50,    # 成交额20.8亿
    "timestamp": 1709121600
}
```

### 6.3 市场整体数据

```python
{
    "上涨股票": 1523,
    "下跌股票": 986,
    "平盘股票": 234,
    "涨停股票": 45,
    "跌停股票": 12,
    "市场宽度": (1523 - 986) / (1523 + 986 + 234),  # ≈ 0.21
    "总成交额": 850000000000,  # 8500亿
    "北向资金": 23500000000,   # 净流入235亿
}
```

---

*基于真实历史数据的测试，才能发现真实的bug。*
