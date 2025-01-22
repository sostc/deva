#!/usr/bin/env python

"""Module enabling a sh like infix syntax (using pipes)."""
from tornado import gen
import asyncio
import functools
import itertools
import socket
import sys
from contextlib import closing
from collections import deque
import dill
import json
import threading
from tornado.ioloop import IOLoop
from urllib.parse import quote


import builtins


__all__: builtins.list[builtins.str] = [
    'P', 'tail', 'skip', 'all', 'any', 'average', 'count',
    'as_dict', 'as_set', 'permutations', 'netcat', 'netwrite',
    'traverse', 'concat', 'as_list', 'as_tuple', 'stdout', 'lineout',
    'tee', 'add', 'first', 'chain', 'take_while', 'attr',
    'skip_while', 'aggregate', 'groupby', 'sort', 'reverse',
    'chain_with', 'islice', 'izip', 'passed', 'index', 'strip',
    'lstrip', 'rstrip', 'run_with', 'append', 'to_type', 'transpose',
    'dedup', 'uniq', 'to_dataframe', 'pmap', 'pfilter', 'post_to',
    'head', 'read', 'tcp_write', 'write_to_file', 'size', 'ls', 'range',
    'sum', 'split', 'sample', 'extract', 'readlines', 'last',
    'abs', 'type', 'll', 'pslice','truncate',
    'dir', 'help',
    'eval',
    'hash',
    'id',
    'input',
    'iter',
    'len',
    'max',
    'min',
    'print',
    'range',
    'sum',
    'get_instances_by_class',
    'to_json',
    'cm', 'call_method',
    'sw', 'sliding_window',
    'read_from',
]


_io_loops = []


def get_io_loop(asynchronous=True):
    if asynchronous:
        return IOLoop.current()

    if not _io_loops:
        loop = IOLoop()
        thread = threading.Thread(target=loop.start)
        thread.daemon = True
        thread.start()
        _io_loops.append(loop)

    return _io_loops[-1]


class Pipe:
    """管道类 - 用于创建可链式调用的函数
    
    使用方法:
    1. 作为装饰器:
        @Pipe
        def first(iterable):
            return next(iter(iterable))
    
    2. 链式调用:
        [1, 2, 3] | first  # 输出: 1
        
    3. 支持的操作符:
        | : 管道操作符
        >> : 右移操作符
        @ : matmul操作符
        << : 左移操作符
        
    示例:
        [1,2,3] | head(2)  # [1,2]
        range(10) >> pfilter(lambda x: x>5)  # [6,7,8,9]
        [1,2,3] @ reverse  # [3,2,1]
    """

    def __init__(self, func):
        """decorater 初始化."""
        self.func = func
        functools.update_wrapper(self, func)


    def run_async(self, asyncfunc, callback):
        """异步执行函数
        
        将异步函数转换为Future对象并添加到事件循环中执行
        
        Args:
            asyncfunc: 异步函数对象
            callback: 回调函数,用于处理异步执行结果
            
        Example:
            async def my_async_func():
                return await some_async_operation()
                
            pipe.run_async(my_async_func(), lambda result: print(result))
        """
        
        futs = gen.convert_yielded(asyncfunc)
        self.loop = get_io_loop()
        self.loop.add_future(futs, lambda x: callback(x.result()))


    def __ror__(self, other):
        """管道操作符 | 的重载实现
        
        支持两种用法:
        1. 同步调用: 直接将左操作数作为参数传给被装饰的函数
        2. 异步调用: 如果左操作数是awaitable对象,则异步执行
        
        Args:
            other: 管道左边的操作数
            
        Returns:
            同步调用时返回函数执行结果
            异步调用时返回None(结果通过callback处理)
            
        Examples:
            # 同步调用
            [1,2,3] | head(2)  # 返回[1,2]
            
            # 异步调用
            async def async_data():
                return await get_data()
            async_data() | process_data  # 异步处理数据
        """
        if isinstance(other, gen.Awaitable):
            self.run_async(other, self.func)
        else:
            return self.func(other)
    def __rrshift__(self, other):
        """重载右移操作符 >>
        
        支持两种用法:
        1. 如果左操作数有sink方法,则调用其sink方法并传入当前函数
        2. 否则,等同于管道操作符 | 的行为
        
        Args:
            other: 管道左边的操作数
            
        Returns:
            如果左操作数有sink方法,返回sink方法的执行结果
            否则返回当前函数对左操作数的执行结果
            
        Examples:
            # 对于有sink方法的对象(如Stream)
            stream >> print  # 等同于 stream.sink(print)
            
            # 对于普通对象
            [1,2,3] >> head(2)  # 等同于 [1,2,3] | head(2)
        """
        # 左边如果支持sink方法，则变为左边sink右边的函数
        if hasattr(other, 'sink'):
            return other.sink(self.func)
        else:
            return self.__ror__(other)
    def __rmatmul__(self, other):
        """左边的 @."""
        return self.__ror__(other)

    def __lshift__(self, other):  # 右边的<<
        """右边的 <<."""
        return self.__ror__(other)

    def __call__(self, *args, **kwargs):
        """像正常函数一样使用使用."""
        return self.func(*args, **kwargs)

    def __add__(self, other):
        """函数组合运算符重载

        使用加号运算符组合多个函数,从左到右依次执行。
        (a + b + c)(x) 等价于 c(b(a(x)))

        Args:
            other: 要组合的另一个函数

        Returns:
            Pipe: 返回组合后的新函数

        Examples:
            # 定义两个简单函数
            @P 
            def double(x): return x * 2
            @P
            def inc(x): return x + 1

            # 使用加号组合函数
            f = double + inc  # 先double再inc
            f(3)  # 7 = (3 * 2) + 1

            # 支持多个函数组合
            g = double + inc + double  # 依次执行
            g(2)  # 10 = ((2 * 2) + 1) * 2
        """
        return Pipe(lambda *args, **kwargs: other(self(*args, **kwargs)))
    # def __repr__(self):
    #     """转化成Pipe对象后的repr."""
    #     return f'<func {self.func.__module__}.{self.func.__name__}@P>'


