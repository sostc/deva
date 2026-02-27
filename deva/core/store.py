from tornado import gen
from .utils.sqlitedict import SqliteDict
from .core import Stream
from .utils.ioloop import get_io_loop
from .pipe import passed
from bisect import bisect_left, bisect_right
import logging
import os
import time
import threading

logger = logging.getLogger(__name__)

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
                 maxsize=None, log=passed, key_mode='explicit',
                 time_dict_policy='reject', **kwargs):
        """初始化数据库流对象

        Args:
            name (str): 表名，默认为 'default'
            filename (str): 数据库文件路径，默认在 ~/.deva/nb.sqlite
            maxsize (int): 最大存储记录数，默认无限制
            log (Stream): 日志流对象，默认为 passed
            key_mode (str): 键模式，'explicit' 或 'time'。
                - explicit: dict 输入视为批量 upsert（默认，兼容旧行为）
                - time: 事件流模式，普通值按时间戳写入
            time_dict_policy (str): 当 key_mode='time' 且输入为 dict 时的策略：
                - reject: 抛出 TypeError（默认，避免误写）
                - append: 将整个 dict 作为一条事件按时间戳写入
            **kwargs: 其他传递给 SqliteDict 的参数
        """
        # 初始化日志流和表名
        self.log = log
        self.tablename = name
        self.name = name
        self.maxsize = maxsize
        self.key_mode = key_mode
        self.time_dict_policy = time_dict_policy
        if self.key_mode not in {'explicit', 'time'}:
            raise ValueError("key_mode must be 'explicit' or 'time'")
        if self.time_dict_policy not in {'reject', 'append'}:
            raise ValueError("time_dict_policy must be 'reject' or 'append'")

        super(DBStream, self).__init__()
        self.name = name
        self._time_index = []
        self._time_index_ts = []
        self._time_index_dirty = True
        self._time_index_lock = threading.RLock()

        if not filename:
            db_path = os.getenv("DEVA_DB_PATH", "~/.deva/nb.sqlite")
            
            try:
                expanded_path = os.path.expanduser(db_path)
                db_dir = os.path.dirname(expanded_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                self.filename = expanded_path
            except Exception as e:
                logger.warning("%s create dbfile nb.sqlite in curdir", e)
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
        if not self.maxsize:
            return
        excess = len(self.db) - self.maxsize
        if excess <= 0:
            return

        self._rebuild_time_index()
        with self._time_index_lock:
            evict_keys = [key for _, key in self._time_index[:excess]]
            evicted = set()
            for key in evict_keys:
                if key in self.db:
                    del self.db[key]
                    evicted.add(key)

            remain = excess - len(evicted)
            if remain > 0:
                fallback_keys = [k for k in self.db.keys() if k not in evicted]
                fallback_keys.sort(key=lambda x: str(x))
                for key in fallback_keys[:remain]:
                    del self.db[key]
        self._mark_time_index_dirty()

    def update(self, x):
        """更新数据库内容

        Args:
            x: 要更新的数据，可以是字典、元组或单个值
        """
        try:
            x >> self.log
        except Exception:
            if callable(self.log):
                self.log(x)

        if isinstance(x, dict):
            if self.key_mode == 'explicit':
                self.bulk_update(x)
            elif self.time_dict_policy == 'append':
                self.append(x)
            else:
                raise TypeError(
                    "dict input is not allowed in key_mode='time'. "
                    "Use append(dict) or upsert(key, value)."
                )
        elif isinstance(x, tuple):
            key, value = x
            self.upsert(key, value)
        else:
            self.append(x)

        self._emit(x)

    def _to_float_timestamp(self, key):
        try:
            return float(key)
        except (TypeError, ValueError):
            return None

    def _mark_time_index_dirty(self):
        with self._time_index_lock:
            self._time_index_dirty = True

    def _rebuild_time_index(self):
        with self._time_index_lock:
            if not self._time_index_dirty:
                return
            data = []
            for key in self.db.keys():
                ts = self._to_float_timestamp(key)
                if ts is not None:
                    data.append((ts, key))
            data.sort(key=lambda x: x[0])
            self._time_index = data
            self._time_index_ts = [ts for ts, _ in data]
            self._time_index_dirty = False

    def append(self, value, key=None):
        """将一条事件按时间戳键写入。"""
        store_key = time.time() if key is None else key
        self.db.update({store_key: value})
        self._mark_time_index_dirty()
        self._check_size_limit()
        return store_key

    def upsert(self, key, value):
        """按显式键写入/覆盖一条记录。"""
        self.db.update({key: value})
        self._mark_time_index_dirty()
        self._check_size_limit()
        return key

    def bulk_update(self, mapping):
        """批量写入映射。"""
        self.db.update(mapping)
        self._mark_time_index_dirty()
        self._check_size_limit()
        return self

    def __slice__(self, start=None, stop=None):
        """时间切片操作

        Args:
            start (str): 开始时间，格式为 'YYYY-MM-DD HH:MM:SS'
            stop (str): 结束时间，格式为 'YYYY-MM-DD HH:MM:SS'

        Yields:
            str: 在时间范围内的键
        """
        from datetime import datetime

        self._rebuild_time_index()
        with self._time_index_lock:
            if not self._time_index:
                return
            if start:
                start = datetime.fromisoformat(start).timestamp()
            else:
                start = self._time_index_ts[0]

            stop = datetime.fromisoformat(stop).timestamp() if stop else time.time()
            left = bisect_right(self._time_index_ts, start)
            right = bisect_left(self._time_index_ts, stop)
            for ts, key in self._time_index[left:right]:
                if start < ts < stop:
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
        self.upsert(key, value)
        return self

    def __delitem__(self, x):
        """删除数据"""
        result = self.db.__delitem__(x)
        self._mark_time_index_dirty()
        return result

    def __contains__(self, x):
        """检查键是否存在"""
        return self.db.__contains__(x)

    def __iter__(self):
        """迭代器"""
        return self.db.__iter__()

    def clear(self):
        """清空当前表。"""
        result = self.db.clear()
        self._mark_time_index_dirty()
        return result
