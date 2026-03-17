# Naja 数据源系统指南

> 基于最新代码结构（2026-03-17）

## 概述

Naja 数据源系统支持多种数据获取方式，包括定时拉取、实时流、文件监控、历史回放等。

## 数据源类型

| 类型 | 说明 | 典型场景 |
|------|------|----------|
| **timer** | 定时拉取 | 定时获取股票行情 |
| **stream** | 实时数据流 | 实时新闻、推送 |
| **file** | 文件监控 | 监控日志文件变化 |
| **directory** | 目录监控 | 监控目录文件增减 |
| **replay** | 历史数据回放 | 回测策略 |

## 使用 Skill 创建数据源

推荐使用 `datasource-creator` skill 创建数据源：

```bash
# 使用 datasource-creator skill
# 参考 .trae/skills/datasource-creator/
```

## 数据源管理页面

访问 `/dsadmin` 管理数据源。

## 数据源代码示例

```python
from deva.admin.datasource import (
    create_timer_source,
    create_stream_source,
    DataSourceType
)

# 创建定时数据源
timer_source = create_timer_source(
    source_id='stock_data',
    interval=60,
    code='''
import akshare as ak
df = ak.stock_zh_a_spot_em()
return df.head(10).to_dict()
'''
)
```

## 数据源绑定策略

数据源可以绑定到策略，实现数据自动输入：

```python
from deva.naja.strategy import bind_datasource

bind_datasource(strategy_id='my_strategy', datasource_id='stock_data')
```

## 相关文档

- [strategy_guide.md](strategy_guide.md) - 策略配置
- [datasource-creator skill](../.trae/skills/datasource-creator/SKILL.md)