@Pipe
def P(func):
    """将普通函数转换为管道函数

    将普通函数转换为支持管道操作的Pipe对象。如果传入的已经是Pipe对象则直接返回,
    防止重复包装。转换后的函数可以使用 >> 和 @ 等管道操作符。

    Args:
        func: 要转换的函数对象

    Returns:
        Pipe: 返回包装后的Pipe对象

    Examples:
        # 装饰器方式使用
        @P
        def double(x):
            return x * 2
        
        [1,2,3] >> double  # [2,4,6]

        # 直接包装函数
        print@P  # 转换print为管道函数
        [1,2,3] >> print@P  # 打印[1,2,3]

        # 链式调用
        [1,2,3] >> double >> print@P

        # 已经是Pipe对象则直接返回
        double@P == double  # True
    """
    if not isinstance(func, Pipe):  # 防止pipe被重复管道化
        return Pipe(func)
    else:
        return func

@Pipe
def to_dataframe(dct, orient='index'):
    """将字典转换为pandas DataFrame对象

    将输入的字典转换为pandas DataFrame数据框。可以指定orient参数来控制转换方式。

    参数:
        dct: 要转换的字典对象
        orient: 转换方向,可选值为'index'或'columns'
            - 'index': 字典的键作为DataFrame的索引
            - 'columns': 字典的键作为DataFrame的列名
    
    返回:
        pandas.DataFrame: 转换后的DataFrame对象

    示例:
        data = {'a': [1,2], 'b': [3,4]}
        
        # 字典键作为索引
        data >> to_dataframe('index')
        #      a  b
        # 0    1  3
        # 1    2  4

        # 字典键作为列名
        data >> to_dataframe('columns') 
        #    a    b
        # 0  1    3
        # 1  2    4
    """
    import pandas as pd
    return pd.DataFrame.from_dict(dct, orient=orient)

@Pipe
def head(qte: int = 5):
    """返回可迭代对象的前N个元素
    
    参数:
        qte: 需要返回的元素个数,默认为5
        
    示例:
        [1,2,3] | head(2)  # [1,2]
    """
    def _head(iterable):
        i = qte
        result = []
        for item in iterable:
            if i > 0:
                i -= 1
                result.append(item)
            else:
                break
        return result

    if isinstance(qte, int):
        return _head @ P
    else:
        iterable, qte = qte, 5
        return _head(iterable)


@Pipe
def tail(qte: int = 5):
    "Yield qte of elements in the given iterable."
    def _(iterable):
        return list(deque(iterable, maxlen=qte))

    if isinstance(qte, int):
        return _ @ P
    else:
        iterable, qte = qte, 5
        return _(iterable)


@Pipe
def last(iterable):
    return (iterable | tail(1))[0]


@Pipe
def skip(qte: int):
    "Skip qte elements in the given iterable, then yield others."
    def _(iterable):
        i = qte
        for item in iterable:
            if i == 0:
                yield item
            else:
                i -= 1

    return _ @ P


@Pipe
def dedup(key=lambda x: x):
    """去除重复元素.

    使用集合记录已出现的元素,只保留第一次出现的元素。
    可以通过key函数指定用于判断重复的键。

    Args:
        key: 用于生成判重键的函数,默认使用元素本身作为键

    Returns:
        返回一个生成器,只生成不重复的元素

    Example::
        
        # 去除简单列表中的重复
        [1,2,2,3,1] | dedup | list  # [1,2,3]
        
        # 根据元素的某个属性去重
        users = [
            {'id':1, 'name':'张三'},
            {'id':2, 'name':'李四'},
            {'id':1, 'name':'张三'} 
        ]
        users | dedup(key=lambda x: x['id']) | list
        # [{'id':1, 'name':'张三'}, {'id':2, 'name':'李四'}]
        
        # 对字符串按长度去重
        ['aa','bb','cc','ddd'] | dedup(key=len) | list
        # ['aa', 'ddd']
    """
    def _(iterable):
        seen = set()
        for item in iterable:
            dupkey = key(item)
            if dupkey not in seen:
                seen.add(dupkey)
                yield item

    return _ @ P

