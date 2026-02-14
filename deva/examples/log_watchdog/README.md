# log-watchdog

一个基于 `deva` 的实时日志监控样例：

- 持续读取增长中的日志文件
- 识别 `WARNING/ERROR/CRITICAL` 日志
- 在滚动时间窗口内达到阈值时触发告警
- 通过 cooldown 避免告警风暴

## 文件结构

- `watchdog.py`: 监控与告警主程序
- `generate_logs.py`: 生成演示日志

## 快速开始

在仓库根目录执行：

```bash
# 终端1：生成测试日志
python3 deva/examples/log_watchdog/generate_logs.py --file ./app.log
```

```bash
# 终端2：启动监控
python3 deva/examples/log_watchdog/watchdog.py --file ./app.log
```

## 你会看到什么

- 普通日志会输出到 `log`
- 当窗口内错误数超过阈值，会输出类似：

```text
ALERT: ERROR spike. 4 errors in last 60s. Last line: ...
```

## 常用参数

`watchdog.py`:

- `--window`: 统计窗口秒数，默认 `60`
- `--error-threshold`: 错误阈值，默认 `3`
- `--warning-threshold`: 警告阈值，默认 `8`
- `--cooldown`: 告警冷却秒数，默认 `30`
- `--poll`: 文件轮询间隔秒数，默认 `0.2`

`generate_logs.py`:

- `--interval`: 每条日志间隔秒数，默认 `0.4`
- `--burst-every`: 每 N 条触发一次突发日志，默认 `25`

## 生产化建议

- 将告警 sink 接到 IM/邮件（例如钉钉、企业微信、Slack）
- 将事件写入 `DBStream` 做事后分析
- 按服务、租户拆分多条 watchdog 流
