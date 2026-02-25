安装指南
========

.. contents:: 目录
   :depth: 3
   :local:

系统要求
--------

- Python 3.8 或更高版本
- pip 包管理器
- 操作系统：Linux / macOS / Windows

基础安装
--------

使用 pip 安装稳定版：

.. code-block:: bash

   pip install deva

或使用 pip3：

.. code-block:: bash

   pip3 install deva

验证安装
~~~~~~~~

安装完成后，验证是否成功：

.. code-block:: bash

   python -c "import deva; print(deva.__version__)"

输出应显示版本号，如：

.. code-block:: text

   1.0.0


可选依赖
--------

根据使用场景，可以选择安装不同的依赖包。

Redis 消息总线
~~~~~~~~~~~~~~

如需跨进程通信功能，需要安装 Redis 依赖：

.. code-block:: bash

   pip install deva[redis]

系统要求：

- Redis 5.0 或更高版本
- Python 包：redis >= 4.0.0

配置环境变量：

.. code-block:: bash

   export DEVA_BUS_MODE=redis
   export DEVA_REDIS_URL=redis://localhost:6379/0

全文检索
~~~~~~~~

如需全文检索功能（基于 Whoosh 和结巴分词）：

.. code-block:: bash

   pip install deva[search]

包含的依赖：

- Whoosh >= 2.7.4
- jieba >= 0.42.1

LLM 集成
~~~~~~~~

如需 LLM（大语言模型）集成功能：

.. code-block:: bash

   pip install deva[llm]

包含的依赖：

- openai >= 1.0.0
- transformers >= 4.0.0（可选，用于本地模型）

开发环境安装
------------

从源码安装
~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/sostc/deva.git
   cd deva
   pip install -e .

安装开发依赖
~~~~~~~~~~~~

.. code-block:: bash

   pip install -e ".[dev]"

开发依赖包含：

- pytest - 测试框架
- sphinx - 文档生成
- black - 代码格式化
- flake8 - 代码检查

运行测试
~~~~~~~~

确保安装开发依赖后，运行测试：

.. code-block:: bash

   pytest tests/

构建文档
~~~~~~~~

.. code-block:: bash

   cd docs
   make html

文档将生成在 ``build/html/`` 目录。


Docker 部署
-----------

使用 Docker 运行 Deva：

.. code-block:: bash

   docker pull sostc/deva:latest
   docker run -it sostc/deva

Dockerfile 示例
~~~~~~~~~~~~~

.. code-block:: dockerfile

   FROM python:3.10-slim

   RUN pip install deva[redis,search]

   WORKDIR /app
   COPY . /app

   CMD ["python", "app.py"]


云平台部署
----------

AWS
~~~

使用 Elastic Beanstalk：

.. code-block:: bash

   eb init
   eb create deva-env
   eb open deva-env

Heroku
~~~~~~

.. code-block:: bash

   heroku create my-deva-app
   git push heroku main
   heroku ps:scale worker=1

配置说明
--------

环境变量
~~~~~~~~

Deva 支持以下环境变量配置：

+---------------------------+------------------+--------------------------------+
| 变量名                    | 默认值           | 说明                           |
+===========================+==================+================================+
| DEVA_LOG_LEVEL            | INFO             | 日志级别                       |
+---------------------------+------------------+--------------------------------+
| DEVA_LOG_FORWARD_TO_      | 0                | 是否转发到 Python logging      |
| LOGGING                   |                  |                                |
+---------------------------+------------------+--------------------------------+
| DEVA_BUS_MODE             | local            | 消息总线模式：local/redis/     |
|                           |                  | file-ipc                       |
+---------------------------+------------------+--------------------------------+
| DEVA_REDIS_URL            | redis://         | Redis 连接 URL                  |
| localhost:6379/0          |                  |                                |
+---------------------------+------------------+--------------------------------+
| DEVA_WEBVIEW_PORT         | 9999             | Web 视图服务端口                |
+---------------------------+------------------+--------------------------------+

配置文件
~~~~~~~~

可以在项目根目录创建 ``deva.conf`` 文件：

.. code-block:: python

   # deva.conf
   LOG_LEVEL = 'INFO'
   BUS_MODE = 'redis'
   REDIS_URL = 'redis://localhost:6379/0'
   WEBVIEW_PORT = 9999


常见问题
--------

安装失败：权限错误
~~~~~~~~~~~~~~~~~~

**问题：**

.. code-block:: text

   ERROR: Could not install packages due to an EnvironmentError: [Errno 13] Permission denied

**解决方案：**

使用 ``--user`` 参数：

.. code-block:: bash

   pip install --user deva

或使用虚拟环境：

.. code-block:: bash

   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate     # Windows
   pip install deva

导入错误：ModuleNotFoundError
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**问题：**

.. code-block:: text

   ModuleNotFoundError: No module named 'deva'

**解决方案：**

确认 Python 环境正确：

.. code-block:: bash

   which python
   python -c "import sys; print(sys.executable)"

确保在正确的环境中安装。

Redis 连接失败
~~~~~~~~~~~~~~

**问题：**

.. code-block:: text

   redis.exceptions.ConnectionError: Error connecting to Redis

**解决方案：**

1. 确认 Redis 服务已启动：

   .. code-block:: bash

      redis-server --version
      redis-cli ping

2. 检查连接配置：

   .. code-block:: bash

      export DEVA_REDIS_URL=redis://localhost:6379/0

版本兼容性
----------

Python 版本支持
~~~~~~~~~~~~~~

+----------+------------+------------+
| Deva 版本 | Python 3.8 | Python 3.9+ |
+==========+============+============+
| 1.x      | ✅        | ✅         |
+----------+------------+------------+

依赖版本要求
~~~~~~~~~~~~

+----------+-------------+-------------+
| 依赖包    | 最低版本     | 推荐版本     |
+==========+=============+=============+
| redis    | 4.0.0       | 5.0.0+      |
+----------+-------------+-------------+
| whoosh   | 2.7.4       | 2.7.4       |
+----------+-------------+-------------+
| jieba    | 0.42.1      | 0.60.0+     |
+----------+-------------+-------------+


升级指南
--------

从旧版本升级：

.. code-block:: bash

   pip install --upgrade deva

查看变更日志：

.. code-block:: bash

   pip show deva

回滚到指定版本：

.. code-block:: bash

   pip install deva==0.9.0


下一步
------

安装完成后，继续：

- :doc:`quickstart` - 快速开始指南
- :doc:`manual_cn` - 使用手册
- :doc:`usage` - 使用指南