@Pipe
def uniq(key=lambda x: x):
    """去除连续重复元素.

    只保留连续重复元素中的第一个,非连续的重复元素会保留。
    可以通过key函数指定用于判断重复的键。

    Args:
        key: 用于生成判重键的函数,默认使用元素本身作为键

    Returns:
        返回一个生成器,只生成不连续重复的元素

    Example::
        
        # 去除连续重复数字
        [1,1,2,2,1] | uniq | list  # [1,2,1]
        
        # 根据元素的某个属性去重
        users = [
            {'id':1, 'name':'张三'},
            {'id':1, 'name':'张三'},
            {'id':2, 'name':'李四'},
            {'id':1, 'name':'张三'}
        ]
        users | uniq(key=lambda x: x['id']) | list
        # [{'id':1, 'name':'张三'}, {'id':2, 'name':'李四'}, {'id':1, 'name':'张三'}]
        
        # 对字符串按长度去重
        ['aa','bb','cc','ddd'] | uniq(key=len) | list
        # ['aa', 'ddd']
    """
    def _(iterable):
        iterator = iter(iterable)
        try:
            prev = next(iterator)
        except StopIteration:
            return
        yield prev
        prevkey = key(prev)
        for item in iterator:
            itemkey = key(item)
            if itemkey != prevkey:
                yield item
            prevkey = itemkey

    return _ @ P

@Pipe
def pmap(func):
    """对迭代器中的每个元素应用函数.

    对迭代器中的每个元素应用给定的函数,返回一个新的迭代器。
    这是Python内置map函数的管道版本。

    Args:
        func: 要应用到每个元素的函数

    Returns:
        返回一个生成器,生成应用func后的结果

    Example::
        
        # 对每个数字加1
        [1,2,3] | pmap(lambda x: x+1) | list  # [2,3,4]
        
        # 将字符串转为大写
        ['a','b','c'] | pmap(str.upper) | list  # ['A','B','C']
        
        # 获取字典中的某个字段
        users = [{'name':'张三','age':18}, {'name':'李四','age':20}]
        users | pmap(lambda x: x['name']) | list  # ['张三','李四']
    """
    def _(iterable):
        return map(func, iterable)

    return _ @ P

@Pipe
def pfilter(func):
    """pfilter == where"""
    def _(iterable):
        return filter(func, iterable)

    return _ @ P


@Pipe
def all(pred):
    """判断迭代器中的所有元素是否都满足条件.

    对迭代器中的每个元素应用pred函数,如果所有元素都返回True则返回True,
    否则返回False。这是Python内置all函数的管道版本。

    Args:
        pred: 判断函数,接受一个参数返回bool值

    Returns:
        bool: 如果所有元素都满足条件返回True,否则返回False

    Example::
        
        # 判断是否所有数字都大于0
        [1,2,3] | all(lambda x: x>0)  # True
        [-1,2,3] | all(lambda x: x>0)  # False
        
        # 判断是否所有字符串长度都大于2
        ['abc','def','gh'] | all(lambda x: len(x)>2)  # False
        
        # 判断是否所有用户年龄都大于18
        users = [{'name':'张三','age':20}, {'name':'李四','age':16}]
        users | all(lambda x: x['age']>=18)  # False
    """
    def _(iterable):
        return builtins.all(pred(x) for x in iterable)

    return _ @ P

@Pipe
def any(pred):
    """判断迭代器中是否存在满足条件的元素.

    对迭代器中的每个元素应用pred函数,如果存在任意一个元素返回True则返回True,
    否则返回False。这是Python内置any函数的管道版本。

    Args:
        pred: 判断函数,接受一个参数返回bool值

    Returns:
        bool: 如果存在满足条件的元素返回True,否则返回False

    Example::
        
        # 判断是否存在小于0的数字
        [1,-2,3] | any(lambda x: x<0)  # True
        [1,2,3] | any(lambda x: x<0)  # False
        
        # 判断是否存在长度小于3的字符串
        ['abc','de','fgh'] | any(lambda x: len(x)<3)  # True
        
        # 判断是否存在未成年用户
        users = [{'name':'张三','age':20}, {'name':'李四','age':16}]
        users | any(lambda x: x['age']<18)  # True
    """
    def _(iterable):
        return builtins.any(pred(x) for x in iterable)

    return _ @ P

@Pipe
def average(iterable):
    """计算迭代器中所有元素的平均值.

    对迭代器中的所有数值元素求和并计算平均值。如果迭代器为空会抛出除零异常。

    Args:
        iterable: 包含数值的迭代器对象

    Returns:
        float: 所有元素的平均值

    Example::
        
        # 计算数字列表的平均值
        [1, 2, 3, 4] | average  # 2.5
        
        # 计算浮点数的平均值
        [1.5, 2.5, 3.5] | average  # 2.5
        
        # 计算用户年龄的平均值
        users = [{'name':'张三','age':20}, {'name':'李四','age':30}]
        users | select(lambda x: x['age']) | average  # 25.0
        
        # 空迭代器会抛出异常
        [] | average  # ZeroDivisionError
    """
    total = 0.0
    qte = 0
    for element in iterable:
        total += element
        qte += 1
    return total / qte

@Pipe
def count(iterable):
    """计算迭代器中元素的数量.

    遍历迭代器并统计其中包含的元素个数。

    Args:
        iterable: 任意可迭代对象

    Returns:
        int: 元素的总数量

    Example::
        
        # 计算列表长度
        [1, 2, 3] | count  # 3
        
        # 计算字符串长度
        'hello' | count  # 5
        
        # 计算生成器元素个数
        range(10) | count  # 10
        
        # 计算过滤后的元素个数
        [1,2,3,4,5] | where(lambda x: x>3) | count  # 2
        
        # 空迭代器返回0
        [] | count  # 0
    """
    count = 0
    for element in iterable:
        count += 1
    return count


