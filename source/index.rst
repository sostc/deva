.. deva documentation master file, created by
   sphinx-quickstart on Thu Oct 14 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

=====================================
Deva 异步流式处理框架文档
=====================================

.. image:: https://raw.githubusercontent.com/sostc/deva/master/deva.jpeg
   :target: https://github.com/sostc/deva
   :align: center
   :alt: Deva Logo

.. image:: https://img.shields.io/pypi/v/deva.svg
   :target: https://pypi.org/project/deva/
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/deva.svg
   :target: https://pypi.org/project/deva/
   :alt: Python Versions

概述
====

Deva 是一个基于 Python 的异步流式处理框架，提供了丰富的流操作符、HTTP 客户端、事件处理、管道操作等功能，适用于实时数据处理、事件驱动应用等场景。

核心理念
--------

- **流式处理**：用 Stream 表达数据流动，通过管道操作符组合处理逻辑
- **事件驱动**：基于消息总线和路由机制实现松耦合组件通信
- **定时调度**：内置定时器和调度器，轻松实现周期性任务和计划任务
- **持久化**：集成 SQLite 存储，支持事件回放和状态持久化
- **可视化**：一键生成 Web 监控页面，实时观察数据流状态

典型应用场景
------------

- 实时日志监控与告警
- 流式 ETL 和数据清洗
- 定时任务和数据采集
- 量化交易策略执行
- 事件驱动的微服务

快速链接
========

================== ==================
文档类型           链接
================== ==================
快速开始           :doc:`quickstart`
使用手册           :doc:`manual_cn`
安装指南           :doc:`installation`
示例集合           `GitHub Examples <https://github.com/sostc/deva/tree/master/deva/examples>`_
API 参考           :ref:`modindex`
================== ==================

目录
====

.. toctree::
   :maxdepth: 2
   :caption: 入门指南

   quickstart
   installation
   manual_cn

.. toctree::
   :maxdepth: 2
   :caption: 核心模块

   usage
   storage
   logging
   modules

.. toctree::
   :maxdepth: 2
   :caption: 示例与实战

   examples
   best_practices
   troubleshooting

.. toctree::
   :maxdepth: 1
   :caption: API 参考

   api

核心模块说明
============

流处理核心
----------

.. autosummary::
   :toctree: generated
   :recursive:

   deva.stream
   deva.compute
   deva.sources

事件与调度
----------

.. autosummary::
   :toctree: generated
   :recursive:

   deva.timer
   deva.scheduler
   deva.bus
   deva.topic

存储与持久化
------------

.. autosummary::
   :toctree: generated
   :recursive:

   deva.dbstream
   deva.namespace
   deva.store

可视化与管理
------------

.. autosummary::
   :toctree: generated
   :recursive:

   deva.page
   deva.admin

扩展功能
--------

.. autosummary::
   :toctree: generated
   :recursive:

   deva.http
   deva.search
   deva.endpoints
   deva.llm

索引和表格
==========

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
* :doc:`glossary`
