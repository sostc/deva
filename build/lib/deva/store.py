from tornado import gen
"""
    是一个流，也是一个自动持久化字典对象，支持定长。

    """

from .utils.sqlitedict import SqliteDict
from .core import Stream
from .pipe import passed
import os
import time


@Stream.register_api()
class DBStream(Stream):
    """对象数据库流.

    将对象数据库包装成流对象,所有输入都会被作为字典在sqlite中做持久存储，若指定tablename，则将所有数据单独存储一个table。
    使用方式和字典一样

    入流参数::
        :tuple: 输入是元组时，第一个值作为key，第二个作为value。
        :value: 输入时一个值时，默认时间作为key，moment.unix(key)可还原为moment时间
        :dict: 输入是字典时，更新字典

    Examples::

        db = DBStream('table1','./dbfile')

        123>>db

        ('key','vlaue')>>db

        {'key':'value'}>>db

        db|ls == db.keys()|ls

        db.values()|ls

        db.items()|ls

        assert db['key'] == 'value'

        del db['key']

        #时间序列的数据的时间切片
        start='2020-03-23 10:20:35'
        db[start:end]

        #定长表
        tmp = NB(name='tmp',maxsize=10)

        #删除表
        tmp.db.drop()

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
        self.log = log
        self.tablename = name
        self.name = name
        self.maxsize = maxsize

        super(DBStream, self).__init__()
        self.name = name
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

    def __slice__(self, start='2020-03-23 00:28:34',
                  stop='2020-03-23 00:28:35'):
        from datetime import datetime

        if start:
            start = datetime.fromisoformat(start).timestamp()
        else:
            start = float(self.keys()[0])
        stop = datetime.fromisoformat(stop).timestamp()\
            if stop else time.time()

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
        assert X('a').data  == [1,2,3]

        'abc' | X('a')
        assert X('a').data  == 'abc'
    """

    def __init__(self, name):
        self.name = name

    def __rrshift__(self, ref):
        self.data = ref
        return ref

    def __ror__(self, ref):
        self.data = ref
        return ref