@Pipe
def as_dict(iterable):
    return dict(iterable)


@Pipe
def as_set(iterable):
    return set(iterable)


@Pipe
def permutations(r=None):
    """生成迭代器中所有元素的全排列.

    生成迭代器中所有元素的全排列,返回一个生成器。

    Args:
        r: 每个排列的长度,默认为None表示全排列
    """
    def _(iterable):
        for x in itertools.permutations(iterable, r):
            yield x

    return _ @ P


@Pipe
def netcat(host, port):
    """通过TCP连接发送数据并接收响应.
    
    建立TCP连接并发送数据,然后持续接收响应直到连接关闭。
    支持发送字符串或可迭代对象中的数据。

    Args:
        host (str): 目标主机地址
        port (int): 目标主机端口

    Returns:
        生成器: 返回接收到的响应数据

    Example::
        
        # 发送单个字符串
        'hello' | netcat('localhost', 8080) | list
        
        # 发送多个数据
        ['hello', 'world'] | netcat('127.0.0.1', 1234) | list
        
        # 发送并打印响应
        'ping' | netcat('example.com', 80) | stdout
        
        # 发送嵌套数据结构
        [['a', 'b'], 'c'] | netcat('localhost', 9999) | list
    """
    def _(to_send):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.connect((host, port))
            for data in to_send | traverse:
                s.send(data.encode("utf-8"))
            while 1:
                data = s.recv(4096)
                if not data:
                    break
                yield data

    return _ @ P

@Pipe
def netwrite(host, port):
    """通过TCP连接发送数据,不接收响应.
    
    建立TCP连接并发送数据,发送完成后立即关闭连接。
    支持发送字符串或可迭代对象中的数据。

    Args:
        host (str): 目标主机地址
        port (int): 目标主机端口

    Returns:
        生成器: 返回None

    Example::
        
        # 发送单个字符串
        'hello' | netwrite('localhost', 8080)
        
        # 发送多个数据
        ['hello', 'world'] | netwrite('127.0.0.1', 1234)
        
        # 发送嵌套数据结构
        [['a', 'b'], 'c'] | netwrite('localhost', 9999)
        
        # 发送到日志服务器
        'log message' | netwrite('logserver.com', 514)
    """
    def _(to_send):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.connect((host, port))
            for data in to_send | traverse:
                s.send(data.encode("utf-8"))

    return _ @ P

@Pipe
def traverse(args):
    """递归遍历嵌套数据结构并生成叶子节点.
    
    深度优先遍历嵌套的数据结构(列表、元组等),将字符串和不可迭代对象作为叶子节点输出。
    字符串虽然可迭代但作为叶子节点处理。

    Args:
        args: 要遍历的数据结构,可以包含嵌套的列表、元组等

    Yields:
        str或其他类型: 遍历到的叶子节点值

    Example::
        
        # 遍历简单列表
        [1, 2, 'a'] | traverse 
        # 输出: 1, 2, 'a'
        
        # 遍历嵌套结构
        [1, [2, 3], ['a', ['b', 'c']]] | traverse
        # 输出: 1, 2, 3, 'a', 'b', 'c'
        
        # 混合类型
        [1, {'k':'v'}, ['a', 2]] | traverse 
        # 输出: 1, {'k':'v'}, 'a', 2
        
        # 字符串作为叶子节点
        ['abc', ['def', 'ghi']] | traverse
        # 输出: 'abc', 'def', 'ghi'
    """
    for arg in args:
        try:
            if isinstance(arg, str):
                yield arg
            else:
                for i in arg | traverse:
                    yield i
        except TypeError:
            # not iterable --- output leaf
            yield arg

@Pipe
def tcp_write(host='127.0.0.1', port=1234):
    """通过TCP连接发送序列化数据.
    
    将数据序列化后通过TCP socket发送到指定主机和端口。
    使用dill进行序列化,支持发送Python对象。
    每条数据后会自动添加换行符作为分隔。

    Args:
        host (str): 目标主机地址,默认为'127.0.0.1'
        port (int): 目标端口号,默认为1234

    Returns:
        function: 返回处理函数,用于在管道中发送数据

    Example::
        
        # 发送简单数据
        'hello' | tcp_write('localhost', 5000)
        
        # 发送Python对象
        class User:
            def __init__(self, name):
                self.name = name
        
        user = User('张三')
        user | tcp_write(port=9999)
        
        # 在数据流中使用
        stream = from_list([1,2,3])
        stream | tcp_write()
        
        # 指定目标地址
        data | tcp_write('10.0.0.1', 8080)
    """
    def _(to_send):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.connect((host, port))
            s.send(dill.dumps(to_send))
            s.send(b'\n')

    return _ @ P

@Pipe
def concat(separator=", "):
    """连接可迭代对象中的元素.
    
    将可迭代对象中的所有元素转换为字符串并用指定的分隔符连接起来。
    
    Args:
        separator (str): 用于连接元素的分隔符,默认为", "
        
    Returns:
        function: 返回处理函数,用于在管道中连接元素
        
    Example::
        
        # 连接列表元素
        [1, 2, 3] | concat()  # "1, 2, 3"
        
        # 指定分隔符
        ['a', 'b', 'c'] | concat('-')  # "a-b-c"
        
        # 连接不同类型的元素
        [1, 'hello', 3.14] | concat()  # "1, hello, 3.14"
        
        # 在数据流中使用
        stream = from_list(['x', 'y', 'z'])
        stream | concat('|')  # "x|y|z"
        
        # 连接空迭代器
        [] | concat()  # ""
    """
    def _(iterable):
        return separator.join(map(str, iterable))
    return _ @ P

