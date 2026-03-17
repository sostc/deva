# Naja 性能监控指南

> 基于最新代码结构（2026-03-17）

## 概述

Naja 性能监控系统提供锁监控、存储监控和性能指标。

## 核心功能

| 功能 | 说明 |
|------|------|
| Lock Monitor | 锁监控 |
| Storage Monitor | 存储监控 |
| Performance Monitor | 性能监控 |

## 核心文件

| 文件 | 功能 |
|------|------|
| `lock_monitor.py` | 锁监控 |
| `storage_monitor.py` | 存储监控 |
| `performance_monitor.py` | 性能监控 |
| `ui.py` | 监控 UI |

## 访问方式

访问 `/monitor` 或 `/performance` 查看监控面板。

## 相关文档

- [strategy_guide.md](strategy_guide.md)
