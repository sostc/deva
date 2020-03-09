
from .core import Stream
from .store import DBStream
from .topic import Topic
import os
import logging

logger = logging.getLogger(__name__)


class Namespace(dict):
    def __init__(self):
        self['stream'] = {}
        self['topic'] = {}
        self['table'] = {}

    def create(self, name, typ='stream', ** kwargs):

        if typ == 'stream':
            constructor = Stream
        elif typ == 'topic':
            constructor = Topic
        elif typ == 'table':
            constructor = DBStream

        try:
            return self[typ][name]
        except KeyError:
            return self[typ].setdefault(
                name,
                constructor(name=name, **kwargs)
            )


namespace = Namespace()


def NS(name='', *args, **kwargs):
    return namespace.create(typ='stream', name=name, *args, **kwargs)


def NT(name='', *args, **kwargs):
    return namespace.create(typ='topic', name=name, *args, **kwargs)


def NB(name='', *args, **kwargs):
    """创建命名的数据库
    NB(name,fname)
    name:流名，表名
    fname，存储文件路径名字
    """
    return namespace.create(typ='table', name=name, *args, **kwargs)
