日志（Logging）
================

概述
----

Deva 默认提供统一日志输出链路：

- 流式日志：`log` / `warn` / `debug`
- 标准库日志：`logging.getLogger(...)`

两者都会收敛到统一格式，便于排障和检索。


默认格式
--------

日志输出格式为：

.. code-block:: text

   [2026-02-18 20:36:35][INFO][deva.page] start webview | {"url":"http://127.0.0.1:9999/"}

字段说明：

- `ts`：时间戳
- `level`：日志级别
- `source`：来源模块
- `message`：主消息
- `extra`：附加结构化字段


级别过滤
--------

通过环境变量控制最低输出级别：

.. code-block:: bash

   export DEVA_LOG_LEVEL=INFO

可选值：`DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。


转发到 Python logging
---------------------

`log/warn/debug` 默认会直接输出结构化文本。

如需再转发到 Python logging 管道（例如外接 handler），可开启：

.. code-block:: bash

   export DEVA_LOG_FORWARD_TO_LOGGING=1

默认值为 `0`，用于避免重复日志输出。


示例
----

.. code-block:: python

   from deva import log, warn, debug

   "service started" >> log

   {
       "level": "warning",
       "source": "crawler",
       "message": "request timeout",
       "url": "https://example.com"
   } >> warn

   {"message": "trace details", "step": 3} >> debug

