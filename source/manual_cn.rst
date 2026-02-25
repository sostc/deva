Deva 使用说明书
=================

.. contents:: 目录
   :depth: 3
   :local:

文档目标
--------

本说明书面向以下读者：

- 初次接触 Deva，希望快速建立整体认知
- 已有 Python 经验，希望用 Deva 搭建流式处理系统
- 维护已有 Deva 项目，需要按模块查找用法

你将获得三类信息：

- Deva 的核心理念与设计取舍
- 典型业务场景与落地模式
- 各模块职责与最小可运行示例

快速参考
--------

================== ==================
主题               章节
================== ==================
核心概念           `1. Deva 的理念`_
快速上手           `2. 快速上手`_
流处理算子         `5.1 deva.core`_
窗口计算           `5.2 deva.compute`_
数据源接入         `5.3 deva.sources`_
定时任务           `5.4 deva.when`_
持久化存储         `5.5 deva.store`_
消息总线           `5.6 deva.bus`_
Web 可视化          `5.8 deva.page`_
================== ==================


1. Deva 的理念
---------------

Deva 的核心是“把程序拆成可组合的数据流”。

传统写法通常是：

- 手动写循环
- 手动控制函数调用顺序
- 手动处理异步、重试、状态缓存

Deva 写法强调：

- 用 `Stream` 表达数据流动
- 用 `>>` 把“数据源 -> 处理算子 -> 输出端”串成管道
- 用定时器、调度器、消息总线统一事件驱动

简化理解：

- `Stream` 是“数据经过的管道”
- `map/filter/window` 是“管道上的处理节点”
- `log/warn/DBStream/webview` 是“结果去向”


2. 快速上手
-----------

安装：

.. code-block:: bash

   pip install deva

最小示例（从输入到输出）：

.. code-block:: python

   from deva import Stream, log, Deva

   source = Stream(name="numbers")
   source.map(lambda x: x * 2).filter(lambda x: x > 3) >> log

   for i in range(5):
       source.emit(i)

   Deva.run()

说明：

- `emit()` 把数据放入流
- `map/filter` 进行处理
- `>> log` 把处理结果输出到日志流
- `Deva.run()` 启动事件循环（脚本模式建议保留）


3. 典型使用场景
---------------

3.1 实时日志监控与告警
~~~~~~~~~~~~~~~~~~~~~~~

适用场景：

- 读取不断增长的日志文件
- 在时间窗口内统计错误数
- 达到阈值后触发告警

参考示例：

- `deva/examples/log_watchdog/watchdog.py`
- `deva/examples/log_watchdog/generate_logs.py`


3.2 流式 ETL / 实时数据处理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

适用场景：

- 数据清洗、过滤、聚合
- 按窗口统计、延迟处理、去重
- 多流合并（`zip/combine_latest/union`）

典型链路：

.. code-block:: text

   source -> map(clean) -> filter(valid) -> sliding_window -> sink/store


3.3 定时任务与计划任务
~~~~~~~~~~~~~~~~~~~~~~

适用场景：

- 周期轮询 API
- 定时跑策略任务
- 固定时间触发事件

参考示例：

- `deva/examples/when/timer.py`
- `deva/examples/when/scheduler.py`


3.4 跨进程消息通信（Bus / Topic）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

适用场景：

- 多进程/多服务之间传递事件
- 解耦生产者与消费者
- 通过 Redis 或本地后端进行消息传输

参考示例：

- `deva/examples/bus/bus_in.py`
- `deva/examples/bus/bus_out.py`


3.5 持久化与回放
~~~~~~~~~~~~~~~~

适用场景：

- 记录事件历史
- 事后审计与重放
- 保存配置和状态

核心组件：

- `DBStream`
- `NB('name')`（命名存储）

参考示例：

- `deva/examples/storage/signal_store_replay.py`


3.6 可视化与运维面板
~~~~~~~~~~~~~~~~~~~~

适用场景：

- 在线观察流的最新数据
- 快速排查处理链路
- 管理任务、查看运行状态

核心组件：

- `stream.webview()`
- `deva.admin`


4. 模块总览
-----------

建议按以下顺序学习：

1. `core`（流模型）
2. `compute`（常用算子）
3. `sources`（输入源）
4. `when`（timer/scheduler）
5. `store`（持久化）
6. `bus`（跨进程通信）
7. `page/admin`（可视化与管理）
8. `search/endpoints/llm`（扩展能力）


5. 各模块使用方法
-----------------

5.1 `deva.core`：流模型与基础算子
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

核心对象：

- `Stream`
- `Deva`

常用能力：

