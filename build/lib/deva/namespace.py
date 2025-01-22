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
from .store import DBStream
from .topic import Topic, TCPTopic


class Namespace(dict):
    """命名空间类,继承自dict
    
    用于管理全局唯一的命名对象,包括stream、topic、table等不同类型
    """
    def __init__(self):
        """初始化命名空间
        
        创建不同类型对象的存储字典
        """
        # 初始化各类型的存储字典
        self['stream'] = {}  # 存储Stream对象
        self['topic'] = {}   # 存储Topic对象 
        self['tcptopic'] = {} # 存储TCPTopic对象
        self['table'] = {}    # 存储DBStream对象
        self['data'] = {}     # 存储数据对象
        self['webserver'] = {} # 存储PageServer对象

    def create(self, name, typ='stream', **kwargs):
        """创建或获取一个命名对象
        
        Args:
            name: 对象名称,用于唯一标识
            typ: 对象类型,可选值包括stream/topic/table/tcptopic/webserver,默认为stream
            **kwargs: 传递给对象构造函数的额外参数
            
        Returns:
            返回已存在的同名对象或新创建的对象实例
        """
        # 定义类型到构造函数的映射
        constructor = {
            'stream': Stream,     # 流处理对象
            'topic': Topic,       # 主题对象
            'table': DBStream,    # 数据库流对象
            'tcptopic': TCPTopic  # TCP主题对象
        }

        # webserver类型需要动态导入
        if typ == 'webserver':
            from .page import PageServer
            constructor['webserver'] = PageServer

        # 先尝试获取已存在对象
        try:
            return self[typ][name]
        except KeyError:
            # 不存在则创建新对象并存储
            return self[typ].setdefault(
                name,
                constructor.get(typ)(name=name, **kwargs)
            )

namespace = Namespace()


def NS(name='', *args, **kwargs):
    """命名流.
    
    创建或获取一个命名的Stream流处理对象,全局名称唯一
    
    Args:
        name: 流对象名称,用于唯一标识 (default: {''})
        *args: 传递给Stream构造函数的位置参数
        **kwargs: 传递给Stream构造函数的关键字参数
        
    Returns:
        Stream: 返回已存在的同名Stream对象或新创建的Stream对象实例
    """
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


def NWT(name='', *args, **kwargs):

    try:
        return namespace.create(typ='tcptopic', name=name, *args, **kwargs)
    except Exception as e:
        print(e)
        return None


def NB(name='default', *args, **kwargs):
    """创建命名的DBStream.

    创建命名的DBStream数据库对象,用于持久化存储数据,全局名称唯一。
    DBStream支持将数据以键值对形式存储到数据库中。

    Args:
        name (str): 数据表名称,用于唯一标识数据表
        filename (str, optional): 数据库文件路径,默认为'nb'
        *args: 传递给DBStream构造函数的位置参数
        **kwargs: 传递给DBStream构造函数的关键字参数

    Returns:
        DBStream: 返回DBStream实例对象

    Example::
        
        # 创建名为'users'的数据表
        db = NB('users')
        
        # 存储单个值
        123 >> NB('numbers')
        
        # 存储键值对
        ('user1', {'name':'张三', 'age':20}) >> NB('users')
        
        # 从文件读取数据
        NB('logs', filename='app.log')
        
        # 查询数据
        db = NB('users')
        print(db['user1'])  # 获取key为'user1'的数据
    """
    return namespace.create(typ='table', name=name, *args, **kwargs)



def NW(name='', host='127.0.0.1', port=9999, start=True, **kwargs):
    """创建命名web服务器.

    创建一个命名的Web服务器对象,用于通过HTTP协议提供数据访问服务。
    服务器对象包含data属性用于存储数据,支持在函数管道中快速存取单个数据。

    Args:
        name (str): 服务器名称,用于唯一标识,默认为空字符串
        host (str): 服务器监听地址,默认为'127.0.0.1'
        port (int): 服务器监听端口,默认为9999
        start (bool): 是否立即启动服务器,默认为True
        **kwargs: 其他传递给服务器的参数

    Returns:
        WebServer: 返回WebServer实例对象

    Example::

        # 创建并启动web服务器
        server = NW('myserver', port=8080)
        
        # 存储数据
        data = {'name': '张三', 'age': 20}
        data >> server
        
        # 通过HTTP访问数据
        # GET http://127.0.0.1:8080/data
        
        # 自定义host和port
        NW('api', host='0.0.0.0', port=5000)
        
        # 创建但不立即启动
        server = NW('temp', start=False)
        server.start()  # 手动启动

    """
    return namespace.create(typ='webserver', name=name, host=host, port=port, start=start, debug=True)