# Naja 雷达系统指南

> 基于最新代码结构（2026-03-30）

## 概述

Naja 雷达系统用于检测市场模式、异常和概念漂移，同时包含全球市场扫描和流动性预测功能。

## 核心功能

| 功能 | 说明 |
|------|------|
| Pattern Detection | 模式检测 |
| Anomaly Detection | 异常检测 |
| Drift Detection | 概念漂移检测 |
| GlobalMarketScanner | 全球市场信号采集 + 流动性预测 |
| Liquidity Prediction | 预测 → 验证 → 解除 完整闭环 |

## 核心文件

| 文件 | 功能 |
|------|------|
| `engine.py` | 雷达引擎 |
| `ui.py` | 雷达 UI |
| `global_market_scanner.py` | 全球市场扫描 + 流动性预测 |

## 访问方式

访问 `/radaradmin` 查看雷达事件和流动性预测状态。

## 数据流

```
策略执行结果 → ResultStore → RadarEngine
                                ↓
                         ┌───────────────┐
                         │ Pattern       │
                         │ Anomaly       │
                         │ Drift         │
                         └───────────────┘
```

## 流动性预测体系

GlobalMarketScanner 提供全球市场联动预测能力：

```python
from deva.naja.radar.global_market_scanner import (
    get_global_market_scanner,
    LiquiditySignalType,
)

scanner = get_global_market_scanner()

# 预测流动性
prediction = scanner.predict_liquidity(
    LiquiditySignalType.US,
    {'change_pct': -3.0, 'volume_ratio': 1.2}
)

# 检测共振
resonance = scanner.detect_resonance(market_signal=-0.8, narrative_signal=-0.7)

# 验证预测
scanner.verify_liquidity(LiquiditySignalType.CHINA_A, {'change_pct': -2.0})

# 获取调整
adjustment = scanner.get_liquidity_adjustment(LiquiditySignalType.CHINA_A)
```

详见：[cross_market_liquidity_prediction.md](cross_market_liquidity_prediction.md)

## 使用 river-market-insight Skill

市场洞察 skill 提供概念漂移检测功能：

```bash
# 参考 .trae/skills/river-market-insight/
```

## 相关文档

- [cognition_guide.md](cognition_guide.md) - 认知系统
- [river-market-insight skill](../.trae/skills/river-market-insight/SKILL.md)