- `emit()` 注入数据
- `map()/filter()/starmap()` 转换与筛选
- `sink()` 接收输出
- `route()/sub()/pub()` 路由与主题分发
- `catch()/catch_except()` 捕获结果或异常
- `visualize()` 输出拓扑图

示例：

.. code-block:: python

   from deva import Stream, log

   s = Stream(name="orders")
   (
       s.map(lambda x: {"id": x["id"], "amount": x["amount"] * 1.06})
        .filter(lambda x: x["amount"] > 100)
   ) >> log

   s.emit({"id": "A001", "amount": 120})


5.2 `deva.compute`：窗口、合流、去重等计算算子
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

常用算子（`Stream.register_api`）：

- 节流/缓冲：`rate_limit`、`buffer`、`delay`
- 窗口：`sliding_window`、`timed_window`、`partition`
- 多流组合：`zip`、`zip_latest`、`combine_latest`、`union`
- 数据整理：`flatten`、`pluck`、`collect`
- 状态计算：`accumulate`、`latest`、`unique`

示例（窗口统计）：

.. code-block:: python

   from deva import Stream, log

   source = Stream(name="ticks")
   source.sliding_window(3).map(lambda xs: sum(xs) / len(xs)) >> log

   for v in [10, 12, 9, 15, 18]:
       source.emit(v)


5.3 `deva.sources`：外部输入接入
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

典型数据源：

- 文件：`Stream.from_textfile(path)`
- 命令：`Stream.from_command()` / `Stream.from_process()`
- Redis：`Stream.RedisStream(...)`、`Stream.from_redis(...)`
- HTTP/TCP：`from_http_server`、`from_tcp_port`
- 周期函数：`from_periodic`

示例（文件流）：

.. code-block:: python

   from deva import Stream, warn

   s = Stream.from_textfile("./app.log", start=True)
   s.filter(lambda line: "ERROR" in line) >> warn


5.4 `deva.when`：定时器与调度器
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

组件：

- `timer(interval=..., func=..., start=True/False)`
- `scheduler(start=True/False)`
- `when('exit', source=...)`（进程退出事件）

示例（每 5 秒执行任务）：

.. code-block:: python

   from deva import timer, log, Deva
   import time

   timer(interval=5, func=lambda: {"ts": time.time()}, start=True) >> log
   Deva.run()

示例（调度器）：

.. code-block:: python

   from deva import Stream, log, Deva

   sch = Stream.scheduler()
   sch.add_job(func=lambda: "heartbeat", seconds=10)
   sch >> log
   Deva.run()


5.5 `deva.store` 与 `deva.namespace.NB`：持久化存储
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

核心类型：

- `DBStream`

两种键模式：

- `key_mode='explicit'`：适合配置/状态（键值覆盖）
- `key_mode='time'`：适合事件流（时间键追加）

常用 API：

- `append(value, key=None)` 追加事件
- `upsert(key, value)` 写入或覆盖
- `bulk_update(mapping)` 批量更新
- `replay(start=None, end=None, interval=None)` 回放

示例：

.. code-block:: python

   from deva import NB

   events = NB("signals", key_mode="time")
   events.append({"symbol": "AAPL", "score": 0.93})

   cfg = NB("config")
   cfg.upsert("risk.max_position", 0.2)


5.6 `deva.bus`：全局事件总线与统一日志流
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

默认全局流：

- `log`：信息日志
- `warn`：告警日志
- `debug`：调试日志
- `bus`：通用事件总线

总线后端：

- 本地模式（`local`）
- Redis 模式（默认）
- 文件 IPC 模式（`file-ipc`）

示例：

.. code-block:: python

   from deva import bus, log, warn, Deva

   bus.filter(lambda x: isinstance(x, int)).map(lambda x: x * 2) >> warn
   "hello" >> bus
   12 >> bus

   bus >> log
   Deva.run()


5.7 `deva.namespace`：命名对象工厂（全局单例）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

快捷函数：

- `NS(name)`：命名 `Stream`
- `NT(name)`：命名 `Topic`
- `NB(name)`：命名 `DBStream`
- `NW(name)`：命名 `PageServer`

用途：

- 在不同模块/文件共享同名对象
- 避免重复初始化同类组件

示例：

.. code-block:: python

   from deva import NS

   s1 = NS("quotes")
   s2 = NS("quotes")
   assert s1 is s2


5.8 `deva.page`：Web 可视化页面
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

能力：

- `stream.webview(url=...)`：把流挂到页面
- `PageServer`：自定义页面服务
- `render_template`：模板渲染

示例：

.. code-block:: python

   from deva import Stream, timer, Deva

   s = timer(interval=1, func=lambda: "tick", start=True, name="ticker")
   s.webview("/ticker")
   Deva.run()

