# Naja LLM 调节指南

> 基于最新代码结构（2026-03-17）

## 概述

LLM 调节器根据雷达事件、记忆摘要和策略性能，生成调节建议。

## 核心功能

| 功能 | 说明 |
|------|------|
| Radar 摘要 | 读取雷达事件摘要 |
| Memory 摘要 | 读取记忆摘要 |
| 策略性能 | 分析策略表现 |
| 调节建议 | 生成优化建议 |

## 核心文件

| 文件 | 功能 |
|------|------|
| `controller.py` | LLM 控制器 |
| `ui.py` | LLM UI |

## 访问方式

访问 `/llmadmin` 查看调节面板。

## 相关文档

- [cognition_guide.md](cognition_guide.md) - 认知系统
- [radar_guide.md](radar_guide.md) - 雷达系统
