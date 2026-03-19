# Naja 注意力策略系统

基于注意力调度系统的智能交易策略集，只在市场活跃时执行，只关注高注意力股票。

## 核心特性

1. **注意力感知**: 策略根据全局注意力水平动态调整执行频率
2. **分层处理**: 全局 → 板块 → 个股，三层注意力架构
3. **双引擎架构**: River（轻量级始终运行）+ PyTorch（重量级按需激活）
4. **性能优化**: 只处理高注意力股票，节省 60%+ 计算资源

## 策略列表

### 1. GlobalMarketSentinel (全局市场监控)
- **作用**: 监控整体市场风险状态
- **触发条件**: 始终运行
- **输出**: 市场风险等级 (Normal/Caution/Warning/Danger/Panic)

### 2. SectorRotationHunter (板块轮动捕捉)
- **作用**: 捕捉资金在板块间的轮动
- **触发条件**: 全局注意力 > 0.3
- **输出**: 板块资金流入/流出信号

### 3. MomentumSurgeTracker (动量突破追踪)
- **作用**: 追踪高注意力股票的动量突破
- **触发条件**: 全局注意力 > 0.4，个股权重 > 2.0
- **输出**: 买入/卖出信号，带止盈止损

### 4. AnomalyPatternSniper (异常模式狙击)
- **作用**: 检测统计异常 + 深度学习模式识别
- **触发条件**: River始终运行，PyTorch在注意力>0.6时激活
- **输出**: 突破确认/假突破/洗盘结束信号

### 5. SmartMoneyFlowDetector (聪明资金流向)
- **作用**: 检测机构资金的建仓/出货行为
- **触发条件**: 全局注意力 > 0.35
- **输出**: 聪明钱建仓/出货信号

## 快速开始

### 1. 启动策略系统

```python
from naja_attention_strategies import setup_attention_strategies

# 一键启动所有策略
manager = setup_attention_strategies()
```

### 2. 处理数据

```python
# 在数据源回调中调用
async def on_market_data(data):
    signals = manager.process_data(data)
    for signal in signals:
        print(f"信号: {signal.symbol} - {signal.signal_type}")
```

### 3. 获取统计信息

```python
# 获取所有策略统计
stats = manager.get_all_stats()
print(f"生成信号数: {stats['total_signals_generated']}")

# 获取最近信号
recent_signals = manager.get_recent_signals(n=20)

# 获取特定股票信号
symbol_signals = manager.get_signals_by_symbol('000001.SZ')
```

### 4. 管理策略

```python
# 禁用某个策略
manager.disable_strategy('momentum_surge_tracker')

# 启用策略
manager.enable_strategy('momentum_surge_tracker')

# 重置所有策略
manager.reset_all_strategies()
```

## 配置系统

配置文件位置: `~/.naja/attention_strategies.json`

```json
{
  "version": "1.0.0",
  "auto_start": true,
  "strategies": {
    "momentum_surge_tracker": {
      "enabled": true,
      "priority": 7,
      "min_global_attention": 0.4,
      "min_symbol_weight": 2.0,
      "custom_params": {
        "price_threshold": 0.03,
        "volume_threshold": 2.0
      }
    }
  }
}
```

### 程序化配置

```python
from naja_attention_strategies import get_config_manager, StrategySettings

config = get_config_manager()

# 更新策略配置
settings = StrategySettings(
    enabled=True,
    min_global_attention=0.5,
    custom_params={'price_threshold': 0.05}
)
config.update_strategy_settings('momentum_surge_tracker', settings)
```

## 自定义策略

继承 `AttentionStrategyBase` 创建自己的策略:

```python
from naja_attention_strategies import AttentionStrategyBase, Signal

class MyStrategy(AttentionStrategyBase):
    def __init__(self):
        super().__init__(
            strategy_id="my_strategy",
            name="My Strategy",
            scope='symbol',
            min_global_attention=0.3
        )
    
    def _on_signal(self, signal: Signal):
        print(f"信号: {signal.symbol} - {signal.signal_type}")
    
    def analyze(self, data, context):
        signals = []
        # 你的分析逻辑
        return signals

# 注册到管理器
from naja_attention_strategies import get_strategy_manager

manager = get_strategy_manager()
my_strategy = MyStrategy()
manager.register_strategy(my_strategy)
```

## 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│                    注意力策略系统                            │
├─────────────────────────────────────────────────────────────┤
│  GlobalMarketSentinel                                       │
│  ├── 始终运行，监控整体市场风险                              │
│  └── 输出: 风险等级 (Normal/Caution/Warning/Danger/Panic)   │
├─────────────────────────────────────────────────────────────┤
│  SectorRotationHunter                                       │
│  ├── 全局注意力 > 0.3 时执行                                 │
│  └── 监控板块权重变化，捕捉轮动                              │
├─────────────────────────────────────────────────────────────┤
│  MomentumSurgeTracker                                       │
│  ├── 全局注意力 > 0.4 时执行                                 │
│  ├── 只处理权重 > 2.0 的股票                                 │
│  └── 价格动量 + 成交量动量双重确认                           │
├─────────────────────────────────────────────────────────────┤
│  AnomalyPatternSniper                                       │
│  ├── River Engine: 始终运行，统计异常检测                    │
│  ├── PyTorch Engine: 注意力 > 0.6 时激活                     │
│  └── 识别: 突破确认 / 假突破 / 洗盘                          │
├─────────────────────────────────────────────────────────────┤
│  SmartMoneyFlowDetector                                     │
│  ├── 全局注意力 > 0.35 时执行                                │
│  └── 分析大单/小单流向差异                                   │
└─────────────────────────────────────────────────────────────┘
```

## 性能对比

| 指标 | 传统策略 | 注意力策略 | 节省 |
|------|---------|-----------|------|
| 处理股票数 | 5000 | 50-200 | 96%+ |
| CPU占用 | 100% | 30-40% | 60%+ |
| 信号质量 | 低 | 高 | - |
| 响应延迟 | 高 | 低 | - |

## 依赖

- Python 3.8+
- pandas
- numpy
- naja_attention_system (注意力系统)

## 版本历史

- v1.0.0: 初始版本，包含5个策略