@Pipe
def split(sep="\n"):
    def _(iteration):
        return iteration.split(sep)
    return _ @ P


@Pipe
def pslice(start, end):
    def _(iteration):
        return iteration[start:end]
    return _ @ P


@Pipe
def attr(name):
    """获取对象的属性值.
    
    获取对象指定名称的属性值,相当于getattr()函数的管道版本。
    
    Args:
        name (str): 要获取的属性名称
        
    Returns:
        function: 返回处理函数,用于在管道中获取对象属性
        
    Example::
        
        # 获取对象属性
        class Person:
            def __init__(self):
                self.name = "张三"
                
        person = Person()
        person | attr('name')  # "张三"
        
        # 获取列表长度
        [1, 2, 3] | attr('__len__')()  # 3
        
        # 获取字符串方法
        "hello" | attr('upper')()  # "HELLO"
        
        # 在数据流中使用
        stream = from_list([Person(), Person()])
        stream | attr('name')  # 获取每个对象的name属性
    """
    def _(object):
        return getattr(object, name)
    return _ @ P

@Pipe
def as_list(iterable):
    return list(iterable)


@Pipe
def as_tuple(iterable):
    return tuple(iterable)


@Pipe
def stdout(x):
    sys.stdout.write(str(x))
    return x


@Pipe
def lineout(x):
    sys.stdout.write(str(x) + "\n")
    return x


@Pipe
def tee(iterable):
    for item in iterable:
        sys.stdout.write(str(item) + "\n")
        yield item


# @Pipe
# def write_to_file(fn, prefix='', suffix='\n', flush=True, mode='a+'):
#     """同时支持二进制和普通文本的写入.

#     Exsapmles:
#         123>>write_to_file('tpm.txt')
#         b'abc'>>write_to_file('music.mp3','ab+')
#     """
#     def _(content):
#         with open(fn, mode) as f:
#             if 'b' in mode:
#                 f.write(content)
#             else:
#                 f.write(prefix)
#                 f.write(str(content))
#                 f.write(suffix)
#             if flush:
#                 f.flush()
#         return content

#     return _ @ P
@Pipe
def write_to_file(fn, prefix='', suffix='\n', flush=True, mode='a+'):
    """同时支持二进制和普通文本的写入.

    将内容写入文件,支持普通文本和二进制格式。可以添加前缀和后缀,并控制是否立即刷新缓冲区。

    Args:
        fn (str): 文件路径
        prefix (str): 写入内容前的前缀,仅文本模式有效,默认为空字符串
        suffix (str): 写入内容后的后缀,仅文本模式有效,默认为换行符
        flush (bool): 是否立即刷新缓冲区,默认为True
        mode (str): 文件打开模式,默认为'a+'追加模式

    Returns:
        写入的原始内容

    Examples:
        # 写入文本文件
        123 >> write_to_file('numbers.txt')  # 写入"123\n"
        'hello' >> write_to_file('log.txt', prefix='[INFO] ')  # 写入"[INFO] hello\n"
        
        # 写入二进制文件
        b'data' >> write_to_file('file.bin', mode='wb')  # 以二进制模式写入
        
        # 追加内容
        'append' >> write_to_file('log.txt', mode='a')  # 追加到文件末尾
        
        # 控制刷新
        'cached' >> write_to_file('cache.txt', flush=False)  # 不立即刷新缓冲区
    """
    f = open(fn, mode)

    def _(content):
        if 'b' in mode:
            f.write(content)
        else:
            f.write(prefix)
            f.write(str(content))
            f.write(suffix)
        if flush:
            f.flush()
        return content

    return _ @ P


@Pipe
def add(x):
    return sum(x)


@Pipe
def first(iterable):
    return next(iter(iterable))


@Pipe
def chain(iterable):
    return itertools.chain(*iterable)


@Pipe
def take_while(predicate):
    def _(iterable):
        return itertools.takewhile(predicate, iterable)

    return _ @ P


@Pipe
def skip_while(predicate):
    def _(iterable):
        return itertools.dropwhile(predicate, iterable)

    return _ @ P


@Pipe
def aggregate(function, **kwargs):
    def _(iterable):
        if 'initializer' in kwargs:
            return functools.reduce(function, iterable, kwargs['initializer'])
        return functools.reduce(function, iterable)

    return _ @ P


@Pipe
def groupby(keyfunc):
    def _(iterable):
        return itertools.groupby(sorted(iterable, key=keyfunc), keyfunc)

    return _ @ P


@Pipe
def sort(**kwargs):
    def _(iterable):
        return sorted(iterable, **kwargs)

    return _ @ P


@Pipe
def reverse(iterable):
    return reversed(iterable)


@Pipe
def passed(x):
    pass


@Pipe
def index(value, start=0, stop=None):
    def _(iterable):
        return iterable.index(value, start, stop or len(iterable))

    return _ @ P


@Pipe
def strip(chars='\n'):
    def _(iterable):
        return iterable.strip(chars)

    return _ @ P


