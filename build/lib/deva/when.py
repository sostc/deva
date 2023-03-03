
import os
import atexit
from .bus import log
from .core import Stream
import datetime
from tornado import gen
import time


@atexit.register
def exit():
    """进程退出时发信号到log.

    Examples:
    ----------
    when('exit',source=log).then(lambda :print('bye bye'))
    """
    #

    return 'exit' >> log


def convert_interval(interval):
    if isinstance(interval, str):
        import pandas as pd
        interval = pd.Timedelta(interval).total_seconds()
    return interval


@Stream.register_api(staticmethod)
class scheduler(Stream):
    """定时流.

    Examples:
    s = scheduler()
    s.add_job(name='hello',seconds=5,start_date='2019-04-03 09:25:00')
    s.get_jobs()>>pmap(lambda x:x.next_run_time)>>to_list

    con = s.map(lambda x:
       match(x,
            'open',lambda x:x>>warn,
             'hello',lambda x:x>>warn,
             ANY,'None',
            ))

    s.add_job(func=lambda :print('yahoo'),seconds=5)

    Parameters:
    weeks (int) – number of weeks to wait
    days (int) – number of days to wait
    hours (int) – number of hours to wait
    minutes (int) – number of minutes to wait
    seconds (int) – number of seconds to wait
    start_date (datetime|str) – starting point for the interval calculation
    end_date (datetime|str) – latest possible date/time to trigger on
    timezone (datetime.tzinfo|str) – to use for the date/time calculations.
    jitter (int|None) – advance or delay  by jitter seconds at most.

    """

    def __init__(self, start=True, **kwargs):
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
        if self.stopped:
            self.stopped = False
        self._scheduler.start()

    def stop(self):
        self._scheduler.shutdown()
        self.stopped = True

    def add_job(self, func, name=None, **kwargs):
        """增加任务.

        Example:
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
        return self.add_job(**x)

    def remove_job(self, name):
        return self._scheduler.remove_job(job_id=name)

    def get_jobs(self,):
        return self._scheduler.get_jobs()


@Stream.register_api(staticmethod)
class timer(Stream):
    """按照时间间隔执行函数并将返回值放入流.

    ::func:: func to gen data，
    ::interval:: func to run interval time
    ::thread:: func execute in threadpool
    ::threadcount:: if thread ,this is threadpool count
    """

    def __init__(self,
                 interval=1,
                 ttl=None,
                 start=False,
                 func=lambda: datetime.datetime.now().second,
                 thread=False,
                 threadcount=5,
                 **kwargs):

        self.interval = convert_interval(interval)
        self.func = func
        self.ttl = convert_interval(ttl)
        self.thread = thread
        if self.thread:
            from concurrent.futures import ThreadPoolExecutor
            self.thread_pool = ThreadPoolExecutor(threadcount)

        super(timer, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    @gen.coroutine
    def run(self):
        while True:
            if self.ttl and time.time() - self._start_time > self.ttl:
                self.stop()

            if self.thread:
                self.thread_pool.submit(lambda: self._emit(self.func()))
            else:
                self._emit(self.func())
            yield gen.sleep(self.interval)
            if self.stopped:
                break

    def start(self):
        self._start_time = time.time()
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.run)

    def stop(self):
        self.stopped = True


class when(object):
    """when a  occasion(from source) appear, then do somthing .

    Examples:
    --------
    when('open').then(lambda :print(f'开盘啦'))

    when(lambda x:x>2).then(lambda x:print(x,'x大于二'))
    """

    def __init__(self, occasion, source=log):
        self.occasion = occasion
        self.source = source
        # 接受来自总线的信号

    def then(self, func, *args, **kwargs):
        if callable(self.occasion):  # 携带上下文给后面的任务，检查发生的函数，函数输入为流里的值，输出为布尔
            return self.source.filter(self.occasion).sink(
                lambda x: func(x, *args, **kwargs))
        else:  # 不处理流的值，不携带上下文
            return self.source.filter(lambda x: self.occasion in str(x)).sink(
                lambda x: func(*args, **kwargs))


when('exit', source=log).then(lambda: print('bye bye,', os.getpid()))
