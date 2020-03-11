"""
    是一个流，也是一个自动持久化字典对象，支持定长。

    """

from .pipe import *
from .utils.sqlitedict import SqliteDict
from .core import Stream
import pkg_resources
import moment


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

    """

    def __init__(self,  name='default', fname='nb', maxsize=None, log=passed, **kwargs):
        """构建数据库流对象.

        Args:
            **kwargs: 流的其他参数
            name: 表名 (default: {'default'})
            fname: 存储的文件名 (default: {'nb'})
            maxsize: 数据表长度 (default: {None})
            log: 日志流 (default: {passed})
        """
        self.log = log
        self.tablename = name
        self.name = name
        self.maxsize = maxsize

        super(DBStream, self).__init__()
        self.name = name
        if fname == 'nb':
            self.fname = pkg_resources.resource_filename(__name__, fname+'.sqlite')
        else:
            self.fname = fname+'.sqlite'

        # self.fname = fname+'.sqlite'
        self.db = SqliteDict(
            self.fname,
            tablename=self.tablename,
            autocommit=True)

        # self.db['tablename'] = self.tablename

        self.keys = self.db.keys
        self.values = self.db.values
        self.items = self.db.items
        self.get = self.db.get
        self.clear = self.db.clear
        self.get_tablenames = self.db.get_tablenames
        self._check_size_limit()

    def emit(self, x, asynchronous=False):
        self._to_store(x)
        return super().emit(x, asynchronous=asynchronous)

    def _check_size_limit(self):
        if self.maxsize is not None:
            while len(self.db) > self.maxsize:
                self.db.popitem()

    def _to_store(self, x):
        x >> self.log
        if isinstance(x, dict):
            self.db.update(x)
        elif isinstance(x, tuple):
            key, value = x
            self.db.update({key: value})
        else:
            key = moment.now().epoch()
            # moment.unix(now.epoch())
            value = x
            self.db.update({key: value})

        self._check_size_limit()

    def __len__(self,):
        return self.db.__len__()

    def __getitem__(self, x):
        return self.db.__getitem__(x)

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
