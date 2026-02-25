最佳实践指南
============

.. contents:: 目录
   :depth: 3
   :local:

概述
----

本文档总结了使用 Deva 进行流式处理的最佳实践，涵盖代码组织、性能优化、错误处理、监控告警等方面。

代码组织
--------

1. 模块化设计
~~~~~~~~~~~~~~

将流处理逻辑按功能模块组织：

.. code-block:: python

   # data_sources.py
   from deva import Stream, timer

   def create_price_stream():
       return timer(interval=1, func=get_price, start=True, name='prices')

   def create_order_stream():
       return Stream(name='orders')


   # processors.py
   def process_price(data):
       return {'symbol': data['symbol'], 'price': data['price'] * 1.06}

   def filter_valid_orders(order):
       return order.get('amount', 0) > 0


   # main.py
   from data_sources import create_price_stream
   from processors import process_price
   from deva import log, Deva

   prices = create_price_stream()
   prices.map(process_price) >> log

   Deva.run()

2. 配置分离
~~~~~~~~~~~

将配置参数提取到独立文件：

.. code-block:: python

   # config.py
   class Config:
       REDIS_URL = 'redis://localhost:6379/0'
       LOG_LEVEL = 'INFO'
       TIMER_INTERVAL = 1
       MAX_BUFFER_SIZE = 1000

   # main.py
   from config import Config
   from deva import timer

   s = timer(interval=Config.TIMER_INTERVAL, func=fetch_data, start=True)

3. 命名规范
~~~~~~~~~~~

使用有意义的流名称：

.. code-block:: python

   # ✅ 好的命名
   order_stream = Stream(name='orders')
   price_stream = Stream(name='market_prices')
   signal_stream = Stream(name='trading_signals')

   # ❌ 避免的命名
   s1 = Stream()
   s2 = Stream()


性能优化
--------

1. 控制流速
~~~~~~~~~~~

使用 rate_limit 防止下游过载：

.. code-block:: python

   from deva import Stream

   # 限制每秒处理 100 条数据
   source.rate_limit(100) >> processor

2. 批量处理
~~~~~~~~~~~

使用 buffer 积累数据后批量处理：

.. code-block:: python

   # 每 100 条或每 5 秒处理一次
   source.buffer(size=100, timeout=5).map(batch_process) >> log

3. 窗口优化
~~~~~~~~~~~

合理选择窗口大小：

.. code-block:: python

   # 小窗口：低延迟，高频率
   source.sliding_window(10) >> fast_processor

   # 大窗口：高准确，低频率
   source.sliding_window(1000) >> accurate_processor

4. 避免阻塞
~~~~~~~~~~~

使用异步操作避免阻塞流：

.. code-block:: python

   # ❌ 避免阻塞操作
   s.map(lambda x: time.sleep(1)) >> log

   # ✅ 使用异步
   from deva import Stream
   s.map(async_process) >> log


错误处理
--------

1. 捕获异常
~~~~~~~~~~~

使用 catch 处理异常：

.. code-block:: python

   from deva import Stream, log, warn

   def risky_process(x):
       if x < 0:
           raise ValueError("负数")
       return x * 2

   source.map(risky_process).catch(lambda e: warn.emit(f"错误：{e}")) >> log

2. 重试机制
~~~~~~~~~~~

实现重试逻辑：

.. code-block:: python

   def with_retry(func, max_retries=3):
       def wrapper(x):
           for i in range(max_retries):
               try:
                   return func(x)
               except Exception as e:
                   if i == max_retries - 1:
                       raise
                   time.sleep(2 ** i)  # 指数退避
       return wrapper

   source.map(with_retry(fetch_data)) >> log

3. 降级处理
~~~~~~~~~~~

提供降级方案：

.. code-block:: python

   def process_with_fallback(x):
       try:
           return process(x)
       except Exception:
           return {'status': 'error', 'fallback': True}

   source.map(process_with_fallback) >> log


监控与告警
----------

1. 关键指标
~~~~~~~~~~~

监控重要指标：

.. code-block:: python

   from deva import Stream, timer, NB

   # 创建监控流
   metrics = NB('metrics', key_mode='time')

   # 记录处理量
   counter = {'count': 0}
   source.map(lambda x: (counter.update(count=counter['count']+1), x)[1]) >> metrics

   # 定期上报
   timer(interval=60, func=lambda: counter.copy(), start=True) >> metrics