@Pipe
def rstrip(chars='\n'):
    def _(iterable):
        return iterable.rstrip(chars)

    return _ @ P


@Pipe
def lstrip(chars='\n'):
    def _(iterable):
        return iterable.lstrip(chars)

    return _ @ P


@Pipe
def run_with(func):
    """
    根据输入类型，将输入数据辩护为具体参数去调用函数。

    如果输入是字典，则使用关键字参数调用函数。
    如果输入是可迭代对象，则使用位置参数调用函数。
    否则，直接将输入作为单个参数调用函数。

    Args:
        func: 要调用的函数对象。

    Returns:
        一个Pipe对象,用于在管道中调用func函数。

    Examples:
        >>> def add(x, y):
        ...     return x + y
        >>> add_with = run_with(add)
        >>> [1, 2] | add_with  # 等同于 add(1, 2)
        3
        >>> {'x': 1, 'y': 2} | add_with  # 等同于 add(x=1, y=2)
        3
        >>> 1 | add_with  # 等同于 add(1)
        1
    """
    def _(iterable):
        return (func(**iterable) if isinstance(iterable, dict) else
                func(*iterable) if hasattr(iterable, '__iter__') else
                func(iterable))

    return _ @ P

@Pipe
def append(y):
    """
    将元素追加到列表的尾部。

    如果输入是一个可迭代对象（不是字符串），则将元素追加到该对象的尾部，并返回一个新的可迭代对象。
    如果输入不是可迭代对象，则将输入和元素作为列表的两个元素返回。

    Args:
        y: 要追加的元素。

    Returns:
        一个Pipe对象,用于在管道中调用append函数。

    Examples:
        >>> [] | append('c') | append('b')  # 等同于 ['c', 'b']
        ['c', 'b']
        >>> 'hello' | append('world')  # 等同于 ['hello', 'world']
        ['hello', 'world']
    """
    def _(iterable):
        if hasattr(iterable, '__iter__') and not isinstance(iterable, str):
            return iterable + type(iterable)([y])
        return [iterable, y]

    return _ @ P

@Pipe
def to_type(t):
    """转换类型 '3'>>to_type(int)==3"""
    def _(x):
        return t(x)

    return _ @ P


@Pipe
def readlines(fn) -> gen.Generator[builtins.str, gen.Any, None]:
    """
    按行读入文本文件，并返回一个生成器，用于在管道中处理每一行的内容。

    Args:
        fn (str): 文件路径

    Yields:
        str: 文件中的每一行内容

    Examples:
        >>> 'example.log' | readlines() | tail(2)  # 读取example.log文件的最后两行
        ['line 9', 'line 10']
    """
    with open(fn, 'r') as f:
        for line in f:
            yield line.strip()

@Pipe
def read(fn):
    """读取整个文本文件内容为字符串

    Args:
        fn (str): 文件路径

    Returns:
        str: 文件内容字符串

    Examples:
        >>> 'test.txt'>>read()  # test.txt内容为'hello world'
        'hello world'
        
        >>> 'data.csv'>>read()>>split('\n')  # 读取CSV文件并按行分割
        ['col1,col2', 'a,1', 'b,2']
    """
    with open(fn, 'r') as f:
        return f.read()


@Pipe
def transpose(iterable):
    return list(zip(*iterable))


chain_with = Pipe(itertools.chain)
# [1,2,3]>> chain_with([4,5,6])>>to_list == [1,2,3,4,5,6]
islice = Pipe(itertools.islice)
# range(10)>>islice(2,100,2)>>to_list == [2,4,6,8]

# Python 2 & 3 compatibility
if "izip" in dir(itertools):
    izip = Pipe(itertools.izip)
else:
    izip = Pipe(zip)


@Pipe
def size(x):
    return sys.getsizeof(x)


@Pipe
def post_to(url='http://127.0.0.1:7777', tag='', asynchronous=True, headers={}):
    """将数据通过HTTP POST方法发送到指定URL

    支持发送字符串、二进制数据和Python对象。对于Python对象会使用dill进行序列化。
    支持同步和异步两种发送方式。异步方式使用Tornado的AsyncHTTPClient。

    Args:
        url (str): 目标URL地址,默认为'http://127.0.0.1:7777'
        tag (str): 请求标签,会添加到headers中
        asynchronous (bool): 是否使用异步方式发送,默认为True
        headers (dict): 额外的HTTP请求头

    Returns:
        如果asynchronous=True,返回Future对象
        如果asynchronous=False,返回requests.Response对象

    Examples::
        # 发送字典数据
        {'name': 'test', 'value': 123} >> post_to('http://example.com/api')

        # 发送DataFrame
        df = pd.DataFrame({'a':[1,2], 'b':[3,4]})
        df >> post_to('http://example.com/data')

        # 同步发送
        result = [1,2,3] >> post_to('http://example.com', asynchronous=False)
        print(result.status_code)

        # 添加自定义headers
        data >> post_to('http://example.com', headers={'token': 'abc123'})

        # 使用tag标记请求
        data >> post_to('http://example.com', tag='test-data')

    Note:
        在Jupyter外使用异步方式时需要:
        loop = IOLoop.current(instance=True)
        loop.start()
    """
    headers.update({'tag': quote(tag)})

    def _encode(body):
        import pandas as pd
        if isinstance(body, pd.DataFrame):
            body = body.to_json()
        if isinstance(body,dict):
            body = json.dumps(body)
        else:
            body = dill.dumps(body)
        return body

    @gen.coroutine 
    def _async(body):
        """异步发送HTTP POST请求

        将数据异步发送到指定URL。支持单个数据和数据列表。
        数据会被编码并序列化后发送。

        Args:
            body: 要发送的数据,可以是单个对象或对象列表

        Returns:
            tornado.concurrent.Future: 包含HTTP响应的Future对象

        Note:
            - 单个对象会被转换为单元素列表
            - 每个对象都会通过_encode()进行编码
            - 编码后的数据会被dill序列化
            - 使用tornado的AsyncHTTPClient发送请求
        """
        if not isinstance(body, list):
            body = [body]
        body = [_encode(i) for i in body]
        body = dill.dumps(body)
        from tornado import httpclient
        http_client = httpclient.AsyncHTTPClient()
        request = httpclient.HTTPRequest(
            url, body=body, method="POST", headers=headers)
        response = yield http_client.fetch(request)
        return response

    def _sync(body):
        body = _encode(body)
        import requests
        return requests.post(url, data=body, headers=headers)

    if asynchronous:
        return _async @ P
    else:
        return _sync @ P

