# 注意力策略系统自动运行配置

## 概述

现在 `realtime_tick_5s` 数据源一有数据产生，注意力系统和策略会自动执行。

## 数据流

```
realtime_tick_5s 数据源 emit 数据
    ↓
数据源 _emit_data() 方法
    ↓
调度中心 process_datasource_data()
    ↓
更新注意力系统 (计算全局注意力、板块权重、个股权重)
    ↓
分发数据到各策略
    ├─→ GlobalMarketSentinel (全局市场监控)
    ├─→ SectorRotationHunter (板块轮动捕捉)
    ├─→ MomentumSurgeTracker (动量突破追踪)
    ├─→ AnomalyPatternSniper (异常模式狙击)
    └─→ SmartMoneyFlowDetector (聪明资金流向)
    ↓
策略生成信号 (如果有满足条件的)
```

## 自动启动配置

### 1. Naja 启动时自动初始化

修改了 `deva/naja/supervisor.py`，在 `start_monitoring()` 中添加：

```python
# 启动注意力策略系统
try:
    from naja_attention_strategies import setup_attention_strategies
    strategy_manager = setup_attention_strategies()
    self._components['attention_strategy_manager'] = strategy_manager
    log.info("注意力策略系统已启动")
except Exception as se:
    log.error(f"注意力策略系统启动失败: {se}")
```

### 2. 数据源自动触发

修改了 `deva/naja/datasource/__init__.py`，在 `_emit_data()` 中添加：

```python
# 发送数据到注意力调度中心（如果是 DataFrame 格式）
try:
    import pandas as pd
    if isinstance(data, pd.DataFrame):
        from ..attention_orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        orchestrator.process_datasource_data(self.name, data)
except Exception as e:
    # 注意力系统处理失败不影响正常数据流
    pass
```

### 3. 调度中心分发到策略

修改了 `deva/naja/attention_orchestrator.py`，在 `_dispatch_to_strategies()` 中添加：

```python
# 分发到新版注意力策略系统
try:
    from .attention_integration import process_data_with_strategies
    context = {
        'global_attention': self._cached_global_attention,
        'high_attention_symbols': self._cached_high_attention_symbols,
        'active_sectors': self._cached_active_sectors,
        'datasource_id': datasource_id,
        'sector_weights': self._get_sector_weights(),
        'symbol_weights': self._get_symbol_weights()
    }
    signals = process_data_with_strategies(data, context)
    if signals:
        log.debug(f"注意力策略生成 {len(signals)} 个信号")
except Exception as e:
    log.error(f"分发数据到注意力策略系统失败: {e}")
```

## 策略执行逻辑

### GlobalMarketSentinel (全局市场监控)
- **触发条件**: 始终运行
- **作用**: 监控整体市场风险状态
- **输出**: 风险等级 (Normal/Caution/Warning/Danger/Panic)

### SectorRotationHunter (板块轮动捕捉)
- **触发条件**: 全局注意力 > 0.3
- **作用**: 捕捉资金在板块间的轮动
- **输出**: 板块资金流入/流出信号

### MomentumSurgeTracker (动量突破追踪)
- **触发条件**: 全局注意力 > 0.4，个股权重 > 2.0
- **作用**: 追踪高注意力股票的动量突破
- **输出**: 买入/卖出信号，带止盈止损

### AnomalyPatternSniper (异常模式狙击)
- **触发条件**: River始终运行，PyTorch在注意力>0.6时激活
- **作用**: 检测统计异常 + 深度学习模式识别
- **输出**: 突破确认/假突破/洗盘结束信号

### SmartMoneyFlowDetector (聪明资金流向)
- **触发条件**: 全局注意力 > 0.35
- **作用**: 检测机构资金的建仓/出货行为
- **输出**: 聪明钱建仓/出货信号

## 使用方法

### 1. 启动 naja

```bash
python -m deva.naja
```

或者带注意力系统报告：

```bash
python -m deva.naja --attention-report
```

### 2. 启动 realtime_tick_5s 数据源

在 naja Web 界面启动 `realtime_tick_5s` 数据源，或者：

```python
from deva.naja.datasource import get_datasource_manager

mgr = get_datasource_manager()
mgr.start_datasource('realtime_tick_5s')
```

### 3. 查看策略状态

```python
from naja_attention_strategies import get_strategy_manager

manager = get_strategy_manager()
stats = manager.get_all_stats()
print(f"总信号数: {stats['total_signals_generated']}")

# 获取最近信号
signals = manager.get_recent_signals(n=20)
for signal in signals:
    print(f"{signal.symbol}: {signal.signal_type} - {signal.reason}")
```

### 4. 管理策略

```python
from naja_attention_strategies import get_strategy_manager

manager = get_strategy_manager()

# 禁用某个策略
manager.disable_strategy('momentum_surge_tracker')

# 启用策略
manager.enable_strategy('momentum_surge_tracker')

# 获取策略统计
stats = manager.get_all_stats()
```

## 配置文件

配置文件位置: `~/.naja/attention_strategies.json`

可以调整各策略的参数：
- `min_global_attention`: 最低全局注意力阈值
- `min_symbol_weight`: 最低个股权重
- `cooldown_period`: 信号冷却期
- `custom_params`: 策略特有参数

## 性能优化

- 只处理高注意力股票（从5000只减少到50-200只）
- 策略根据注意力水平动态调整执行频率
- 双引擎架构：River轻量级始终运行，PyTorch重量级按需激活
- 预计节省 60%+ CPU 资源

## 测试

运行测试脚本验证流程：

```bash
python test_attention_flow.py
```

## 注意事项

1. 确保 `realtime_tick_5s` 数据源正在运行
2. 策略只在市场活跃时（高注意力）执行
3. 信号生成需要满足策略的触发条件
4. 可以通过 `manager.get_all_stats()` 监控策略运行状态
