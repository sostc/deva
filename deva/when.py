import os
import atexit
from .bus import log
from .core import Stream
import datetime
from tornado import gen
import time
from typing import Union


"""定时任务和事件调度模块

本模块提供了定时任务调度和事件处理的功能。主要包含:

- exit(): 进程退出时发送信号
- convert_interval(): 转换时间间隔格式
- scheduler: 定时任务调度流

示例
-------
# 基本使用
>>> from deva import when

# 退出事件处理
>>> when('exit').then(lambda: print('bye'))  # 进程退出时打印

# 创建调度器
>>> s = scheduler()  # 创建调度器实例

# 定时任务示例
# 1. 间隔执行
>>> when.scheduler().add_job(lambda: print('hello'), seconds=5)  # 每5秒打印一次
>>> s.add_job(lambda: print('每分钟执行'), minutes=1)  # 每分钟执行一次

# 2. 定时执行
>>> s.add_job(lambda: print('每天9点执行'), trigger='cron', hour=9)  # 每天9点执行

# 3. 延迟执行
>>> s.add_job(lambda: print('5秒后执行一次'), run_date=datetime.datetime.now() + datetime.timedelta(seconds=5))  # 延迟5秒执行一次

# 任务管理
>>> s.get_jobs()  # 获取所有已添加的任务
>>> s.remove_job('job_1')  # 移除指定任务

参见
--------
deva.core.Stream : 基础流处理类
deva.bus : 消息总线模块
"""

@atexit.register
def exit():
    """进程退出时发信号到log.

    Examples:
    ----------
    when('exit',source=log).then(lambda :print('bye bye'))
    """
    #

    return 'exit' >> log


def convert_interval(interval: Union[str, int, float]) -> float:
    """将不同格式的时间间隔转换为秒数

    Args:
        interval: 时间间隔，可以是字符串格式（如'1h'）或数字（秒）

    Returns:
        float: 转换后的秒数
    """
    if isinstance(interval, str):
        import pandas as pd
        interval = pd.Timedelta(interval).total_seconds()
    return float(interval)


