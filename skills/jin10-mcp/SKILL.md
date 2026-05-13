---
name: jin10-mcp
description: >
  金十数据财经数据服务集成。使用标准 MCP 协议访问实时行情、K线、快讯、新闻和财经日历。
  支持品种：现货黄金、白银、原油、外汇等。
  Triggers: jin10, 金十数据, 实时行情, 快讯, 财经日历, K线
---

# Jin10 MCP Skill (金十数据 MCP 集成)

使用金十数据提供的标准 MCP 协议访问财经数据服务。

## 1. 功能说明

### 可用工具

| 工具 | 描述 |
|------|------|
| `get_quote` | 获取指定品种实时行情报价 |
| `get_kline` | 获取指定品种分钟级 K 线数据 |
| `list_flash` | 获取最新快讯列表（支持分页） |
| `search_flash` | 按关键词搜索快讯 |
| `list_news` | 获取最新文章列表（支持分页） |
| `search_news` | 按关键词搜索文章 |
| `get_news` | 获取单篇文章详情 |
| `list_calendar` | 获取本周财经日历数据 |

### 常用品种代码

| 代码 | 名称 |
|------|------|
| `XAUUSD` | 现货黄金 |
| `XAGUSD` | 现货白银 |
| `USOIL` | WTI 原油 |
| `UKOIL` | 布伦特原油 |
| `COPPER` | 现货铜 |
| `USDJPY` | 美元/日元 |
| `EURUSD` | 欧元/美元 |
| `USDCNH` | 美元/人民币 |

## 2. 使用方法

### 使用 mcporter CLI 直接调用

```bash
# 列出所有工具
mcporter list jin10 --schema

# 获取黄金实时行情
mcporter call jin10.get_quote code:XAUUSD

# 获取黄金 K 线
mcporter call jin10.get_kline code:XAUUSD

# 获取快讯列表
mcporter call jin10.list_flash

# 搜索黄金相关快讯
mcporter call jin10.search_flash keyword:黄金

# 获取财经日历
mcporter call jin10.list_calendar
```

### 使用 Python 客户端

本 skill 包含 Python 客户端 `scripts/jin10_client.py`，提供更友好的接口：

```bash
# 获取行情
python scripts/jin10_client.py quote XAUUSD

# 获取 K 线
python scripts/jin10_client.py kline XAUUSD

# 获取快讯
python scripts/jin10_client.py flash

# 搜索快讯
python scripts/jin10_client.py search_flash 黄金

# 获取新闻
python scripts/jin10_client.py news

# 获取财经日历
python scripts/jin10_client.py calendar
```

## 3. 数据约定

### 报价数据结构
```json
{
  "code": "XAUUSD",
  "name": "现货黄金",
  "time": "2026-05-13T17:54:17+08:00",
  "open": "4715.39",
  "close": "4698.05",
  "high": "4726.57",
  "low": "4686.05",
  "volume": 108385,
  "ups_price": "-17.03",
  "ups_percent": "-0.36"
}
```

### 分页约定
- 请求参数：`cursor`
- 响应字段：`data.next_cursor`, `data.has_more`

## 4. 协议版本

使用推荐协议版本：`2025-11-25`
