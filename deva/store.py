from .pipe import *

import pkg_resources
import pandas as pd
import datetime


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


if __name__ == '__main__':
    hs = HDFStore()
    hs.daily_set(pd.DataFrame(), '/test/a')
    # hs.daily_read('/test/a')
    hs.daily_get('/test/a')
    hs.get('/test/a/ts20200114')