2. 健康检查
~~~~~~~~~~~

实现健康检查：

.. code-block:: python

   from deva import timer, log

   health_status = {'status': 'healthy', 'last_check': None}

   def check_health():
       health_status['last_check'] = __import__('time').time()
       return health_status

   timer(interval=10, func=check_health, start=True) >> log

3. 告警阈值
~~~~~~~~~~~

设置告警规则：

.. code-block:: python

   from deva import bus, warn

   def check_threshold(x):
       if x > 1000:
           warn.emit(f"超过阈值：{x}")
       return x

   source.map(check_threshold) >> processor


资源管理
--------

1. 流的生命周期
~~~~~~~~~~~~~~

正确管理流的启动和停止：

.. code-block:: python

   from deva import Stream

   s = Stream(name='temp')
   s.start()

   try:
       for i in range(100):
           s.emit(i)
   finally:
       s.stop()

2. 上下文管理器
~~~~~~~~~~~~~~

使用上下文管理器自动清理：

.. code-block:: python

   from deva import Stream

   with Stream(name='temp') as s:
       s >> log
       s.emit(100)

3. 资源限制
~~~~~~~~~~~

设置合理的资源限制：

.. code-block:: python

   from deva import DBStream

   # 限制数据库大小
   db = DBStream('events.db', 'events', maxsize=10000)


测试策略
--------

1. 单元测试
~~~~~~~~~~~

测试处理逻辑：

.. code-block:: python

   import pytest
   from deva import Stream

   def test_process():
       s = Stream()
       result = []
       s.map(lambda x: x * 2).sink(result.append)

       s.emit(5)
       assert result == [10]

2. 集成测试
~~~~~~~~~~~

测试完整流程：

.. code-block:: python

   def test_pipeline():
       from deva import Stream, log

       s = Stream(name='test')
       s.map(process).filter(valid) >> log

       s.start()
       s.emit(test_data)
       # 验证输出

3. 性能测试
~~~~~~~~~~~

测试吞吐量：

.. code-block:: python

   import time
   from deva import Stream

   def test_throughput():
       s = Stream()
       count = 0

       s.map(lambda x: x).sink(lambda x: nonlocal count; count += 1)
       s.start()

       start = time.time()
       for i in range(10000):
           s.emit(i)

       elapsed = time.time() - start
       print(f"吞吐量：{10000/el:.2f} 条/秒")


部署建议
--------

1. 环境配置
~~~~~~~~~~~

使用环境变量管理配置：

.. code-block:: bash

   export DEVA_LOG_LEVEL=INFO
   export DEVA_BUS_MODE=redis
   export DEVA_REDIS_URL=redis://prod-redis:6379/0

2. 进程管理
~~~~~~~~~~~

使用进程管理工具：

.. code-block:: bash

   # systemd 服务
   [Unit]
   Description=Deva Stream Processor
   After=network.target

   [Service]
   Type=simple
   User=deva
   ExecStart=/usr/bin/python3 /opt/deva/main.py
   Restart=always

   [Install]
   WantedBy=multi-user.target

3. 日志轮转
~~~~~~~~~~~

配置日志轮转：

.. code-block:: bash

   # /etc/logrotate.d/deva
   /var/log/deva/*.log {
       daily
       rotate 7
       compress
       missingok
       notifempty
   }


安全考虑
--------

1. 敏感信息
~~~~~~~~~~~

不要硬编码敏感信息：

.. code-block:: python

   # ❌ 避免
   API_KEY = "sk-1234567890"

   # ✅ 使用环境变量
   import os
   API_KEY = os.environ.get('API_KEY')

2. 输入验证
~~~~~~~~~~~

验证所有输入：

.. code-block:: python

   def safe_process(data):
       if not isinstance(data, dict):
           raise ValueError("无效数据格式")
       if 'amount' not in data:
           raise ValueError("缺少金额字段")
       return process(data)


总结
----

遵循这些最佳实践可以：

- ✅ 提高代码可维护性
- ✅ 优化系统性能
- ✅ 增强错误处理能力
- ✅ 改善监控和可观测性
- ✅ 确保资源合理使用

下一步
------

- :doc:`troubleshooting` - 故障排查指南
- :doc:`examples` - 查看示例代码
- :doc:`api` - API 参考
