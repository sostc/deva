"""全局命名功能

全局唯一名称,重复执行获取的都是同一个对象



Example usage::

    log == NS('log')
    bus == NT('bus')
    NT('bus') == NT('bus')
    NS('log') == NS('log')
    NB('tmp') == NB('tmp')
    NX('a') == NX('a')

"""

from .core import Stream
from .store import DBStream, X
from .topic import Topic


class Namespace(dict):
    def __init__(self):
        self['stream'] = {}
        self['topic'] = {}
        self['table'] = {}
        self['data'] = {}
        self['webserver'] = {}

    def create(self, name, typ='stream', **kwargs):
        constructor = {'stream': Stream,
                       'topic': Topic,
                       'table': DBStream,
                       'data': X, }

        if typ == 'webserver':
            from .page import PageServer
            constructor.update({'webserver': PageServer})

        try:
            return self[typ][name]
        except KeyError:
            return self[typ].setdefault(
                name,
                constructor.get(typ)(name=name, **kwargs)
            )


namespace = Namespace()


def NS(name='', *args, **kwargs):
    return namespace.create(typ='stream', name=name, *args, **kwargs)


def NT(name='', *args, **kwargs):
    """命名主题.

    跨进程的流，唯一名称

    Args:
        *args: [description]
        **kwargs: [description]
        name: [description] (default: {''})

    Returns:
        [description]
        [type]
    """
    try:
        return namespace.create(typ='topic', name=name, *args, **kwargs)
    except Exception as e:
        print(e)
        return None


def NB(name, *args, **kwargs):
    """创建命名的DBStream.

    创建命名的DBStream数据库,全局名称唯一

    Args:
        name: 数据表名称 (default: {'default'})
        filename:文件路径名称(default:{'nb'})


    Returns:
        DBStream(name,filename)
        type

    Example::

        123>>NB('tmp')

        ('key','value')>>NB('tmp')
    """
    return namespace.create(typ='table', name=name, *args, **kwargs)


def NX(name=''):
    """创建命名数据存储对象.

    返回的对象，data属性存储了数据，用在你们函数内部以及函数管道上快速存储单个数据

    Example usage::

        123>>NX('a')
        assert NX('a').data == 123

        10|range|sum|NX('a')
        assert NX('a').data ==45

        f = lambda x:x>>NX('b')
        f(10)
        assert NX('b').data ==10


    """
    return namespace.create(typ='data', name=name)


def NW(name='', host='127.0.0.1', port=9999, start=True):
    """创建命名web服务器.

    返回的对象，data属性存储了数据，用在你们函数内部以及函数管道上快速存储单个数据

    Example usage::

         pass

    """
    return namespace.create(typ='webserver', name=name, host=host, port=port, start=start)
