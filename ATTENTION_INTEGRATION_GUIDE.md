# Naja Attention Scheduling System 集成指南

## 快速开始

### 1. 启动 Naja（自动加载注意力系统）

```bash
# 正常启动（自动启用注意力系统）
cd /Users/spark/pycharmproject/deva
python -m deva.naja

# 显式启用注意力系统
python -m deva.naja --attention

# 禁用注意力系统
python -m deva.naja --no-attention

# 查看注意力系统状态报告
python -m deva.naja --attention-report
```

### 2. 环境变量配置

```bash
# 启用/禁用
export NAJA_ATTENTION_ENABLED=true

# 配置参数
export NAJA_ATTENTION_MAX_SYMBOLS=5000
export NAJA_ATTENTION_MAX_SECTORS=100
export NAJA_ATTENTION_HIGH_INTERVAL=1.0
export NAJA_ATTENTION_MEDIUM_INTERVAL=10.0
export NAJA_ATTENTION_LOW_INTERVAL=60.0

# 启动 naja
python -m deva.naja
```

### 3. 配置文件

创建 `~/.naja/attention_config.yaml`：

```yaml
# 主开关
enabled: true

# 系统规模
max_symbols: 5000
max_sectors: 100

# 频率配置（秒）
high_interval: 1.0      # 高频：1秒
medium_interval: 10.0   # 中频：10秒
low_interval: 60.0      # 低频：60秒

# 监控配置
enable_monitoring: true
report_interval: 60.0

# 调试
debug_mode: false
log_level: INFO
```

## 在代码中使用

### 1. 获取注意力系统实例

```python
from deva.naja.attention_integration import get_attention_integration

# 获取集成实例
integration = get_attention_integration()

# 获取注意力系统
attention_system = integration.attention_system
```

### 2. 在策略中使用

```python
from deva.naja.strategy import Strategy
from deva.naja.attention_integration import get_attention_integration

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.integration = get_attention_integration()
    
    def on_data(self, data):
        # 检查是否应该执行（基于注意力）
        symbol = data.get('code')
        if not self.integration.should_fetch_symbol(symbol):
            return  # 跳过这次执行
        
        # 获取个股权重
        weight = self.integration.get_frequency_for_symbol(symbol)
        
        # 根据权重调整策略参数
        if weight.value >= 2:  # HIGH
            # 高频模式：更敏感
            threshold = 0.3
        else:
            # 低频模式：更保守
            threshold = 0.7
        
        # 执行策略逻辑...
```

### 3. 在数据源中使用

```python
from deva.naja.datasource import DataSource
from deva.naja.attention_integration import get_attention_integration

class MyDataSource(DataSource):
    def __init__(self):
        super().__init__()
        self.integration = get_attention_integration()
    
    def fetch_data(self):
        # 获取频率控制指令
        control = self.integration.get_datasource_control()
        
        # 根据频率调整拉取策略
        high_freq_symbols = control['high_freq_symbols']
        medium_freq_symbols = control['medium_freq_symbols']
        low_freq_symbols = control['low_freq_symbols']
        
        # 高频：每次拉取
        for symbol in high_freq_symbols:
            data = self.fetch_symbol(symbol)
            self.emit(data)
        
        # 中频：间隔拉取
        if self.should_fetch_medium():
            for symbol in medium_freq_symbols:
                data = self.fetch_symbol(symbol)
                self.emit(data)
        
        # 低频：偶尔拉取
        if self.should_fetch_low():
            for symbol in low_freq_symbols:
                data = self.fetch_symbol(symbol)
                self.emit(data)
```

### 4. 获取实时报告

```python
from deva.naja.attention_integration import get_attention_integration

integration = get_attention_integration()

# 获取完整报告
report = integration.get_attention_report()
print(f"全局注意力: {report['global_attention']}")
print(f"活跃策略: {report['strategy_summary']['active_count']}")

# 获取高注意力个股
high_attention_symbols = integration.get_high_attention_symbols(threshold=2.0)
print(f"高注意力个股: {high_attention_symbols}")

# 获取活跃板块
active_sectors = integration.get_active_sectors(threshold=0.5)
print(f"活跃板块: {active_sectors}")
```

## 工作原理

### 数据流

```
┌─────────────────────────────────────────────────────────────┐
│ DataSource (你的数据源)                                       │
│  └─> _emit_data()                                           │
│       └─> 自动调用 attention_integration.process_market_data() │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Attention System                                            │
│  ├─> Global Attention (全局注意力计算)                        │
│  ├─> Sector Attention (板块注意力计算)                        │
│  ├─> Weight Pool (个股权重计算)                              │
│  ├─> Frequency Scheduler (频率调度)                          │
│  └─> Dual Engine (异常检测 + 模式识别)                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 输出应用                                                     │
│  ├─> 数据源频率调整                                           │
│  ├─> 策略启停控制                                            │
│  └─> 交易信号增强                                            │
└─────────────────────────────────────────────────────────────┘
```

### 自动发现机制

启动时会自动：
1. 从 `naja_dictionaries` 表加载板块信息
2. 从 `quant_snapshot_5min_window` 表获取个股列表
3. 如果没有板块信息，使用默认板块（科技/金融/医疗/能源/消费）

## 性能指标

- **处理延迟**: < 10ms (每帧)
- **内存占用**: 恒定 (预分配)
- **CPU 占用**: 低 (向量化计算)

## 故障排除

### 1. 注意力系统没有启动

```bash
# 检查日志
python -m deva.naja --log-level DEBUG

# 检查是否被禁用
export NAJA_ATTENTION_ENABLED=true
```

### 2. 板块信息不正确

```python
# 手动配置板块
from deva.naja.attention_integration import get_attention_integration
from naja_attention_system import SectorConfig

integration = get_attention_integration()

# 添加自定义板块
sector = SectorConfig(
    sector_id="my_sector",
    name="我的板块",
    symbols={"000001", "000002"}
)
integration.attention_system.sector_attention.register_sector(sector)
```

### 3. 查看调试信息

```python
# 在代码中添加
import logging
logging.getLogger('deva.naja.attention').setLevel(logging.DEBUG)
```

## 进阶配置

### 自定义频率阈值

```python
from naja_attention_system import FrequencyConfig

# 创建自定义频率配置
freq_config = FrequencyConfig(
    low_threshold=1.0,      # 低于1.0为低频
    high_threshold=3.0,     # 高于3.0为高频
    low_interval=120.0,     # 低频120秒
    medium_interval=30.0,   # 中频30秒
    high_interval=5.0       # 高频5秒
)

# 应用到调度器
integration.attention_system.frequency_scheduler.config = freq_config
```

### 自定义策略分配

```python
from naja_attention_system import StrategyConfig, StrategyScope, StrategyType, StrategyParams

# 创建自定义策略
strategy_config = StrategyConfig(
    strategy_id="my_strategy",
    name="我的策略",
    scope=StrategyScope.SYMBOL,
    strategy_type=StrategyType.TREND,
    params=StrategyParams(threshold=0.5),
    min_attention=0.3,  # 注意力低于0.3不执行
    max_attention=1.0
)

# 注册到策略分配器
integration.attention_system.strategy_allocator.registry.register(strategy_config)
```