@Stream.register_api(staticmethod)
class scheduler(Stream):
    """定时流.

    一个基于apscheduler的定时任务调度器,可以按照固定时间间隔执行任务并将结果放入流中。

    示例:
    -------
    s = scheduler()  # 创建调度器
    s.add_job(name='hello',seconds=5,start_date='2019-04-03 09:25:00')  # 添加任务
    s.get_jobs()>>pmap(lambda x:x.next_run_time)>>to_list  # 获取所有任务的下次执行时间

    con = s.map(lambda x:
       match(x,
            'open',lambda x:x>>warn,
             'hello',lambda x:x>>warn,
             ANY,'None',
            ))

    s.add_job(func=lambda :print('yahoo'),seconds=5)  # 添加简单的打印任务

    参数:
    -------
    weeks (int): 等待的周数
    days (int): 等待的天数  
    hours (int): 等待的小时数
    minutes (int): 等待的分钟数
    seconds (int): 等待的秒数
    start_date (datetime|str): 任务开始时间
    end_date (datetime|str): 任务结束时间
    timezone (datetime.tzinfo|str): 时区设置
    jitter (int|None): 任务执行时间的随机偏移量(秒)
    """

    def __init__(self, start=True, **kwargs):
        """初始化调度器

        Args:
            start (bool): 是否立即启动调度器
            **kwargs: 其他参数
        """
        from apscheduler.schedulers.tornado import TornadoScheduler
        from apscheduler.executors.pool import ThreadPoolExecutor
        import pytz

        self._scheduler = TornadoScheduler(
            timezone=pytz.timezone('Asia/Shanghai'),
            executors={'default': ThreadPoolExecutor(20)},
            job_defaults={
                'coalesce': False,
                'max_instances': 1  # 相同job重复执行与否的判断，相同job最多同时多少个实例
            }
        )
        super(scheduler, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def start(self):
        """启动调度器"""
        if self.stopped:
            self.stopped = False
        self._scheduler.start()

    def stop(self):
        """停止调度器"""
        self._scheduler.shutdown()
        self.stopped = True

    def add_job(self, func, name=None, **kwargs):
        """添加定时任务

        Args:
            func: 要执行的函数
            name: 任务名称,也作为任务ID
            **kwargs: 其他调度参数

        Returns:
            Job: 添加的任务对象

        示例:
            i.add_job(name='hello',func = lambda x:'heoo',
            seconds=5,start_date='2019-04-03 09:25:00')
        """
        return self._scheduler.add_job(
            func=lambda: self._emit(func()),
            name=name,
            id=name,
            trigger='interval',
            **kwargs)

    def emit(self, x, asynchronous=None):
        """发送数据到流中

        Args:
            x: 要发送的数据
            asynchronous: 是否异步执行

        Returns:
            Job: 添加的任务对象
        """
        return self.add_job(**x)

    def remove_job(self, name):
        """移除指定名称的任务

        Args:
            name: 要移除的任务名称

        Returns:
            bool: 是否成功移除
        """
        return self._scheduler.remove_job(job_id=name)

    def get_jobs(self,):
        """获取所有任务列表

        Returns:
            list: 所有任务对象列表
        """
        return self._scheduler.get_jobs()

@Stream.register_api(staticmethod)
class timer(Stream):
    """按照时间间隔执行函数并将返回值放入流.

    定时器类,按照指定的时间间隔重复执行函数,并将函数返回值发送到数据流中。

    参数:
        interval (int/float): 执行时间间隔,单位为秒,默认1秒
        ttl (int/float): 定时器生命周期,超过后自动停止,默认None表示永不停止
        start (bool): 是否在创建后立即启动,默认False
        func (callable): 要执行的函数,默认返回当前秒数
        thread (bool): 是否在线程池中执行函数,默认False
        threadcount (int): 线程池大小,默认5个线程
        ensure_io_loop (bool): 是否确保IO循环存在,默认True
        **kwargs: 传递给父类的额外参数

    示例:
        # 每秒打印当前时间
        timer(interval=1, func=lambda: datetime.now(), start=True)

        # 在线程池中每5秒执行一次耗时操作
        timer(interval=5, func=heavy_task, thread=True, threadcount=3)
    """

    def __init__(self,
                 interval=1,
                 ttl=None,
                 start=False,
                 func=lambda: datetime.datetime.now().second,
                 thread=False,
                 threadcount=5,
                 ensure_io_loop=True,
                 **kwargs):

        self.interval = convert_interval(interval)  # 转换并存储时间间隔
        self.func = func  # 存储要执行的函数
        self.ttl = convert_interval(ttl)  if ttl else None# 转换并存储生命周期
        if thread:  # 如果使用线程池则创建线程池
            from concurrent.futures import ThreadPoolExecutor
            self.thread_pool = ThreadPoolExecutor(threadcount)

        super(timer, self).__init__(ensure_io_loop=ensure_io_loop, **kwargs)
        self.stopped = True  # 初始状态为停止
        if start:  # 如果需要自动启动则调用start()
            self.start()

    @gen.coroutine
    def run(self):
        """定时器主循环,负责按照间隔执行函数"""
        while True:
            # 检查是否超过生命周期
            if self.ttl and time.time() - self._start_time > self.ttl:
                self.stop()

            # 根据配置选择在线程池或主线程中执行函数
            if self.thread:
                self.thread_pool.submit(lambda: self.emit(self.func()))
            else:
                self.emit(self.func())
            yield gen.sleep(self.interval)  # 等待到下一次执行时间
            if self.stopped:  # 如果已停止则退出循环
                break

    def start(self):
        """启动定时器"""
        self._start_time = time.time()  # 记录启动时间
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.run)  # 将主循环加入事件循环

    def stop(self):
        """停止定时器"""
        self.stopped = True


class when(object):
    """当某个事件发生时执行指定操作的类

    该类用于监听数据流中的事件,当满足条件时执行相应的回调函数。
    可以通过字符串匹配或自定义函数来定义触发条件。

    参数:
    -------
    occasion : str或callable
        触发条件,可以是字符串或函数:
        - 字符串: 当数据流中的值包含该字符串时触发
        - 函数: 接收数据流中的值作为输入,返回布尔值表示是否触发
    source : Stream, 可选
        数据源流,默认为全局日志流log

    示例:
    -------
    # 字符串匹配方式
    when('open').then(lambda :print('开盘啦'))

    # 函数判断方式 
    when(lambda x:x>2).then(lambda x:print(x,'x大于二'))
    """

    def __init__(self, occasion, source=log):
        self.occasion = occasion  # 存储触发条件
        self.source = source  # 存储数据源流

    def then(self, func, *args, **kwargs):
        """设置触发时要执行的回调函数
        
        参数:
        -------
        func : callable
            要执行的回调函数
        *args, **kwargs : 
            传递给回调函数的额外参数

        返回:
        -------
        Sink
            返回sink对象,用于接收数据流
        """
        if callable(self.occasion):  # 如果是函数条件,传入数据值作为参数
            return self.source.filter(self.occasion).sink(
                lambda x: func(x, *args, **kwargs))
        else:  # 如果是字符串条件,只执行回调不传参
            return self.source.filter(lambda x: self.occasion in str(x)).sink(
                lambda x: func(*args, **kwargs))

when('exit', source=log).then(lambda: print('bye bye,', os.getpid()))
