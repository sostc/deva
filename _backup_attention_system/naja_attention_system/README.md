# Naja Attention Scheduling System

自适应注意力调度机制 - 让系统只在值得计算的地方计算

## 核心思想

> 平时如常，异常才深看。  
> 轻者以水观之，重者以火照之。

**Attention = "势"** (资源流向)  
**Strategy = "术"** (如何利用资源)

## 架构概览

```
snapshot → Global Attention → Sector Attention → Weight Pool → 
    Frequency Scheduler → Strategy Allocation → Dual Engine → 
    DataSource Control
```

## 模块说明

### 1. Global Attention (全局注意力)

**功能**: 从全市场 snapshot 中提取市场状态

**输出**: `global_attention ∈ [0, 1]`

**计算维度**:
- 市场波动率 (30%)
- 成交量异常 (30%)
- 涨跌分布 (20%)
- 趋势强度 (20%)

**用途**:
- 控制整体策略激进程度
- 调节数据源频率基线
- 作为所有局部注意力的上位约束

### 2. Sector Attention (板块注意力)

**功能**: 每个板块独立计算注意力

**特性**:
- 多板块并行计算
- 半衰期衰减 (自动降低关注)
- 增量更新，避免全量 groupby

**计算维度**:
- 领涨股比例 (40%)
- 成交量集中度 (30%)
- 内部相关性 (30%)

### 3. Weight Pool (多对多权重池)

**功能**: 解决个股 ↔ 多板块的映射关系

**特性**:
- 一个 symbol 可属于多个 sector
- 最终权重由多个 sector 决定
- 支持快速查找 O(1)

**权重公式**:
```
weight = base_weight × (1 + sector_influence) × (1 + local_activity)
```

### 4. Frequency Scheduler (频率调度器)

**功能**: 将连续权重转换为离散数据频率

**频率档位**:
- **LOW**: 60秒间隔 (低频)
- **MEDIUM**: 10秒间隔 (中频)
- **HIGH**: 1秒间隔 (高频)

**特性**:
- 滞后机制 (避免频繁切换)
- 冷静期 (cooldown)
- 最小变更原则

### 5. Strategy Allocation (策略分配与调节)

**三层作用域**:
1. **Global Strategy**: 判断整体风险状态
2. **Sector Strategy**: 捕捉板块轮动
3. **Symbol Strategy**: 精细交易执行

**参数调节** (基于 attention):
- `attention ↑` → `threshold ↓` (更容易触发)
- `attention ↑` → `position_size ↑`
- `attention ↓` → `holding_time ↓`
- `attention ↑` → `risk_limit ↑` (更宽松)

### 6. Dual Engine (双引擎)

**River Engine** (基础层/常态层):
- 全市场持续运行
- 流式均值/方差/回归
- 残差检测
- O(1)/tick

**PyTorch Engine** (专家层/异常层):
- 只处理被 River 标记的异常标的
- 高阶模式识别
- 异步执行，批量推理

**触发逻辑**:
```
if anomaly_score > threshold and trigger_score > 0.5:
    进入 PyTorch 分析
```

## 性能目标

| 指标 | 目标 |
|------|------|
| 单次处理延迟 | < 10ms |
| 复杂度 | O(n), n=股票数量 |
| 内存占用 | 恒定 (预分配) |
| Python 循环 | 最小化 (向量化) |

## 快速开始

### 1. 安装依赖

```bash
pip install numpy river
# PyTorch 可选 (用于专家层)
pip install torch
```

### 2. 基础用法

```python
from naja_attention_system import (
    AttentionSystem,
    AttentionSystemConfig,
    SectorConfig
)
import numpy as np

# 创建系统
config = AttentionSystemConfig(
    max_symbols=5000,
    max_sectors=100
)
system = AttentionSystem(config)

# 初始化板块和个股
sectors = [
    SectorConfig(sector_id="tech", name="科技", symbols={"AAPL", "MSFT"}),
    SectorConfig(sector_id="finance", name="金融", symbols={"JPM", "BAC"}),
]

symbol_sector_map = {
    "AAPL": ["tech"],
    "MSFT": ["tech"],
    "JPM": ["finance"],
    "BAC": ["finance"],
}

system.initialize(sectors, symbol_sector_map)

# 处理市场快照
result = system.process_snapshot(
    symbols=np.array(["AAPL", "MSFT", "JPM", "BAC"]),
    returns=np.array([1.5, -0.5, 2.0, 0.3]),
    volumes=np.array([1000000, 800000, 1200000, 600000]),
    prices=np.array([150.0, 300.0, 140.0, 35.0]),
    sector_ids=np.array([0, 0, 1, 1]),
    timestamp=time.time()
)

print(f"Global Attention: {result['global_attention']}")
print(f"Active Sectors: {result['sector_attention']}")
print(f"Symbol Weights: {result['symbol_weights']}")
```