@Pipe
def read_from(url='http://127.0.0.1:7777', tag='', asynchronous=True, headers={}):
    """从URL读取数据.

    从指定URL读取数据,支持同步和异步两种方式。可以读取字符串、二进制数据和Python对象。
    数据会根据内容类型自动解析为相应的Python对象。

    Args:
        url (str): 要读取数据的URL地址,默认为'http://127.0.0.1:7777'
        tag (str): URL路径标签,会被添加到URL末尾,默认为空
        asynchronous (bool): 是否使用异步方式读取,默认为True
        headers (dict): 请求头信息,默认为空字典

    Returns:
        根据数据类型返回相应的Python对象:
        - 字符串: 返回解码后的字符串
        - JSON: 返回解析后的Python对象
        - 二进制: 返回解析后的Python对象或原始二进制数据
        - 异步模式下返回Future对象

    Example::
        
        # 同步读取
        data = read_from('http://api.example.com', asynchronous=False)
        print(data)

        # 异步读取
        future = read_from('http://api.example.com')
        data = yield future
        
        # 带标签读取
        data = read_from('http://api.example.com', tag='users')
        
        # 自定义请求头
        headers = {'Authorization': 'Bearer token123'}
        data = read_from('http://api.example.com', headers=headers)

        # 在管道中使用
        'http://api.example.com' >> read_from >> print
    """
    headers.update({'User-Agent': 'deva'})
    if tag:
        url += quote(tag)

    def _encode(body):
        if not isinstance(body, bytes):
            try:
                body = json.dumps(body, ensure_ascii=False)
            except TypeError:
                body = dill.dumps(body)
        return body

    def _loads(body):
        """解析从web端口提交过来的数据.

        可能的数据有字符串和二进制,
        字符串可能是直接字符串,也可能是json编码后的字符串
        二进制可能是图像等直接可用的二进制,也可能是dill编码的二进制pyobject
        """
        try:
            body = json.loads(body)
        except TypeError:
            body = dill.loads(body)
        except ValueError:
            body = body.decode('utf-8')
        finally:
            return body

    @gen.coroutine
    def _async():
        from tornado import httpclient
        http_client = httpclient.AsyncHTTPClient()
        request = httpclient.HTTPRequest(
            url, method="GET", headers=headers)
        response = yield http_client.fetch(request)
        body = dill.loads(response.body)
        return body

    def _sync():
        import requests
        body = requests.get(url, headers=headers)
        body = _loads(body)
        return body

    if asynchronous:
        return _async()
    else:
        return _sync()

@Pipe
def sample(samplesize=5):
    """从序列中取出随机的n个数据

    从字符串 列表 字典 生成器等iterable中获取随机的n个数值，不加括号调用时，默认返回5个值

    Args:
        samplesize: 获取的数量 (default: {5})

    Returns:
        iterable中的随机n个值，当n大于iterable长度时，只返回iterable长度的数
        list

    Examples:

        10|range|sample
        10|range|sample(3)
    """
    def _(iterable):
        import random
        import pandas as pd
        if isinstance(iterable, pd.DataFrame):
            return iterable.sample(samplesize)
        else:
            results = []
            iterator = iter(iterable)
            # Fill in the first samplesize elements:
            try:
                for _ in range(samplesize):
                    results.append(next(iterator))
            except StopIteration:
                pass
                # raise ValueError("Sample larger than population.")
            random.shuffle(results)  # Randomize their positions
            for i, v in enumerate(iterator, samplesize):
                r = random.randint(0, i)
                if r < samplesize:
                    results[r] = v  # at a decreasing rate,
                    # replace random items
            return results

    if isinstance(samplesize, int):
        return _ @ P
    else:
        iterable, samplesize = samplesize, 5
        return _(iterable)


