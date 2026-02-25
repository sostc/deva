故障排查指南
============

.. contents:: 目录
   :depth: 3
   :local:

概述
----

本指南帮助快速诊断和解决 Deva 使用过程中的常见问题。

安装问题
--------

问题：pip install 失败
~~~~~~~~~~~~~~~~~~~~~~

**错误信息：**

.. code-block:: text

   ERROR: Could not install packages due to an EnvironmentError: [Errno 13] Permission denied

**解决方案：**

1. 使用 ``--user`` 参数：

   .. code-block:: bash

      pip install --user deva

2. 或使用虚拟环境：

   .. code-block:: bash

      python -m venv venv
      source venv/bin/activate
      pip install deva

问题：依赖冲突
~~~~~~~~~~~~~~

**错误信息：**

.. code-block:: text

   ERROR: Cannot install deva and deva[redis] because these package versions have conflicting dependencies

**解决方案：**

.. code-block:: bash

   pip install --upgrade pip
   pip install 'deva[redis,search]'


运行问题
--------

问题：脚本不退出
~~~~~~~~~~~~~~~~

**现象：**

脚本运行后一直阻塞，不退出。

**原因：**

Deva.run() 启动事件循环，会持续运行。

**解决方案：**

1. 正常运行（预期行为）：

   .. code-block:: python

      Deva.run()  # 按 Ctrl+C 停止

2. 定时停止：

   .. code-block:: python

      import threading
      threading.Timer(10, lambda: exit()).start()
      Deva.run()

3. Jupyter 中运行：

   .. code-block:: python

      # Jupyter 中不需要 Deva.run()
      s >> log

问题：Timer 不执行
~~~~~~~~~~~~~~~~~

**现象：**

定时器创建后没有执行。

**检查清单：**

1. 是否调用了 ``start()``：

   .. code-block:: python

      # ❌ 错误
      timer(func=lambda: "tick")

      # ✅ 正确
      timer(func=lambda: "tick", start=True)

2. 是否调用了 ``Deva.run()``：

   .. code-block:: python

      timer(start=True) >> log
      Deva.run()  # 必须有

3. 间隔时间是否合理：

   .. code-block:: python

      # 间隔不能为负数或 0
      timer(interval=1, func=func, start=True)  # interval >= 0.1

问题：Bus 消息丢失
~~~~~~~~~~~~~~~~

**现象：**

发送到 bus 的消息没有接收到。

**排查步骤：**

1. 检查总线模式：

   .. code-block:: bash

      echo $DEVA_BUS_MODE

2. Redis 模式检查：

   .. code-block:: bash

      redis-cli ping  # 应返回 PONG
      redis-cli keys '*'  # 查看键

3. 本地模式限制：

   本地模式只能在同一进程内通信，跨进程需用 Redis 模式。

4. 确保订阅在发送之前：

   .. code-block:: python

      # ✅ 正确顺序
      bus >> log  # 先订阅
      "hello" >> bus  # 后发送


数据流问题
----------

问题：数据未处理
~~~~~~~~~~~~~~~~

**现象：**

emit 数据后没有输出。

**检查清单：**

1. 流是否已启动：

   .. code-block:: python

      s.start()  # 需要启动

2. 处理链是否正确连接：

   .. code-block:: python

      # ✅ 正确
      s.map(func) >> log

      # ❌ 错误（未连接输出）
      s.map(func)

3. filter 条件是否满足：

   .. code-block:: python

      # 检查 filter 条件
      s.filter(lambda x: x > 100)  # 如果数据都<=100 则无输出

问题：窗口计算错误
~~~~~~~~~~~~~~~~~

**现象：**

sliding_window 结果不符合预期。

**常见原因：**

1. 窗口大小设置：

   .. code-block:: python

      # 窗口大小必须为正整数
      s.sliding_window(5)  # ✅
      s.sliding_window(0)  # ❌

2. 数据量不足：

   .. code-block:: python

      # 窗口大小为 5，但只 emit 了 3 个数据
      s.sliding_window(5)  # 不会输出，直到收集满 5 个

3. 窗口类型选择：

   .. code-block:: python

      # 滑动窗口：每次移动 1 个元素
      s.sliding_window(5)

      # 时间窗口：按时间收集
      s.timed_window(seconds=10)


持久化问题
----------

问题：DBStream 写入失败
~~~~~~~~~~~~~~~~~~~~~~

**错误信息：**

.. code-block:: text

   TypeError: dict not supported in time mode

**原因：**

time 模式下默认拒绝 dict 直接写入。

**解决方案：**

1. 使用 append：

   .. code-block:: python

      db = NB('events', key_mode='time')
      db.append({'event': 'click'})  # ✅

2. 或切换模式：

   .. code-block:: python

      db = NB('config', key_mode='explicit')
      db['key'] = {'data': 'value'}  # ✅

问题：回放无数据
~~~~~~~~~~~~~~~

**现象：**

replay() 返回空结果。

**检查清单：**