### 3. 运行演示

```bash
cd /Users/spark/pycharmproject/deva
python -m naja_attention_system.demo
```

## 与 Naja 集成

### 接入 DataSource

```python
from naja_attention_system import AttentionSystemIntegration

# 创建集成层
integration = AttentionSystemIntegration(attention_system)

# 注册数据源回调
def on_attention_update(result):
    # 根据注意力调整数据源订阅
    control = attention_system.get_datasource_control()
    # 更新 WebSocket 订阅...

integration.register_datasource_callback(on_attention_update)

# 在数据源回调中调用
integration.on_datasource_data({
    'symbols': [...],
    'returns': [...],
    'volumes': [...],
    'prices': [...],
    'timestamp': time.time()
})
```

### 接入 Strategy

```python
# 注册策略
from naja_attention_system import (
    StrategyConfig, StrategyScope, StrategyType, StrategyParams
)

config = StrategyConfig(
    strategy_id="my_strategy",
    name="我的策略",
    scope=StrategyScope.SYMBOL,
    strategy_type=StrategyType.TREND,
    params=StrategyParams(threshold=0.5),
    min_attention=0.3  # 注意力低于0.3时不激活
)

# 策略执行前检查
if integration.should_process_strategy("my_strategy"):
    # 执行策略
    pass
```

## 配置说明

### AttentionSystemConfig

```python
AttentionSystemConfig(
    # 全局注意力
    global_history_window=20,      # 历史窗口大小
    
    # 板块注意力
    max_sectors=100,               # 最大板块数
    sector_decay_half_life=300.0,  # 半衰期(秒)
    
    # 权重池
    max_symbols=5000,              # 最大个股数
    
    # 频率调度
    low_interval=60.0,             # 低频间隔(秒)
    medium_interval=10.0,          # 中频间隔(秒)
    high_interval=1.0,             # 高频间隔(秒)
    
    # 双引擎
    river_history_window=20,       # River历史窗口
    pytorch_max_concurrent=10      # PyTorch最大并发
)
```

## 扩展开发

### 自定义策略

```python
from naja_attention_system import Strategy, StrategyConfig

class MyStrategy(Strategy):
    async def on_activate(self):
        # 策略激活时的初始化
        pass
    
    async def on_deactivate(self):
        # 策略停用时的清理
        pass
    
    async def execute(self, context: Dict) -> Dict:
        # 策略执行逻辑
        return {'signal': 'buy', 'confidence': 0.8}

# 注册策略工厂
registry.register_factory("my_strategy_type", MyStrategy)
```

### 自定义 PyTorch 模型

```python
# 在 PyTorchEngine 中替换模型
class MyPatternModel(nn.Module):
    def __init__(self):
        super().__init__()
        # 定义模型结构
        
    def forward(self, x):
        # 前向传播
        return output

# 替换默认模型
engine.pytorch._model = MyPatternModel()
```

## 性能优化建议

1. **预分配**: 所有数组预先分配，避免运行时的内存分配
2. **向量化**: 使用 numpy 向量化操作，避免 Python 层循环
3. **增量计算**: 基于变化而非全量重计算
4. **缓存**: 合理使用缓存避免重复计算
5. **异步**: PyTorch 推理异步执行，不阻塞主流程

## 监控指标

```python
# 获取系统状态
status = attention_system.get_system_status()

# 关键指标
{
    'processing_count': 1000,        # 处理快照数
    'avg_latency_ms': 5.2,           # 平均延迟
    'global_attention': 0.65,        # 当前全局注意力
    'frequency_summary': {           # 频率分布
        'high_frequency': 50,
        'medium_frequency': 200,
        'low_freqency': 4750
    },
    'strategy_summary': {            # 策略状态
        'active_count': 15,
        'by_scope': {
            'global': 2,
            'sector': 5,
            'symbol': 8
        }
    }
}
```

## 许可证

MIT License