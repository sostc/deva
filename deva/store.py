from tornado import gen
from .utils.sqlitedict import SqliteDict
from .core import Stream, get_io_loop
from .pipe import passed, first
import os
import time

"""
SqliteDict 和 DBStream 的关系说明:

1. 底层存储:
- SqliteDict 是 DBStream 的底层存储实现
- 它基于 SQLite 数据库实现了一个类似字典的键值存储
- 提供了基本的 CRUD 操作接口

2. 功能扩展:
- DBStream 在 SqliteDict 的基础上进行了功能扩展
- 增加了流式处理能力，支持数据流式写入和读取
- 提供了时间序列、容量限制、数据回放等高级功能

3. 使用方式:
- SqliteDict 提供了基础的键值存储接口
- DBStream 提供了更高级的流式操作接口
- 用户可以直接使用 DBStream 的流式 API，而无需直接操作 SqliteDict

4. 性能优化:
- DBStream 在 SqliteDict 的基础上进行了性能优化
- 支持批量写入、异步操作等特性
- 提供了缓存机制来提高数据访问效率

5. 关系总结:
- SqliteDict 是 DBStream 的核心存储引擎
- DBStream 是 SqliteDict 的功能扩展和高级封装
- 两者配合使用，既提供了基础的存储能力，又支持流式处理
"""

@Stream.register_api()
class DBStream(Stream):
    """基于 SQLite 的持久化数据流存储类

    该类将流式处理与 SQLite 数据库存储相结合，提供了高效、灵活的数据存储和处理能力。

    主要特性：
    - 持久化存储：基于 SQLite 实现键值对的持久化存储
    - 流式处理：支持数据流式写入和读取
    - 自动时间戳：单值存储时自动使用时间戳作为键
    - 容量管理：可设置最大存储容量，自动清理旧数据
    - 时间序列：支持基于时间范围的数据查询和回放
    - 异步支持：支持异步函数返回的数据流式写入

    参数：
        name (str): 表名，默认为 'default'
        filename (str): 数据库文件路径，默认在 ~/.deva/nb.sqlite
        maxsize (int): 最大存储记录数，默认无限制
        log (Stream): 日志流对象，默认为 passed

    示例：
        # 创建数据库
        db = DBStream('my_table', './data/mydb')

        # 基础操作
        db['key'] = 'value'  # 写入数据
        value = db['key']    # 读取数据

        # 流式写入
        123 >> db            # 单值写入，自动使用时间戳作为键
        ('key', 'value') >> db  # 元组写入
        {'key': 'value'} >> db  # 字典写入

        # 时间序列查询
        start = '2023-01-01 00:00:00'
        end = '2023-01-01 23:59:59'
        for key in db[start:end]:
            print(db[key])

        # 数据回放
        db.replay(start='2023-01-01 00:00:00', interval=1)  # 每秒回放一条数据
    """

    def __init__(self, name='default', filename=None,
                 maxsize=None, log=passed, **kwargs):
        """初始化数据库流对象

        Args:
            name (str): 表名，默认为 'default'
            filename (str): 数据库文件路径，默认在 ~/.deva/nb.sqlite
            maxsize (int): 最大存储记录数，默认无限制
            log (Stream): 日志流对象，默认为 passed
            **kwargs: 其他传递给 SqliteDict 的参数
        """
        # 初始化日志流和表名
        self.log = log
        self.tablename = name
        self.name = name
        self.maxsize = maxsize

        super(DBStream, self).__init__()
        self.name = name

        # 处理文件路径
        if not filename:
            try:
                if not os.path.exists(os.path.expanduser('~/.deva/')):
                    os.makedirs(os.path.expanduser('~/.deva/'))
                self.filename = os.path.expanduser('~/.deva/nb.sqlite')
            except Exception as e:
                print(e, 'create dbfile nb.sqlite in curdir')
                self.filename = 'nb.sqlite'
        else:
            self.filename = filename + '.sqlite'

        # 初始化 SQLite 字典
        self.db = SqliteDict(
            self.filename,
            tablename=self.tablename,
            autocommit=True,
            **kwargs)

        # 绑定常用方法
        self.keys = self.db.keys
        self.values = self.db.values
        self.items = self.db.items
        self.get = self.db.get
        self.clear = self.db.clear
        self._check_size_limit()

    @property
    def tables(self):
        """获取所有表名"""
        return self.db.tables

    def emit(self, x, asynchronous=False):
        """发送数据到流中

        Args:
            x: 要发送的数据，可以是普通数据或异步可等待对象
            asynchronous (bool): 是否异步处理，默认为 False
        """
        if isinstance(x, gen.Awaitable):
            futs = gen.convert_yielded(x)
            if not self.loop:
                self._set_asynchronous(False)
            if self.loop is None and self.asynchronous is not None:
                self._set_loop(get_io_loop(self.asynchronous))
            self.loop.add_future(futs, lambda x: self.update(x.result()))
        else:
            self.update(x)
    
    def _check_size_limit(self):
        """检查并维护最大容量限制"""
        if self.maxsize:
            while len(self.db) > self.maxsize:
                self.db.popitem()

    def update(self, x):
        """更新数据库内容

        Args:
            x: 要更新的数据，可以是字典、元组或单个值
        """
        x >> self.log

        if isinstance(x, dict):
            self.db.update(x)
        elif isinstance(x, tuple):
            key, value = x
            self.db.update({key: value})
        else:
            key = time.time()
            value = x
            self.db.update({key: value})

        self._check_size_limit()
        self._emit(x)

    def __slice__(self, start=None, stop=None):
        """时间切片操作

        Args:
            start (str): 开始时间，格式为 'YYYY-MM-DD HH:MM:SS'
            stop (str): 结束时间，格式为 'YYYY-MM-DD HH:MM:SS'

        Yields:
            str: 在时间范围内的键
        """
        from datetime import datetime

        start = datetime.fromisoformat(start).timestamp() if start else float(self.keys() | first)
        stop = datetime.fromisoformat(stop).timestamp() if stop else time.time()

        for key in self.keys():
            if start < float(key) < stop:
                yield key

    @gen.coroutine
    def replay(self, start=None, end=None, interval=None):
        """时序数据回放

        Args:
            start (str): 开始时间，格式为 'YYYY-MM-DD HH:MM:SS'
            end (str): 结束时间，格式为 'YYYY-MM-DD HH:MM:SS'
            interval (float): 回放间隔时间，单位为秒

        Yields:
            按时间顺序回放的数据
        """
        for key in self[start:end]:
            self._emit(self[key])
            yield gen.moment if not interval else gen.sleep(interval)

    def __len__(self):
        """获取数据库记录数"""
        return self.db.__len__()

    def __getitem__(self, item):
        """获取数据

        Args:
            item: 键值或时间切片
        """
        if isinstance(item, slice):
            return self.__slice__(item.start, item.stop)
        return self.db.__getitem__(item)

    def __setitem__(self, key, value):
        """设置数据"""
        self.db.__setitem__(key, value)
        self._check_size_limit()
        return self

    def __delitem__(self, x):
        """删除数据"""
        return self.db.__delitem__(x)

    def __contains__(self, x):
        """检查键是否存在"""
        return self.db.__contains__(x)

    def __iter__(self):
        """迭代器"""
        return self.db.__iter__()