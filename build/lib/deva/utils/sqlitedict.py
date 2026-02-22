#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This code is distributed under the terms and conditions
# from the Apache License, Version 2.0
#
# http://opensource.org/licenses/apache2.0.php
#
# This code was inspired by:
#  * http://code.activestate.com/recipes/576638-draft-for-an-sqlite3-based-dbm/
#  * http://code.activestate.com/recipes/526618/

"""
A lightweight wrapper around Python's sqlite3 database, with a dict-like interface
and multi-thread access support::

>>> mydict = SqliteDict('some.db', autocommit=True) # the mapping will be persisted to file `some.db`
>>> mydict['some_key'] = any_picklable_object
>>> print mydict['some_key']
>>> print len(mydict) # etc... all dict functions work

Pickle is used internally to serialize the values. Keys are strings.

If you don't use autocommit (default is no autocommit for performance), then
don't forget to call `mydict.commit()` when done with a transaction.

"""

import sqlite3
import os
import sys
import tempfile
import random
import logging
import traceback
import dill

from threading import Thread

try:
    __version__ = __import__('pkg_resources').get_distribution('sqlitedict').version
except:
    __version__ = '?'

major_version = sys.version_info[0]
if major_version < 3:  # py <= 2.x
    if sys.version_info[1] < 5:  # py <= 2.4
        raise ImportError(
            "sqlitedict requires python 2.5 or higher (python 3.3 or higher supported)")

    # necessary to use exec()_ as this would be a SyntaxError in python3.
    # this is an exact port of six.reraise():
    def exec_(_code_, _globs_=None, _locs_=None):
        """Execute code in a namespace."""
        if _globs_ is None:
            frame = sys._getframe(1)
            _globs_ = frame.f_globals
            if _locs_ is None:
                _locs_ = frame.f_locals
            del frame
        elif _locs_ is None:
            _locs_ = _globs_
        exec("""exec _code_ in _globs_, _locs_""")

    exec_("def reraise(tp, value, tb=None):\n"
          "    raise tp, value, tb\n")
else:
    def reraise(tp, value, tb=None):
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value

try:
    from cPickle import dumps, loads, HIGHEST_PROTOCOL as PICKLE_PROTOCOL # type: ignore
except ImportError:
    from pickle import dumps, loads, HIGHEST_PROTOCOL as PICKLE_PROTOCOL

# some Python 3 vs 2 imports
try:
    from collections import UserDict as DictClass
except ImportError:
    from UserDict import DictMixin as DictClass # type: ignore

try:
    from queue import Queue
except ImportError:
    from Queue import Queue # type: ignore


logger = logging.getLogger(__name__)


def open(*args, **kwargs):
    """See documentation of the SqliteDict class."""
    return SqliteDict(*args, **kwargs)


def encode(obj):
    """Serialize an object using pickle to a binary format accepted by SQLite."""
    try:
        return dill.dumps(obj)
    except:
        return sqlite3.Binary(dumps(obj, protocol=PICKLE_PROTOCOL))


def decode(obj):
    """Deserialize objects retrieved from SQLite."""
    try:
        return dill.loads(obj)
    except:
        return loads(bytes(obj))


