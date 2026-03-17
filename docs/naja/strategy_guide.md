# Naja 策略系统指南

> 基于最新代码结构（2026-03-17）

## 概述

Naja 策略系统是平台的核心计算引擎，支持 River 策略、多数据源策略、信号处理等功能。

## 策略类型

### 1. River 策略

基于 River 框架的流计算策略，支持 Tick 级别数据处理。

```python
from deva.naja.strategy.river_wrapper import RiverStrategy

class MyStrategy(RiverStrategy):
    name = "my_strategy"
    
    def process(self, data):
        # 处理逻辑
        return result
```

### 2. 多数据源策略

支持绑定多个数据源，统一处理。

```python
from deva.naja.strategy.multi_datasource import MultiDatasourceStrategy

class MultiDS(MultiDatasourceStrategy):
    name = "multi_ds"
    sources = ["source1", "source2"]
```

### 3. Bandit 策略

基于多臂老虎机的自适应交易策略。

```python
from deva.naja.bandit import BanditStrategy
```

## 核心文件

| 文件 | 功能 |
|------|------|
| `runtime.py` | 策略运行时，管理策略生命周期 |
| `registry.py` | 策略注册表，存储策略元数据 |
| `river_wrapper.py` | River 策略包装器 |
| `river_tick_strategies.py` | Tick 级别策略实现 |
| `multi_datasource.py` | 多数据源策略 |
| `signal_processor.py` | 信号处理器 |
| `result_store.py` | 结果存储 |

## 策略创建

### 使用 Skill 创建

```bash
# 使用 strategy-creator skill 创建策略
# 参考 .trae/skills/strategy-creator/
```

### 手动创建

1. 编写策略代码
2. 注册策略
3. 配置数据源绑定
4. 启动策略

## 策略管理页面

访问 `/strategyadmin` 管理策略。

## 相关文档

- [datasource_guide.md](datasource_guide.md) - 数据源配置
- [bandit_guide.md](bandit_guide.md) - Bandit 交易
- [river-market-insight skill](../.trae/skills/river-market-insight/SKILL.md) - 市场洞察
