#!/usr/bin/env python

"""Module enabling a sh like infix syntax (using pipes)."""
from tornado import gen
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

try:
    import builtins
except ImportError:
    import __builtin__ as builtins


__all__ = [
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
    'abs', 'type', 'll', 'pslice',
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
]


_io_loops = []


def get_io_loop(asynchronous=None):
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
    """
    Represent a Pipeable Element.

    Described as :
    first = Pipe(lambda iterable: next(iter(iterable)))
    and used as :
    print [1, 2, 3] | first
    printing 1

    Or represent a Pipeable Function :
    It's a function returning a Pipe
    Described as :
    pfilter = Pipe(lambda iterable, pred: (pred(x) for x in iterable))
    and used as :
    print [1, 2, 3] | pfilter(lambda x: x * 2)
    # 2, 4, 6
    """

    def __init__(self, func):
        """decorater 初始化."""
        self.func = func
        functools.update_wrapper(self, func)

    def run_async(self, asyncfunc, callback):
        self.futs = gen.convert_yielded(asyncfunc)
        self.loop = get_io_loop()
        self.loop.add_future(self.futs, lambda x: callback(x.result()))

    def __ror__(self, other):
        """左边的 |."""
        if isinstance(other, gen.Awaitable):
            self.run_async(other, self.func)
        else:
            return self.func(other)

    def __rrshift__(self, other):
        """左边的 >>."""
        # 左边如果支持sink方法，则变为左边sin右边的函数
        if hasattr(other, 'sink'):
            return other.sink(self.func)
        else:
            return self.func(other)

    def __rmatmul__(self, other):
        """左边的 @."""
        return self.func(other)

    def __lshift__(self, other):  # 右边的<<
        """右边的 <<."""
        return self.func(other)

    def __call__(self, *args, **kwargs):
        """像正常函数一样使用使用."""
        return self.func(*args, **kwargs)

    def __add__(self, other):
        """Function composition: (a + b + c)(x) -> c(b(a(x)))."""
        return Pipe(lambda *args, **kwargs: other(self(*args, **kwargs)))

    # def __repr__(self):
    #     """转化成Pipe对象后的repr."""
    #     return f'<func {self.func.__module__}.{self.func.__name__}@P>'


@Pipe
def P(func):
    """
    [1,2,3]>>print@P
    """
    if not isinstance(func, Pipe):  # 防止pipe被重复管道化
        return Pipe(func)
    else:
        return func


@Pipe
def to_dataframe(dct, orient='index'):
    """orient = 'index'
                orient = 'columne'"""

    import pandas as pd
    return pd.DataFrame.from_dict(dct, orient=orient)


@Pipe
def head(qte: int = 5):
    "Yield qte of elements in the given iterable."
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
    """Only yield unique items. Use a set to keep track of duplicate data."""
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
    """Deduplicate consecutive duplicate values."""
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
    """Returns True if ALL elements in the given iterable are true for the
    given pred function"""
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
    """Returns True if ALL elements in the given iterable are true for the
    given pred function"""
    def _(iterable):
        return builtins.all(pred(x) for x in iterable)

    return _ @ P


@Pipe
def any(pred):
    """Returns True if ANY element in the given iterable is True for the
    given pred function"""
    def _(iterable):
        return builtins.any(pred(x) for x in iterable)

    return _ @ P


@Pipe
def average(iterable):
    """Build the average for the given iterable, starting with 0.0 as seed
    Will try a division by 0 if the iterable is empty...
    """
    total = 0.0
    qte = 0
    for element in iterable:
        total += element
        qte += 1
    return total / qte


@Pipe
def count(iterable):
    "Count the size of the given iterable, walking thrue it."
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
    # permutations('ABCD', 2) --> AB AC AD BA BC BD CA CB CD DA DB DC
    # permutations(range(3)) --> 012 021 102 120 201 210
    def _(iterable):
        for x in itertools.permutations(iterable, r):
            yield x

    return _ @ P


@Pipe
def netcat(host, port):
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
    def _(to_send):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.connect((host, port))
            for data in to_send | traverse:
                s.send(data.encode("utf-8"))

    return _ @ P


@Pipe
def traverse(args):
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
    def _(to_send):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.connect((host, port))
            s.send(dill.dumps(to_send))
            s.send(b'\n')

    return _ @ P


@Pipe
def concat(separator=", "):
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

    Exsapmles:
        123>>write_to_file('tpm.txt')
        b'abc'>>write_to_file('music.mp3','ab+')
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
    def _(iterable):
        return (func(**iterable) if isinstance(iterable, dict) else
                func(*iterable) if hasattr(iterable, '__iter__') else
                func(iterable))

    return _ @ P


@Pipe
def append(y):
    """追加元素到列表尾部，[]>>t('c')>>t('b') == ['c', 'b']"""
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
def readlines(fn):
    """ 按行读入文本文件，mode参数为读到方式 'xxx.log'>>readlines()>>tail(2)"""
    with open(fn, 'r') as f:
        for line in f:
            yield line


@Pipe
def read(fn):
    """ 按行读入文本文件，mode参数为读到方式 'xxx.log'>>read()"""
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
def post_to(url='http://127.0.0.1:7777', asynchronous=True, headers={}):
    """ post a str or bytes or pyobject to url.

    str:直接发送
    bytes:直接发送
    pyobject:dill序列化后发送
    发送方式use async http client,Future对象，jupyter中可直接使用
    jupyter 之外需要loop = IOLoop.current(instance=True)，loop.start()

    Examples::

        {'a':1}>>post_to(url)
        {'a':1}>>post_to(url,asynchronous=False)

    """
    def _encode(body):
        if not isinstance(body, bytes):
            try:
                body = json.dumps(body, ensure_ascii=False)
            except TypeError:
                body = dill.dumps(body)
        return body

    @gen.coroutine
    def _async(body):
        body = _encode(body)
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
    import gc
    for obj in gc.get_objects():
        if isinstance(obj, cls):
            yield obj


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
def cm(mkey):
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


call_method = cm


if __name__ == "__main__":
    import doctest
    doctest.testfile('README.md')
