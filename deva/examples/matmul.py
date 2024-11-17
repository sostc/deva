"""@ 符号用法.

    @符号可以跟在一个同步或者异步函数后面，将函数立即产生基因突变

    1. 如果@符号后面的对象是一个流对象，当前表达式返回一个新函数，新函数执行结果会立即进入流，可以在流上面配置后续的各种计算
    2. 如果@富豪后面是一个P，当前表达式返回的是一个Pipe化的函数，新函数可以支持管道操作


"""

from deva import *

# 创建流，并且对流中进来的数据*2后打印
s = Stream()
s.map(lambda x: x*2).sink(print)

# 创建一个异步函数，sleep2秒后返回数值123


async def a_foo():
    import asyncio
    await asyncio.sleep(2)
    return 123


# a_foo@s会返回一个新函数
f = a_foo@s
# 异步函数a_foo在结果返回后，会立即进入s中
f()


# 创建同步函数
def s_foo(x):
    return x*2


# 返回一个新函数，会把结果发到s中
sf = s_foo@s
sf(234)

# s_foo返回一个管道函数，可以制止｜方式传参数调用,库倒入时，已经将print管道化，执行过print=print@P
345 | s_foo@P | print

Deva.run()