1. 确认有数据：

   .. code-block:: python

      print(len(db))  # 检查数据量

2. 时间范围正确：

   .. code-block:: python

      # 指定有效的时间范围
      db.replay(start='2026-01-01', end='2026-12-31')

3. key_mode 影响：

   time 模式才有时间回放，explicit 模式不支持时间回放。


Web 可视化问题
--------------

问题：页面无法访问
~~~~~~~~~~~~~~~~

**现象：**

浏览器无法访问 webview 页面。

**排查步骤：**

1. 检查服务是否启动：

   .. code-block:: python

      s.webview('/path')
      Deva.run()  # 必须调用

2. 检查端口：

   .. code-block:: bash

      netstat -tlnp | grep 9999

3. 检查 URL 路径：

   .. code-block:: python

      # 访问 http://127.0.0.1:9999/path
      s.webview('/path')

4. 防火墙设置：

   .. code-block:: bash

      # macOS
      sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off

      # Linux
      sudo ufw disable

问题：页面不更新
~~~~~~~~~~~~~~

**现象：**

Web 页面显示后不更新数据。

**解决方案：**

1. 确认流在持续产生数据：

   .. code-block:: python

      # 使用 timer 持续产生数据
      timer(interval=1, func=lambda: data, start=True)

2. 检查浏览器缓存：

   强制刷新页面（Ctrl+F5）

3. 检查 WebSocket 连接：

   打开浏览器开发者工具，查看 Console 和 Network


性能问题
--------

问题：处理速度慢
~~~~~~~~~~~~~~~~

**优化建议：**

1. 使用 rate_limit 控制流速：

   .. code-block:: python

      source.rate_limit(1000) >> processor

2. 批量处理：

   .. code-block:: python

      source.buffer(size=100).map(batch_process)

3. 减少窗口大小：

   .. code-block:: python

      # 小窗口更快
      s.sliding_window(10)  # 比 1000 快

4. 异步处理：

   .. code-block:: python

      # 使用异步函数
      async def async_process(x):
          return await do_something(x)

问题：内存占用高
~~~~~~~~~~~~~~

**优化建议：**

1. 限制 buffer 大小：

   .. code-block:: python

      s.buffer(size=100, timeout=1)  # 限制最多 100 条

2. 限制 DBStream 大小：

   .. code-block:: python

      db = DBStream('events.db', 'events', maxsize=10000)

3. 及时清理：

   .. code-block:: python

      with Stream() as s:
          # 自动清理


日志问题
--------

问题：日志不输出
~~~~~~~~~~~~~~

**检查清单：**

1. 日志级别设置：

   .. code-block:: bash

      export DEVA_LOG_LEVEL=DEBUG

2. 连接是否正确：

   .. code-block:: python

      # ✅ 正确
      s >> log

      # ❌ 错误（未连接）
      log

3. 转发设置：

   .. code-block:: bash

      export DEVA_LOG_FORWARD_TO_LOGGING=1


跨进程通信问题
--------------

问题：Redis 连接失败
~~~~~~~~~~~~~~~~~

**错误信息：**

.. code-block:: text

   redis.exceptions.ConnectionError: Error connecting to Redis

**解决方案：**

1. 启动 Redis：

   .. code-block:: bash

      redis-server

2. 检查连接：

   .. code-block:: bash

      redis-cli ping

3. 配置 URL：

   .. code-block:: bash

      export DEVA_REDIS_URL=redis://localhost:6379/0

问题：消费者组读取失败
~~~~~~~~~~~~~~~~~~~

**错误信息：**

.. code-block:: text

   NOGROUP No such consumer group

**解决方案：**

.. code-block:: python

   from deva.topic import Topic

   # 创建消费者组
   topic = Topic("orders", group="my-group", create_group=True)


调试技巧
--------

1. 启用调试日志

   .. code-block:: bash

      export DEVA_LOG_LEVEL=DEBUG

2. 可视化流拓扑

   .. code-block:: python

      s.visualize()  # 输出流的拓扑结构

3. 添加日志点

   .. code-block:: python

      s.map(lambda x: (log.debug(f"处理：{x}"), x)[1])

4. 使用 sink 观察

   .. code-block:: python

      result = []
      s.sink(result.append)
      # 检查 result 内容


获取帮助
--------

如果以上方法无法解决问题：

1. 查看文档：

   - :doc:`manual_cn` - 使用手册
   - :doc:`best_practices` - 最佳实践

2. 检查示例：

   - :doc:`examples` - 示例集合

3. 提交 Issue：

   - `GitHub Issues <https://github.com/sostc/deva/issues>`_

4. 提供信息：

   - Deva 版本
   - Python 版本
   - 操作系统
   - 错误日志
   - 最小可复现代码


总结
----

故障排查流程：

1. ✅ 阅读错误信息
2. ✅ 检查相关文档
3. ✅ 运行示例对比
4. ✅ 启用调试日志
5. ✅ 最小化复现
6. ✅ 寻求帮助
