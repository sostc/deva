# Naja Bandit 交易指南

> 基于最新代码结构（2026-03-17）

## 概述

Bandit 系统是基于多臂老虎机的自适应交易系统，支持虚拟组合、市场观察等功能。

## 核心功能

| 功能 | 说明 |
|------|------|
| Adaptive Cycle | 自适应周期 |
| Virtual Portfolio | 虚拟组合 |
| Market Observer | 市场观察 |
| Signal Listener | 信号监听 |

## 核心文件

| 文件 | 功能 |
|------|------|
| `runner.py` | Bandit 运行器 |
| `optimizer.py` | 优化器 |
| `virtual_portfolio.py` | 虚拟组合 |
| `market_observer.py` | 市场观察 |
| `xiaohe_integration` | Xiaohe 集成 |

## 访问方式

访问 `/banditadmin` 或通过主菜单进入。

## 使用方式

```python
from deva.naja.bandit import BanditRunner

runner = BanditRunner()
runner.start()
```

## 相关文档

- [strategy_guide.md](strategy_guide.md) - 策略系统
- [realtime_quant_strategy_workflow_guide.md](../guides/realtime_quant_strategy_workflow_guide.md)
