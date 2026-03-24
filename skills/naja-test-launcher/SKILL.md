---
name: naja-test-launcher
description: 启动 Naja 系统各种测试模式。当用户想要启动实盘测试、实验室模式、回放模式、雷达调试等时使用此技能。
---

# Naja Test Launcher

启动 Naja 系统的各种测试和实验模式。

## 启动模式

### 1. 实验室模式（数据回放）

```bash
python -m deva.naja --lab --lab-table quant_snapshot_5min_window --lab-interval 1.0 --lab-debug --port 8080
```

参数说明：
- `--lab`: 启用实验室模式
- `--lab-table`: 回放数据表名，默认 `quant_snapshot_5min_window`
- `--lab-interval`: 回放间隔（秒），默认 1.0
- `--lab-debug`: 启用调试日志
- `--lab-speed`: 回放速度倍数，默认 1.0
- `--port`: Web 端口，默认 8080

### 2. 雷达调试模式

```bash
python -m deva.naja --radar-debug --radar-interval 0.5 --port 8080
```

参数说明：
- `--radar-debug`: 启用雷达调试模式
- `--radar-interval`: 雷达数据间隔（秒）
- `--news-radar`: 启动新闻舆情策略
- `--cognition-debug`: 启用认知系统调试

### 3. 认知系统调试（自动启用实验室+雷达+新闻）

```bash
python -m deva.naja --cognition-debug --port 8080
```

### 4. 强制交易模式（模拟实盘）

当需要强制模拟交易时间时，可以在代码中设置：

```python
import os
os.environ['NAJA_FORCE_TRADING'] = 'true'
```

或者在启动时手动启动组件：

```bash
python -m deva.naja --attention --port 8080
```

## 当前时间判断

A股交易时间：
- 盘前: 09:00-09:30
- 交易: 09:30-11:30 / 13:00-15:00
- 盘后: 15:00-15:30
- 休市: 15:30 后及周末

## 使用场景

| 场景 | 推荐命令 |
|------|---------|
| 数据回放测试 | `--lab --lab-table quant_snapshot_5min_window --lab-interval 1.0 --lab-debug` |
| 新闻舆情测试 | `--news-radar --radar-interval 0.5` |
| 完整系统测试 | `--cognition-debug` |
| 收盘后模拟交易 | 设置 `NAJA_FORCE_TRADING=true` 后启动 |
| 明天开盘前测试 | `--lab` 使用历史数据回放 |

## 日志查看

```bash
# 实时查看日志
tail -f /tmp/naja_debug.log

# 查看特定级别日志
python -m deva.naja --lab --log-level DEBUG

# 查看雷达日志
grep -i radar /tmp/naja_debug.log

# 查看交易时钟日志
grep -i trading /tmp/naja_debug.log
```

## 进程管理

```bash
# 查看运行中的进程
ps aux | grep deva.naja

# 停止所有 naja 进程
pkill -f "python -m deva.naja"

# 停止特定端口的进程
lsof -ti:8080 | xargs kill
```
