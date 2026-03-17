# Naja 雷达系统指南

> 基于最新代码结构（2026-03-17）

## 概述

Naja 雷达系统用于检测市场模式、异常和概念漂移。

## 核心功能

| 功能 | 说明 |
|------|------|
| Pattern Detection | 模式检测 |
| Anomaly Detection | 异常检测 |
| Drift Detection | 概念漂移检测 |

## 核心文件

| 文件 | 功能 |
|------|------|
| `engine.py` | 雷达引擎 |
| `ui.py` | 雷达 UI |

## 访问方式

访问 `/radaradmin` 查看雷达事件。

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

## 使用 river-market-insight Skill

市场洞察 skill 提供概念漂移检测功能：

```bash
# 参考 .trae/skills/river-market-insight/
```

## 相关文档

- [memory_guide.md](memory_guide.md) - 记忆系统
- [river-market-insight skill](../.trae/skills/river-market-insight/SKILL.md)
