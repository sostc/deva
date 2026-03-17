# Naja Agent 系统指南

> 基于最新代码结构（2026-03-17）

## 概述

Naja Agent 系统包含多个专用 Agent，用于不同的量化任务。

## Agent 列表

| Agent | 功能 | 说明 |
|-------|------|------|
| **Hanxin** | 交易执行 | 执行买卖交易 |
| **Liubang** | 持仓分析 | 分析账户持仓 |
| **Zhangliang** | 策略调度 | 管理策略运行 |
| **Xiaohe** | 对话交互 | 用户交互 |

## 核心文件

| 文件 | 功能 |
|------|------|
| `base.py` | Agent 基类 |
| `hanxin.py` | Hanxin 实现 |
| `liubang.py` | Liubang 实现 |
| `zhangliang.py` | Zhangliang 实现 |
| `xiaohe.py` | Xiaohe 实现 |
| `manager.py` | Agent 管理器 |

## 访问方式

访问 `/agentadmin` 管理 Agent。

## 相关文档

- [strategy_guide.md](strategy_guide.md) - 策略系统