class SqliteDict(DictClass):
    """基于SQLite的线程安全字典实现"""
    VALID_FLAGS = ['c', 'r', 'w', 'n']  # 有效的文件打开模式

    def __init__(self, filename=None, tablename='unnamed', flag='c',
                 autocommit=False, journal_mode="DELETE", encode=encode, decode=decode):
        """
        初始化一个线程安全的SQLite字典
        
        参数:
            filename: 数据库文件路径，如果为None则使用临时文件
            tablename: 表名，默认为'unnamed'
            flag: 打开模式，可选值：
                'c': 默认模式，读写模式，如果数据库/表不存在则创建
                'w': 读写模式，但会先清空表内容
                'r': 只读模式
                'n': 创建新数据库（会删除所有表，不仅仅是当前表）
            autocommit: 是否自动提交，如果为True则每次操作后自动提交
            journal_mode: SQLite日志模式，建议使用"DELETE"，遇到I/O问题时可以设为"OFF"
            encode: 自定义序列化函数，默认为pickle
            decode: 自定义反序列化函数，默认为pickle
        """
        self.in_temp = filename is None
        if self.in_temp:
            randpart = hex(random.randint(0, 0xffffff))[2:]
            filename = os.path.join(tempfile.gettempdir(), 'sqldict' + randpart)

        if flag not in SqliteDict.VALID_FLAGS:
            raise RuntimeError("无效的flag参数: %s" % flag)
        self.flag = flag

        if flag == 'n':
            if os.path.exists(filename):
                os.remove(filename)

        dirname = os.path.dirname(filename)
        if dirname:
            if not os.path.exists(dirname):
                raise RuntimeError('错误！目录不存在: %s' % dirname)

        self.filename = filename
        if '"' in tablename:
            raise ValueError('无效的表名 %r' % tablename)
        self.tablename = tablename
        self.autocommit = autocommit
        self.journal_mode = journal_mode
        self.encode = encode
        self.decode = decode

        logger.info("打开SQLite表 %r 在 %s" % (tablename, filename))
        MAKE_TABLE = 'CREATE TABLE IF NOT EXISTS "%s" (key TEXT PRIMARY KEY, value BLOB)' % self.tablename
        self.conn = self._new_conn()
        self.conn.execute(MAKE_TABLE)
        self.conn.commit()
        if flag == 'w':
            self.clear()

    def _new_conn(self):
        """创建新的数据库连接"""
        return SqliteMultithread(self.filename, autocommit=self.autocommit, journal_mode=self.journal_mode)

    def __enter__(self):
        """上下文管理器入口"""
        if not hasattr(self, 'conn') or self.conn is None:
            self.conn = self._new_conn()
        return self

    def __exit__(self, *exc_info):
        """上下文管理器退出"""
        self.close()

    def __str__(self):
        """返回字符串表示"""
        return "SqliteDict(%s)" % (self.filename)

    def __repr__(self):
        """返回对象的正式表示"""
        return str(self)

    def __len__(self):
        """返回字典中键值对的数量"""
        GET_LEN = 'SELECT COUNT(*) FROM "%s"' % self.tablename
        rows = self.conn.select_one(GET_LEN)[0]
        return rows if rows is not None else 0

    def __bool__(self):
        """判断字典是否为空"""
        GET_MAX = 'SELECT MAX(ROWID) FROM "%s"' % self.tablename
        m = self.conn.select_one(GET_MAX)[0]
        return True if m is not None else False

    def getrowid(self, key):
        """获取指定键对应的行ID"""
        GET_ITEM = 'SELECT rowid FROM "%s" WHERE key = ?' % self.tablename
        item = self.conn.select_one(GET_ITEM, (key,))
        if item is None:
            raise KeyError(key)
        return item[0]

    def iterkeys(self):
        """迭代所有键"""
        GET_KEYS = 'SELECT key FROM "%s" ORDER BY rowid' % self.tablename
        for key in self.conn.select(GET_KEYS):
            yield key[0]

    def itervalues(self):
        """迭代所有值"""
        GET_VALUES = 'SELECT value FROM "%s" ORDER BY rowid' % self.tablename
        for value in self.conn.select(GET_VALUES):
            yield self.decode(value[0])

    def iteritems(self):
        """迭代所有键值对"""
        GET_ITEMS = 'SELECT key, value FROM "%s" ORDER BY rowid' % self.tablename
        for key, value in self.conn.select(GET_ITEMS):
            yield key, self.decode(value)

    def keys(self):
        """返回所有键"""
        return self.iterkeys() if major_version > 2 else list(self.iterkeys())

    def values(self):
        """返回所有值"""
        return self.itervalues() if major_version > 2 else list(self.itervalues())

    def items(self):
        """返回所有键值对"""
        return self.iteritems() if major_version > 2 else list(self.iteritems())

    def __contains__(self, key):
        """判断键是否存在"""
        HAS_ITEM = 'SELECT 1 FROM "%s" WHERE key = ?' % self.tablename
        return self.conn.select_one(HAS_ITEM, (key,)) is not None

    def __getitem__(self, key):
        """获取指定键的值"""
        GET_ITEM = 'SELECT value FROM "%s" WHERE key = ?' % self.tablename
        item = self.conn.select_one(GET_ITEM, (key,))
        if item is None:
            raise KeyError(key)
        return self.decode(item[0])

    def __setitem__(self, key, value):
        """设置键值对"""
        if self.flag == 'r':
            raise RuntimeError('拒绝写入只读的SqliteDict')

        ADD_ITEM = 'REPLACE INTO "%s" (key, value) VALUES (?,?)' % self.tablename
        return self.conn.execute(ADD_ITEM, (key, self.encode(value)))

    def __delitem__(self, key):
        """删除指定键"""
        if self.flag == 'r':
            raise RuntimeError('拒绝删除只读的SqliteDict')

        if key not in self:
            raise KeyError(key)
        DEL_ITEM = 'DELETE FROM "%s" WHERE key = ?' % self.tablename
        self.conn.execute(DEL_ITEM, (key,))

    def update(self, items=(), **kwds):
        """批量更新键值对"""
        if self.flag == 'r':
            raise RuntimeError('拒绝更新只读的SqliteDict')

        try:
            items = items.items()
        except AttributeError:
            pass
        items = [(k, self.encode(v)) for k, v in items]

        UPDATE_ITEMS = 'REPLACE INTO "%s" (key, value) VALUES (?, ?)' % self.tablename
        self.conn.executemany(UPDATE_ITEMS, items)
        if kwds:
            self.update(kwds)

    def __iter__(self):
        """返回键的迭代器"""
        return self.iterkeys()

    def clear(self):
        """清空整个表"""
        if self.flag == 'r':
            raise RuntimeError('拒绝清空只读的SqliteDict')

        CLEAR_ALL = 'DELETE FROM "%s";' % self.tablename
        self.conn.commit()
        self.conn.execute(CLEAR_ALL)
        self.conn.commit()

    def drop(self):
        """删除整个表"""
        if self.flag == 'r':
            raise RuntimeError('拒绝删除只读的SqliteDict')

        DROP_TABLE = 'DROP TABLE "%s";' % self.tablename
        self.conn.commit()
        self.conn.execute(DROP_TABLE)
        self.conn.commit()

    @property
    def tables(self):
        """获取数据库中所有表的名称"""
        if not os.path.isfile(self.filename):
            raise IOError('文件 %s 不存在' % (self.filename))
        GET_TABLENAMES = 'SELECT name FROM sqlite_master WHERE type="table"'
        with sqlite3.connect(self.filename) as conn:
            cursor = conn.execute(GET_TABLENAMES)
            res = cursor.fetchall()

        return [name[0] for name in res]

    def commit(self, blocking=True):
        """
        提交所有更改到磁盘
        
        参数:
            blocking: 如果为False，提交命令会进入队列但不保证立即持久化
        """
        if self.conn is not None:
            self.conn.commit(blocking)

    sync = commit

    def close(self, do_log=True, force=False):
        """关闭数据库连接"""
        if do_log:
            logger.debug("关闭 %s" % self)
        if hasattr(self, 'conn') and self.conn is not None:
            if self.conn.autocommit and not force:
                self.conn.commit(blocking=True)
            self.conn.close(force=force)
            self.conn = None
        if self.in_temp:
            try:
                os.remove(self.filename)
            except:
                pass

    def terminate(self):
        """删除底层数据库文件，请谨慎使用"""
        if self.flag == 'r':
            raise RuntimeError('拒绝终止只读的SqliteDict')

        self.close()

        if self.filename == ':memory:':
            return

        logger.info("删除 %s" % self.filename)
        try:
            if os.path.isfile(self.filename):
                os.remove(self.filename)
        except (OSError, IOError):
            logger.exception("删除 %s 失败" % (self.filename))

    def __del__(self):
        """析构函数，自动关闭连接"""
        try:
            self.close(do_log=False, force=True)
        except Exception:
            pass

