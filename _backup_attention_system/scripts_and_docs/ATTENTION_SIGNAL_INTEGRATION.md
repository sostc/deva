# 注意力策略信号对接说明

## 概述

注意力策略产生的信号现在会自动对接到 Bandit 交易系统和信号流系统，用户可以在 Web UI 中查看这些信号。

## 信号流转

```
注意力策略生成信号
    ↓
emit_signal() 方法
    ↓
    ├─→ _on_signal() - 控制台输出
    ├─→ _forward_signal_to_bandit() - 发送到 Bandit
    └─→ _forward_signal_to_stream() - 发送到信号流
```

## 对接机制

### 1. 对接到 Bandit 系统

**代码位置**: `naja_attention_strategies/base.py::_forward_signal_to_bandit()`

**逻辑**:
- 只转发 `buy` 和 `sell` 信号（hold/watch 不转发）
- 创建 `StrategyResult` 对象
- 通过 `SignalStream.update()` 发送到信号流
- Bandit 的 `SignalListener` 会监听这些信号并创建虚拟持仓

**信号格式**:
```python
StrategyResult(
    id=f"{strategy_id}_{symbol}_{timestamp}",
    strategy_id="momentum_surge_tracker",
    strategy_name="Momentum Surge Tracker",
    ts=signal.timestamp,
    success=True,
    input_preview="000001.SZ: buy",
    output_preview="置信度: 0.85, 得分: 0.92",
    output_full={
        'symbol': '000001.SZ',
        'signal_type': 'buy',
        'confidence': 0.85,
        'score': 0.92,
        'reason': '动量突破...',
        'metadata': {...}
    },
    metadata={
        'source': 'attention_strategy',
        'scope': 'symbol',
        'signal_type': 'buy',
        'confidence': 0.85
    }
)
```

### 2. 对接到信号流系统

**代码位置**: `naja_attention_strategies/base.py::_forward_signal_to_stream()`

**逻辑**:
- 所有类型的信号都会转发
- 策略名称前缀加上 `[注意力]` 以便区分
- 通过 `SignalStream.update()` 发送到信号流
- 可以在 Web UI 的 `/signaladmin` 页面查看

**信号格式**:
```python
StrategyResult(
    id=f"attn_{strategy_id}_{timestamp}",
    strategy_id="momentum_surge_tracker",
    strategy_name="[注意力] Momentum Surge Tracker",
    ts=signal.timestamp,
    success=True,
    input_preview="股票: 000001.SZ",
    output_preview="BUY | 置信度: 0.85",
    output_full={
        'strategy': 'Momentum Surge Tracker',
        'symbol': '000001.SZ',
        'type': 'buy',
        'confidence': 0.85,
        'score': 0.92,
        'reason': '动量突破...',
        'timestamp': 1234567890.0,
        'metadata': {...}
    },
    metadata={
        'attention_signal': True,
        'scope': 'symbol',
        'symbol': '000001.SZ',
        'signal_type': 'buy'
    }
)
```

## 查看信号

### 1. Bandit 虚拟持仓

访问: `http://localhost:8080/banditadmin`

- 注意力策略的买入信号会触发虚拟持仓创建
- 可以看到持仓、收益、交易历史等信息

### 2. 信号流页面

访问: `http://localhost:8080/signaladmin`

- 所有注意力策略的信号都会显示在这里
- 信号带有 `[注意力]` 前缀，便于识别
- 显示置信度、得分、原因等详细信息

### 3. 注意力系统页面

访问: `http://localhost:8080/attentionadmin`

- 在"最近信号"区域查看最近生成的信号
- 显示信号类型、股票代码、置信度

## 信号类型映射

| 注意力信号 | Bandit 接收 | 信号流显示 | 说明 |
|-----------|------------|-----------|------|
| buy | ✅ 是 | ✅ BUY | 买入信号，触发虚拟持仓 |
| sell | ✅ 是 | ✅ SELL | 卖出信号，触发平仓 |
| hold | ❌ 否 | ✅ HOLD | 持有信号，仅显示 |
| watch | ❌ 否 | ✅ WATCH | 观察信号，仅显示 |

## 错误处理

信号转发采用"失败不影响"策略：

```python
try:
    # 转发信号...
except Exception as e:
    # 转发失败不影响策略执行
    pass
```

这意味着：
- 即使 Bandit 系统未启动，策略仍能正常工作
- 即使信号流系统故障，策略仍能生成信号
- 信号转发是可选的增强功能，不是必需依赖

## 配置

### 调整信号转发行为

可以在策略初始化时配置：

```python
class MyStrategy(AttentionStrategyBase):
    def __init__(self):
        super().__init__(
            strategy_id="my_strategy",
            name="My Strategy",
            # ... 其他配置
        )
        # 可以在这里添加自定义转发逻辑
```

### 过滤信号

如果需要过滤某些信号，可以重写 `emit_signal` 方法：

```python
def emit_signal(self, signal: Signal):
    # 只转发高置信度信号
    if signal.confidence < 0.7:
        return
    
    super().emit_signal(signal)
```

## 调试

### 查看信号转发日志

信号转发失败时不会抛出异常，但可以通过以下方式调试：

```python
# 在 _forward_signal_to_bandit 中添加日志
import logging
log = logging.getLogger(__name__)

try:
    # 转发逻辑...
    log.info(f"信号已转发到 Bandit: {signal.symbol}")
except Exception as e:
    log.error(f"信号转发失败: {e}")
```

### 验证信号是否到达

1. **检查信号流**:
   ```python
   from deva.naja.signal.stream import get_signal_stream
   stream = get_signal_stream()
   recent = stream.get_recent(limit=10)
   for r in recent:
       print(f"{r.strategy_name}: {r.output_preview}")
   ```

2. **检查 Bandit 监听**:
   ```python
   from deva.naja.bandit import get_signal_listener
   listener = get_signal_listener()
   print(f"监听器状态: {listener._running}")
   ```

## 总结

✅ **自动对接**: 策略生成信号后自动转发到 Bandit 和信号流
✅ **双向兼容**: 不影响原有策略体系，独立运行
✅ **错误隔离**: 转发失败不影响策略执行
✅ **友好展示**: 用户可以在 Web UI 中查看所有信号