@Pipe
def extract(typ='chinese'):
    """文本中提取特定数据类型的Pipe

    使用正则表达式从字符串中提取特定类型内容

    Args:
        typ: 提取类型，可选,['chinese','numbers','phone','url','email']
        (default: {'chinese'})
            chinese:中文提取
            numbers:整数提取
            phone:手机号提取
            url:网址提取
            email:邮箱提取

    Returns:
        提取到的结果列表
        list

    Examples:
        'ddd 23.4 sddsd345'>>extract('numbers')>>print
        '你好ds34手'>>extract()>>print
        'dff@fmail.cc.ccd123ddd'>>extract('email')>>print
        'ddshttp://baidu.com/fds dfs'>>extract('url')>>print

        [23.4, 345]
        ['你好', '手']
        ['dff@fmail.cc.ccd']
        ['http://baidu.com/fds']

    """
    import re

    url_regex = re.compile(
        r'(?:(?:https?|ftp|file)://|www\.|ftp\.)[-A-Z0-9+&@#/%=~_|$?!:,.]*[A-Z0-9+&@#/%=~_|$]', re.IGNORECASE)
    email_regex = re.compile(
        r'([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4})', re.IGNORECASE)

    def _(text: str) -> list:
        if typ == 'chinese':
            return re.findall(r"[\u4e00-\u9fa5]+", text)
        elif typ == 'numbers' or typ == 'number':
            return re.findall(
                r"[+-]?\d+\.*\d*", text
            ) >> pmap(lambda x:
                      float(x) if '.' in x else int(x)) >> ls
        elif typ == 'table':
            import pandas as pd
            return pd.read_html(text)
        elif typ == 'url':
            return [x for x in url_regex.findall(text)]
        elif typ == 'email':
            return [x for x in email_regex.findall(text)]
        elif typ == 'tags':
            import jieba.analyse
            return jieba.analyse.extract_tags(text, 20)

    return _ @ P


@P
def get_instances_by_class(cls):
    """获取指定类的所有实例对象

    使用gc模块遍历所有对象,返回指定类的实例。

    Args:
        cls: 要查找实例的类

    Returns:
        生成器,产生所有找到的实例对象

    Examples:
        >>> class MyClass:
        ...     pass
        >>> obj1 = MyClass()
        >>> obj2 = MyClass() 
        >>> list(get_instances_by_class(MyClass))
        [<__main__.MyClass object at 0x...>, <__main__.MyClass object at 0x...>]
        
        >>> # 查找所有Stream实例
        >>> from deva import Stream
        >>> streams = get_instances_by_class(Stream)>>ls
        >>> print(len(streams))  # 输出找到的Stream实例数量
        2
    """
    import gc
    for obj in gc.get_objects():
        if isinstance(obj, cls):
            yield obj

@P
def truncate(text, max_length=20):
    """截断内容超过指定长度的文本"""
    return text if len(text) <= max_length else text[:max_length] + "..."

# %%转换内置函数为pipe
for i in builtins.__dict__.copy():
    if callable(builtins.__dict__.get(i)):
        f = 'to_' + i
        builtins.__dict__[f] = Pipe(builtins.__dict__[i])


ls = list @ P
ll = ls
abs = P(abs)
dir = P(dir)
type = P(type)
help = P(help)
eval = P(eval)
format = P(format)
hash = P(hash)
id = P(id)
input = P(input)
iter = P(iter)
len = P(len)
max = P(max)
min = P(min)
print = P(print)
range = P(range)
sum = P(sum)

to_bytes = P(bytes)
to_dict = P(dict)
to_float = P(float)
to_int = P(int)
to_list = P(list)
to_set = P(set)
to_str = P(str)
# zip = P(zip)
# 这种情况会导致isinstanced等非直接调用方法失败


@P
def to_json(r):
    if hasattr(r, 'json'):
        return r.json()
    elif hasattr(r, 'to_json'):
        return r.to_json()
    else:
        return json.loads(r)


@Pipe
def call_method(mkey):
    "call method by a method key"

    def _cm(obj):
        for method in dir(obj):
            if callable(getattr(obj, method)) and mkey in method:
                return getattr(obj, method)()

    if isinstance(mkey, str):
        return _cm @ P
    else:
        obj, mkey = mkey, 'json'
        return _cm(obj)


cm = call_method


@Pipe
def sliding_window(qte: int = 2):
    """在可迭代对象上创建滑动窗口

    对输入的可迭代对象创建一个固定大小的滑动窗口,每次移动一个位置。
    窗口大小由qte参数指定,默认为2。

    Args:
        qte (int): 滑动窗口的大小,默认为2

    Returns:
        generator: 返回一个生成器,每次生成一个元组,包含当前窗口内的元素

    Examples:
        >>> [1,2,3,4] >> sliding_window(2) >> to_list
        [(1, 2), (2, 3), (3, 4)]

        >>> range(5) >> sliding_window(3) >> to_list  
        [(0, 1, 2), (1, 2, 3), (2, 3, 4)]

        >>> "abcd" >> sliding_window() >> to_list
        [('a', 'b'), ('b', 'c'), ('c', 'd')]

        >>> # 可以配合其他管道操作使用
        >>> range(100) >> sample(10) >> sliding_window() >> pmap(sum) >> max
        195  # 示例结果,实际值可能不同
    """
    def _window(iterable):
        i = qte
        it = iter(iterable)
        result = tuple(islice(it, i))
        if len(result) == i:
            yield result
        for elem in it:
            result = result[1:] + (elem,)
            yield result

    if isinstance(qte, int):
        return _window @ P
    else:
        iterable, qte = qte, 2
        return _window(iterable)

sw = sliding_window

if __name__ == "__main__":
    import doctest
    doctest.testfile('../README.rst')
