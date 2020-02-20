from .pipe import *

import pkg_resources
import pandas as pd
from .streamz.sqlitedict import SqliteDict
import datetime
import moment


class HDFStore(object):
    """
    用作dataframe存储，
    set：key value方式存储dataframe
    daily_set：将当前日期变形后作为key存储
    daily_get：查询当天的数据
    """

    def __init__(self, fname='_hdfstore.h5'):
        self.fname = pkg_resources.resource_filename(__name__, fname)

    def daily_set(self, path, value, date=None):
        """df,'/stock/tal',2020-01-11'"""
        key = path+'/ts'+datetime.date.today().strftime('%Y%m%d')
        return self.set(key, value)

    def set(self, key, value, append=False):
        """df,'/stock/tal',2020-01-11'#append true时df append"""
        with pd.HDFStore(self.fname, 'a') as hs:
            hs.put(key, value, format='table', append=append)
            # hs[key]=df
        return self
        #

    def daily_get(self, key, date=None):
        date = today()
        key = key+'/ts'+date.replace('-', '')
        return self.get(key)

    def get(self, key):
        """df,'/stock/tal',2020-01-11'"""
        with pd.HDFStore(self.fname, 'r') as hs:
            return hs[key]

    def keys(self,):
        with pd.HDFStore(self.fname, 'r') as hs:
            return hs.keys()

    def walk(self, group):
        with pd.HDFStore(self.fname, 'r') as hs:
            return list(hs.walk(group))


# @Stream.register_api()
class ODBStream(object):
    """
    所有输入都会被作为字典在sqlite中做持久存储，若指定tablename，则将所有数据单独存储一个table。使用方式和字典一样
    输入是元组时，第一个值作为key，第二个作为value。
    输入时一个值时，默认时间作为key，moment.unix(key)可还原为moment时间
    输入是字典时，更新字典
    maxsize保持定长字典
    stream_name是表名
    fname是文件路径
    """

    def __init__(self, tablename='default', fname='_dictstream', maxsize=None, log=passed, **kwargs):
        self.log = log
        self.tablename = tablename
        self.maxsize = maxsize

        super(ODBStream, self).__init__()
        if fname == '_dictstream':
            self.fname = pkg_resources.resource_filename(__name__, fname+'.sqlite')
        else:
            self.fname = fname+'.sqlite'

        # self.fname = fname+'.sqlite'
        self.db = SqliteDict(
            self.fname,
            tablename=self.tablename,
            autocommit=True)

        self.db['tablename'] = self.tablename

        self.keys = self.db.keys
        self.values = self.db.values
        self.items = self.db.items
        self.get = self.db.get
        self.clear = self.db.clear
        self._check_size_limit()

    def __rrshift__(self, x):
        self._to_store(x)
        return x

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


class ODBNamespace(dict):
    def create_table(self, tablename='default', **kwargs):
        try:
            return self[tablename]
        except KeyError:
            return self.setdefault(
                tablename,
                ODBStream(tablename=tablename, **kwargs)
            )


odbnamespace = ODBNamespace()


def NB(*args, **kwargs):
    """创建命名的数据库
    NB(tablename,fname)
    tablename:流名，底层是表名
    fname，存储文件路径名字
    """
    return odbnamespace.create_table(*args, **kwargs)


NODB = NB

if __name__ == '__main__':
    hs = HDFStore()
    hs.daily_set(pd.DataFrame(), '/test/a')
    # hs.daily_read('/test/a')
    hs.daily_get('/test/a')
    hs.get('/test/a/ts20200114')
