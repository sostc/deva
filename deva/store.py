from tornado import gen
from .utils.sqlitedict import SqliteDict
from .core import Stream
from .pipe import passed, first
import os
import time


@Stream.register_api()
class DBStream(Stream):
    """基于 SQLite 的持久化数据流存储类
    
    功能特性:
    1. 持久化存储: 基于 SQLite 实现键值对的持久化存储
    2. 流式操作: 支持数据流式处理和传输
    3. 自动时间戳: 单值存储时自动使用时间戳作为键
    4. 容量限制: 可设置最大存储容量，自动清理旧数据
    5. 时间切片: 支持基于时间范围的数据查询
    
    主要用法:
    1. 基础存储:
        db = DBStream('table_name', './data/mydb')  # 创建数据库
        db['key'] = 'value'                         # 直接赋值
        value = db['key']                           # 直接读取
        
    2. 流式写入:
        123 >> db                    # 单值写入(自动使用时间戳作为键)
        ('key', 'value') >> db      # 元组写入
        {'key': 'value'} >> db      # 字典写入
        
    3. 遍历操作:
        db.keys() | ls              # 查看所有键
        db.values() | ls            # 查看所有值
        db.items() | ls             # 查看所有键值对
        
    4. 时间序列:
        # 查询特定时间范围的数据
        start = '2020-03-23 10:20:35'
        end = '2020-03-23 11:20:35'
        for key in db[start:end]:
            print(db[key])
            
    5. 容量限制:
        # 创建最多存储10条记录的数据表
        db = DBStream('cache', maxsize=10)
        
    6. 数据回放:
        # 按时间顺序回放数据
        db.replay(start='2020-03-23 10:20:35', interval=1)  # 每秒回放一条
        
    参数说明:
        name (str): 表名，默认为 'default'
        filename (str): 数据库文件路径，默认在 ~/.deva/nb.sqlite
        maxsize (int): 最大存储记录数，默认无限制
        log (Stream): 日志流对象，默认为 passed
    """

    def __init__(self, name='default', filename=None,
                 maxsize=None, log=passed, **kwargs):
        """构建数据库流对象.

        Args:
            **kwargs: 流的其他参数
            name: 表名 (default: {'default'})
            filename: 存储的文件名 (default: {'nb'})
            maxsize: 数据表长度 (default: {None})
            log: 日志流 (default: {passed})
        """
        # 初始化日志流和表名
        self.log = log
        self.tablename = name
        self.name = name
        # 设置表的最大容量限制
        self.maxsize = maxsize

        super(DBStream, self).__init__()
        self.name = name
        if not filename:
            try:
                # 如果未指定文件名，默认在用户目录下创建 .deva/nb.sqlite
                if not os.path.exists(os.path.expanduser('~/.deva/')):
                    os.makedirs(os.path.expanduser('~/.deva/'))
                self.filename = os.path.expanduser('~/.deva/nb.sqlite')
            except Exception as e:
                # 如果无法在用户目录创建，则在当前目录创建
                print(e, 'create dbfile nb.sqlite in curdir')
                self.filename = 'nb.sqlite'

        else:
            self.filename = filename + '.sqlite'

        # 初始化 SQLite 字典，启用自动提交
        self.db = SqliteDict(
            self.filename,
            tablename=self.tablename,
            autocommit=True,
            **kwargs)

        self.keys = self.db.keys
        self.values = self.db.values
        self.items = self.db.items
        self.get = self.db.get
        self.clear = self.db.clear
        self.tables = self.db.tables
        self._check_size_limit()

    def emit(self, x, asynchronous=False):
        self.update(x)
        # return super().emit(x, asynchronous=asynchronous)

    def _check_size_limit(self):
        if self.maxsize:
            while len(self.db) > self.maxsize:
                self.db.popitem()

    def update(self, x):
        # 记录日志
        x >> self.log
        
        # 根据输入类型不同进行不同的处理
        if isinstance(x, dict):
            # 如果是字典，直接更新
            self.db.update(x)
        elif isinstance(x, tuple):
            # 如果是元组，将第一个元素作为键，第二个作为值
            key, value = x
            self.db.update({key: value})
        else:
            # 其他情况使用当前时间戳作为键
            key = time.time()
            value = x
            self.db.update({key: value})

        # 检查并维护最大容量限制
        self._check_size_limit()
        self._emit(x)

    def __slice__(self, start='2020-03-23 00:28:34',
                  stop='2020-03-23 00:28:35'):
        # 时间切片操作，用于查询特定时间范围内的数据
        from datetime import datetime

        # 如果没有指定开始时间，使用最早的记录时间
        if start:
            start = datetime.fromisoformat(start).timestamp()
        else:
            start = float(self.keys() | first)
        # 如果没有指定结束时间，使用当前时间
        stop = datetime.fromisoformat(stop).timestamp()\
            if stop else time.time()

        # 遍历所有在时间范围内的键
        for key in self.keys():
            if start < float(key) < stop:
                yield key

    @gen.coroutine
    def replay(self, start=None, end=None, interval=None):
        """ts db data replay.

        时序数据库数据回放，仅限于key是时间的数据

        Args:
            start: 开始时间 (default: {None}),start='2020-03-23 10:20:35'
            end: 结束时间 (default: {None})
            interval: 回放间隔 (default: {None})

        Yields:
            [description]
            [type]

        Examples::

            db = NB('ts_test')
            for i in range(100):
                i >> db
            db>>log
            db.replay()

            [2020-03-23 06:38:16.521248] INFO: log: 2
            [2020-03-23 06:38:17.529558] INFO: log: 3
            [2020-03-23 06:38:18.533068] INFO: log: 4
            [2020-03-23 06:38:19.538777] INFO: log: 5


        """
        for key in self[start:end]:
            self._emit(self[key])
            yield gen.moment if not interval else gen.sleep(interval)

    def __len__(self,):
        return self.db.__len__()

    def __getitem__(self, item):
        if isinstance(item, slice):
            # 时间为key的时间切片
            return self.__slice__(item.start, item.stop)
        else:
            return self.db.__getitem__(item)

    def __setitem__(self, key, value):
        self.db.__setitem__(key, value)
        self._check_size_limit()
        return self

    def __delitem__(self, x):
        return self.db.__delitem__(x)

    def __contains__(self, x):
        return self.db.__contains__(x)

    def __iter__(self,):
        return self.db.__iter__()


class X():
    """存储变量 .

    Examples
    --------
        [1,2,3]>>X('a')
        assert a  == [1,2,3]

        'abc' | X('a')
        assert a  == 'abc'
    """

    def __init__(self, name, scope=globals):
        self.scope = scope
        self.name = name
        self.scope()[self.name] = ''
        # print(self.scope()[self.name]*2)

    def __rrshift__(self, ref):
        self.scope()[self.name] = ref
        return ref

    def __ror__(self, ref):
        self.scope()[self.name] = ref
        return ref
