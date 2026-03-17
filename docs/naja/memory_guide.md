# Naja 记忆系统指南

> 基于最新代码结构（2026-03-17）

## 概述

Naja 记忆系统是平台级的记忆能力，包括短期记忆、长期记忆和主题沉淀。

## 核心概念

| 概念 | 说明 |
|------|------|
| 短期记忆 | 当前会话上下文 |
| 长期记忆 | 跨会话的知识沉淀 |
| 主题 | 按主题分类的记忆 |

## 核心文件

| 文件 | 功能 |
|------|------|
| `core.py` | 记忆核心逻辑 |
| `engine.py` | 记忆引擎（沉淀） |
| `ui.py` | 记忆 UI |

## 访问方式

访问 `/memory` 页面查看记忆系统。

## 记忆策略注册

```bash
python deva/naja/strategy/tools/register_memory.py
```

## 数据流

```
策略执行结果 → ResultStore → MemoryEngine → 记忆沉淀
                                     ↓
                              ┌───────────────┐
                              │  短期记忆     │
                              │  长期记忆     │
                              │  主题沉淀     │
                              └───────────────┘
```

## 相关文档

- [NAJA_OVERVIEW.md](../NAJA_OVERVIEW.md)
- [radar_guide.md](radar_guide.md) - 雷达系统
