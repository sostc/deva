# Deva Examples Index | 示例集合

## 📖 快速说明

本目录包含 Deva 的完整示例集合，涵盖从基础到高级的所有使用场景。每个示例都包含：

- ✅ 完整的可运行代码
- ✅ 详细的功能说明
- ✅ 预期输出示例
- ✅ 常见问题解答

---

## 🚀 快速开始

### 运行示例

1. **克隆或进入 Deva 项目目录**

```bash
cd /path/to/deva
```

2. **运行任意示例**

```bash
python3 deva/examples/{示例路径}/{脚本名}.py
```

3. **停止示例**

大多数示例会持续运行，按 `Ctrl+C` 停止。

---

## 📋 示例清单

### 基础示例 | Basic Examples

#### 1. 定时器 | Timer

演示定时任务的基本用法。

| 示例 | 说明 | 运行命令 |
|------|------|----------|
| [Timer](when/timer/) | 默认定时器和自定义间隔 | `python3 deva/examples/when/timer.py` |
| [Scheduler](when/scheduler/) | 计划任务和 CRON 调度 | `python3 deva/examples/when/scheduler.py` |

#### 2. 消息总线 | Bus

演示跨进程通信和消息传递。

| 示例 | 说明 | 运行命令 |
|------|------|----------|
| [Bus 输入端](bus/bus_in/) | 向 bus 发送数据 | `python3 deva/examples/bus/bus_in.py` |
| [Bus 输出端](bus/bus_out/) | 从 bus 接收数据 | `python3 deva/examples/bus/bus_out.py` |

#### 3. 存储与回放 | Storage

演示数据持久化和事件回放。

| 示例 | 说明 | 运行命令 |
|------|------|----------|
| [信号存储与回放](storage/signal_store_replay/) | DBStream 基本用法 | `python3 deva/examples/storage/signal_store_replay.py` |

---

### 进阶示例 | Advanced Examples

#### 4. Web 可视化 | Webview

演示如何生成 Web 监控页面。

| 示例 | 说明 | 运行命令 |
|------|------|----------|
| [流页面](webview/stream_page/) | 实时数据流 Web 展示 | `python3 deva/examples/webview/stream_page.py` |
| [SSE 服务器推送](sse/) | Server-Sent Events | `python3 deva/examples/sse.py` |

#### 5. 数据采集 | Crawler

演示 HTTP 请求和数据采集。

| 示例 | 说明 | 运行命令 |
|------|------|----------|
| [异步 HTTP](crawler/asynchttp/) | 并发 HTTP 请求 | `python3 deva/examples/crawler/asynchttp.py` |

#### 6. 全文检索 | Search

演示基于 Whoosh 的全文检索功能。

| 示例 | 说明 | 运行命令 |
|------|------|----------|
| [流式检索](search/search_stream/) | 流式全文搜索 | `python3 deva/examples/search/search_stream.py` |
| [SQL 检索](search/search_sql/) | SQL 方式查询索引 | `python3 deva/examples/search/search_sql.py` |

---

### 特色示例 | Featured Examples

#### 7. 日志监控 | Log Watchdog

实时监控日志文件并告警。

| 文件 | 说明 |
|------|------|
| [generate_logs.py](log_watchdog/) | 生成测试日志 |
| [watchdog.py](log_watchdog/) | 监控并告警 |

运行方式：

```bash
# 终端 1：生成日志
python3 deva/examples/log_watchdog/generate_logs.py --file ./app.log

# 终端 2：监控日志
python3 deva/examples/log_watchdog/watchdog.py --file ./app.log
```

#### 8. 矩阵计算 | MatMul

演示流式矩阵乘法计算。

```bash
python3 deva/examples/matmul.py
```

#### 9. 异步 Future | My Future

演示异步 Future 模式。

```bash
python3 deva/examples/my_future.py
```

#### 10. 愚公移山 | Yugong Yishan

寓言故事示例，演示递归和流式处理。

```bash
python3 deva/examples/愚公移山.py
```

---

## 🎯 按场景查找示例

### 实时数据处理

```
数据源 -> map/filter -> sliding_window -> 输出/存储
```

**推荐示例：**
- [Timer](when/timer/) - 定时数据生成
- [Log Watchdog](log_watchdog/) - 实时日志处理

### 定时任务调度

```
timer/scheduler -> 处理函数 -> 输出
```

**推荐示例：**
- [Timer](when/timer/) - 简单定时
- [Scheduler](when/scheduler/) - 复杂调度

### 跨进程通信

```
生产者 -> bus/topic -> 消费者
```

**推荐示例：**
- [Bus 输入端](bus/bus_in/) - 消息发送
- [Bus 输出端](bus/bus_out/) - 消息接收

### 数据持久化

```
数据流 -> DBStream -> 回放/查询
```

**推荐示例：**
- [信号存储与回放](storage/signal_store_replay/) - 完整示例

### Web 可视化

```
数据流 -> webview() -> 浏览器访问
```

**推荐示例：**
- [流页面](webview/stream_page/) - 基础 Web 视图
- [SSE](sse/) - 实时推送

---

## 📚 学习路径建议

### 初学者路径

1. ⭐ [Timer](when/timer/) - 理解定时任务
2. ⭐ [Bus 输入端/输出端](bus/bus_in/) - 理解消息传递
3. ⭐ [流页面](webview/stream_page/) - 体验 Web 可视化

### 进阶路径

1. ⭐⭐ [Scheduler](when/scheduler/) - 复杂调度
2. ⭐⭐ [信号存储与回放](storage/signal_store_replay/) - 持久化
3. ⭐⭐ [日志监控](log_watchdog/) - 综合应用

### 高级路径

1. ⭐⭐⭐ [异步 HTTP](crawler/asynchttp/) - 并发处理
2. ⭐⭐⭐ [全文检索](search/search_stream/) - 高级功能
3. ⭐⭐⭐ [愚公移山](愚公移山.py) - 复杂递归

---

## 🔧 运行所有示例

批量测试所有示例：

```bash
# 运行基础示例
for script in deva/examples/when/*.py; do
    echo "Running $script"
    timeout 5 python3 "$script" || true
done
```

---

## ❓ 常见问题

### Q: 示例运行后不退出？

**A:** 大多数示例设计为持续运行（如定时器、Web 服务），需要按 `Ctrl+C` 手动停止。

### Q: 如何在 Jupyter 中运行示例？

**A:** 在 Jupyter 中不需要调用 `Deva.run()`，直接运行流代码即可。

### Q: Bus 示例收不到消息？

**A:** 确保两个终端都运行了，并且 Redis 服务已启动（如果使用 Redis 模式）。

### Q: Web 页面无法访问？

**A:** 检查：
1. 示例是否正在运行
2. 端口 9999 是否被占用
3. 防火墙设置

---

## 📖 相关文档

- :doc:`../source/quickstart` - 快速开始
- :doc:`../source/manual_cn` - 使用手册
- :doc:`../source/installation` - 安装指南

## 🔗 外部资源

- [GitHub 仓库](https://github.com/sostc/deva)
- [PyPI 页面](https://pypi.org/project/deva/)
- [问题反馈](https://github.com/sostc/deva/issues)

---

**最后更新：** 2026-02-26

**Deva 版本：** 1.0
