.. deva documentation master file, created by
   sphinx-quickstart on Thu Oct 14 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. deva documentation master file, created by
   sphinx-quickstart on Thu Oct 14 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

欢迎使用 Deva 文档！
=====================

.. image:: https://raw.githubusercontent.com/sostc/deva/master/deva.jpeg
   :target: https://github.com/sostc/deva
   :align: center
   :alt: secsay.com

概述
----

Deva 是一个基于 Python 的异步流式处理框架，提供了丰富的流操作符、HTTP 客户端、事件处理、管道操作等功能，适用于实时数据处理、事件驱动应用等场景。

--------

.. image:: https://raw.githubusercontent.com/sostc/deva/master/streaming.gif
   :target: https://github.com/sostc/deva
   :align: center
   :alt: secsay.com

-------

.. toctree::
   :maxdepth: 2
   :caption: 目录:

   installation
   usage
   storage
   logging
   modules
   examples
   api

安装
----

.. include:: installation.rst

使用
----

.. include:: usage.rst

模块
----

.. toctree::
   :maxdepth: 2
   :caption: 模块:

   deva.stream
   deva.http
   deva.timer
   deva.page
   deva.bus
   deva.dbstream

示例
----

.. include:: examples.rst

API 参考
--------

.. automodule:: deva.stream
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: deva.http
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: deva.timer
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: deva.page
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: deva.bus
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: deva.dbstream
   :members:
   :undoc-members:
   :show-inheritance:

索引和表格
==========

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