# Adding extra methods for python 2 compatibility (at import time)
if major_version == 2:
    SqliteDict.__nonzero__ = SqliteDict.__bool__
    del SqliteDict.__bool__  # not needed and confusing
# endclass SqliteDict


class SqliteMultithread(Thread):
    """
    Wrap sqlite connection in a way that allows concurrent requests from multiple threads.

    This is done by internally queueing the requests and processing them sequentially
    in a separate thread (in the same order they arrived).

    """

    def __init__(self, filename, autocommit, journal_mode):
        super(SqliteMultithread, self).__init__()
        self.filename = filename
        self.autocommit = autocommit
        self.journal_mode = journal_mode
        # use request queue of unlimited size
        self.reqs = Queue()
        self.setDaemon(True)  # python2.5-compatible
        self.exception = None
        self.log = logging.getLogger('sqlitedict.SqliteMultithread')
        self.start()

    def run(self):
        if self.autocommit:
            conn = sqlite3.connect(
                self.filename, isolation_level=None, check_same_thread=False)
        else:
            conn = sqlite3.connect(self.filename, check_same_thread=False)
        conn.execute('PRAGMA journal_mode = %s' % self.journal_mode)
        conn.text_factory = str
        cursor = conn.cursor()
        conn.commit()
        cursor.execute('PRAGMA synchronous=OFF')

        res = None
        while True:
            req, arg, res, outer_stack = self.reqs.get()
            if req == '--close--':
                assert res, ('--close-- without return queue', res)
                break
            elif req == '--commit--':
                conn.commit()
                if res:
                    res.put('--no more--')
            else:
                try:
                    cursor.execute(req, arg)
                except Exception as err:
                    self.exception = (e_type, e_value, e_tb) = sys.exc_info()
                    inner_stack = traceback.extract_stack()

                    # An exception occurred in our thread, but we may not
                    # immediately able to throw it in our calling thread, if it has
                    # no return `res` queue: log as level ERROR both the inner and
                    # outer exception immediately.
                    #
                    # Any iteration of res.get() or any next call will detect the
                    # inner exception and re-raise it in the calling Thread; though
                    # it may be confusing to see an exception for an unrelated
                    # statement, an ERROR log statement from the 'sqlitedict.*'
                    # namespace contains the original outer stack location.
                    self.log.error('Inner exception:')
                    for item in traceback.format_list(inner_stack):
                        self.log.error(item)
                    # deliniate traceback & exception w/blank line
                    self.log.error('')
                    for item in traceback.format_exception_only(e_type, e_value):
                        self.log.error(item)

                    self.log.error('')  # exception & outer stack w/blank line
                    self.log.error('Outer stack:')
                    for item in traceback.format_list(outer_stack):
                        self.log.error(item)
                    self.log.error('Exception will be re-raised at next call.')

                if res:
                    for rec in cursor:
                        res.put(rec)
                    res.put('--no more--')

                if self.autocommit:
                    conn.commit()

        self.log.debug('received: %s, send: --no more--', req)
        conn.close()
        res.put('--no more--')

    def check_raise_error(self):
        """
        Check for and raise exception for any previous sqlite query.

        For the `execute*` family of method calls, such calls are non-blocking and any
        exception raised in the thread cannot be handled by the calling Thread (usually
        MainThread).  This method is called on `close`, and prior to any subsequent
        calls to the `execute*` methods to check for and raise an exception in a
        previous call to the MainThread.
        """
        if self.exception:
            e_type, e_value, e_tb = self.exception

            # clear self.exception, if the caller decides to handle such
            # exception, we should not repeatedly re-raise it.
            self.exception = None

            self.log.error('An exception occurred from a previous statement, view '
                           'the logging namespace "sqlitedict" for outer stack.')

            # The third argument to raise is the traceback object, and it is
            # substituted instead of the current location as the place where
            # the exception occurred, this is so that when using debuggers such
            # as `pdb', or simply evaluating the naturally raised traceback, we
            # retain the original (inner) location of where the exception
            # occurred.
            reraise(e_type, e_value, e_tb)

    def execute(self, req, arg=None, res=None):
        """
        `execute` calls are non-blocking: just queue up the request and return immediately.
        """
        self.check_raise_error()

        # NOTE: This might be a lot of information to pump into an input
        # queue, affecting performance.  I've also seen earlier versions of
        # jython take a severe performance impact for throwing exceptions
        # so often.
        stack = traceback.extract_stack()[:-1]
        self.reqs.put((req, arg or tuple(), res, stack))

    def executemany(self, req, items):
        for item in items:
            self.execute(req, item)
        self.check_raise_error()

    def select(self, req, arg=None):
        """
        Unlike sqlite's native select, this select doesn't handle iteration efficiently.

        The result of `select` starts filling up with values as soon as the
        request is dequeued, and although you can iterate over the result normally
        (`for res in self.select(): ...`), the entire result will be in memory.
        """
        res = Queue()  # results of the select will appear as items in this queue
        self.execute(req, arg, res)
        while True:
            rec = res.get()
            self.check_raise_error()
            if rec == '--no more--':
                break
            yield rec

    def select_one(self, req, arg=None):
        """Return only the first row of the SELECT, or None if there are no matching rows."""
        try:
            return next(iter(self.select(req, arg)))
        except StopIteration:
            return None

    def commit(self, blocking=True):
        if blocking:
            # by default, we await completion of commit() unless
            # blocking=False.  This ensures any available exceptions for any
            # previous statement are thrown before returning, and that the
            # data has actually persisted to disk!
            self.select_one('--commit--')
        else:
            # otherwise, we fire and forget as usual.
            self.execute('--commit--')

    def close(self, force=False):
        if force:
            # If a SqliteDict is being killed or garbage-collected, then select_one()
            # could hang forever because run() might already have exited and therefore
            # can't process the request. Instead, push the close command to the requests
            # queue directly. If run() is still alive, it will exit gracefully. If not,
            # then there's nothing we can do anyway.
            self.reqs.put(('--close--', None, Queue(), None))
        else:
            # we abuse 'select' to "iter" over a "--close--" statement so that we
            # can confirm the completion of close before joining the thread and
            # returning (by semaphore '--no more--'
            self.select_one('--close--')
            self.join()
# endclass SqliteMultithread
