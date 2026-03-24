# Naja 认知系统指南

> 基于最新代码结构（2026-03-24）

## 概述

Naja 认知系统是平台级的智能中枢，整合了注意力机制、叙事追踪、跨信号分析和洞察生成能力。之前的"记忆系统"功能已整合到认知系统中。

## 核心功能

| 功能 | 说明 |
|------|------|
| CognitionEngine | 认知引擎，平台级认知输入输出入口 |
| NarrativeTracker | 叙事追踪器，管理市场叙事生命周期 |
| SemanticColdStart | 语义冷启动，处理新概念的快速学习 |
| InsightEngine | 洞察引擎，管理认知产物 |
| CrossSignalAnalyzer | 跨信号分析器，合并新闻和注意力信号 |

## 核心文件

| 文件 | 功能 |
|------|------|
| `cognition/core.py` | NewsMindStrategy、AttentionScorer |
| `cognition/engine.py` | CognitionEngine 认知引擎 |
| `cognition/narrative_tracker.py` | NarrativeTracker 叙事追踪 |
| `cognition/semantic_cold_start.py` | SemanticColdStart 语义冷启动 |
| `cognition/insight/engine.py` | InsightEngine 洞察引擎 |
| `cognition/cross_signal_analyzer.py` | CrossSignalAnalyzer 跨信号分析 |
| `cognition/ui.py` | 认知系统 UI |

## 访问方式

访问 `/cognition` 或 `/memory`（兼容旧入口）查看认知系统。

## 数据流

```
策略执行结果 → ResultStore → CognitionEngine
                                    ↓
                         ┌─────────────────────┐
                         │ NarrativeTracker    │
                         │ 叙事追踪            │
                         ├─────────────────────┤
                         │ SemanticColdStart   │
                         │ 语义冷启动          │
                         ├─────────────────────┤
                         │ CrossSignalAnalyzer │
                         │ 跨信号分析          │
                         ├─────────────────────┤
                         │ InsightEngine       │
                         │ 洞察生成            │
                         └─────────────────────┘
```

## 与注意力系统的关系

认知系统与注意力系统深度集成：

- **注意力 → 认知**：注意力系统产生的信号会输入到认知引擎
- **认知 → 注意力**：认知引擎的洞察会影响注意力分配决策
- **叙事 → 叙事主题**：市场叙事状态会反馈到注意力策略

## 相关文档

- [attention_guide.md](attention_guide.md) - 注意力调度系统
- [radar_guide.md](radar_guide.md) - 雷达系统
- [NAJA_OVERVIEW.md](../NAJA_OVERVIEW.md) - Naja 架构总览