参考：

- `deva/examples/webview/stream_page.py`


5.9 `deva.admin`：管理面板
~~~~~~~~~~~~~~~~~~~~~~~~~~

能力：

- 流/日志/任务的可视化管理
- 数据表与对象检查
- Bus 状态查看

典型启动方式（按项目实际入口）：

- 作为模块引入并调用启动函数
- 或运行项目内已有 admin 启动脚本

建议：

- 优先用于开发/测试环境排查
- 生产环境请配合认证与网络访问控制


5.10 `deva.search`：全文检索流（IndexStream）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

能力：

- 基于 Whoosh + 结巴分词建立中文索引
- `search(query, limit)` 查询
- `ask(question)` 相似问题匹配

示例：

.. code-block:: python

   from deva import Stream

   idx = Stream.IndexStream("./whoosh/demo_idx")
   "Deva 是流式处理框架" >> idx
   ("doc2", "支持定时任务和消息总线") >> idx
   print(list(idx.search("定时任务")))


5.11 `deva.endpoints`：外部系统输出端
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

组件：

- `to_kafka`：写入 Kafka
- `to_redis`：写入 Redis Stream
- `Dtalk`：发送钉钉机器人消息
- `mail`：邮件发送

示例：

.. code-block:: python

   from deva import Stream

   s = Stream()
   # 需要先安装并配置 Kafka 连接参数
   k = s.map(str).to_kafka("events", {"bootstrap.servers": "localhost:9092"})
   s.emit("hello")
   k.flush()


5.12 `deva.llm`：LLM 调用（可选）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

能力：

- `sync_gpt(prompts)`：同步调用
- `async_gpt(prompts)`：异步调用

依赖：

- 需安装带 LLM 依赖的版本（例如 `pip install 'deva[llm]'`）
- 需在 `NB(...)` 中配置模型/密钥信息（以代码示例为准）


6. 场景化实践模板
-----------------

模板 A：实时监控
~~~~~~~~~~~~~~~~

.. code-block:: text

   from_textfile -> filter(ERROR) -> sliding_window -> warn -> DBStream

模板 B：定时抓取
~~~~~~~~~~~~~~~~

.. code-block:: text

   timer -> http/crawler -> map(parse) -> filter(valid) -> bus/store

模板 C：跨进程协作
~~~~~~~~~~~~~~~~~~

.. code-block:: text

   producer -> bus/topic -> consumer(map/filter) -> endpoints

模板 D：可回放事件系统
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   source -> DBStream(key_mode=time, append) -> replay -> analysis


7. 常见问题
-----------

Q1：脚本不退出？
~~~~~~~~~~~~~~~~

- `timer/scheduler` 默认会持续运行
- 脚本中调用 `Deva.run()` 后会进入事件循环
- 需要手动 `Ctrl+C` 或在代码中 `stop()`

Q2：跨进程消息收不到？
~~~~~~~~~~~~~~~~~~~~~~

- 检查 `DEVA_BUS_MODE` 配置
- Redis 模式下确认 Redis 可用、连接参数正确
- 本地模式只能在当前进程内可见

Q3：DBStream 里 dict 写入报错？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 若使用 `key_mode='time'`，默认拒绝 dict 直接写入
- 用 `append(dict)`，或切换 `time_dict_policy='append'`

Q4：什么时候用 `NB`，什么时候直接用 `DBStream`？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- `NB(name)`：更方便，适合全局共享命名表
- `DBStream(...)`：更灵活，适合自定义 filename/maxsize 等参数


8. 建议的学习路径
-----------------

1. 跑通 `deva/examples/when/timer.py`
2. 跑通 `deva/examples/bus/bus_in.py` + `deva/examples/bus/bus_out.py`
3. 跑通 `deva/examples/storage/signal_store_replay.py`
4. 尝试 `deva/examples/webview/stream_page.py`
5. 基于你的业务把输入源替换为真实数据


9. 附：示例命令速查
-------------------

.. code-block:: bash

   # 定时器
   python3 deva/examples/when/timer.py

   # 调度器
   python3 deva/examples/when/scheduler.py

   # Bus 输入端
   python3 deva/examples/bus/bus_in.py

   # Bus 输出端
   python3 deva/examples/bus/bus_out.py

   # 存储与回放
   python3 deva/examples/storage/signal_store_replay.py

   # WebView 示例
   python3 deva/examples/webview/stream_page.py

   # 日志监控（两个终端）
   python3 deva/examples/log_watchdog/generate_logs.py --file ./app.log
   python3 deva/examples/log_watchdog/watchdog.py --file ./app.log

