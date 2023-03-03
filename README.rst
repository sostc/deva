.. image:: https://raw.githubusercontent.com/sostc/deva/master/deva.jpeg
   :target: https://github.com/sostc/deva
   :align: center
   :alt: 518.is


------

The ``deva`` lib makes it easy to write streaming data process pipelines,event driven programing,and run async function.

An example of a streaming process and web view

.. image:: https://raw.githubusercontent.com/sostc/deva/master/streaming.gif
   :target: https://raw.githubusercontent.com/sostc/deva/master/streaming.gif
   :align: center
   :alt: streanming


.. code-block:: python

    # coding: utf-8
    from deva.page import page, render_template
    from deva import *

    # 系统日志监控
    s = from_textfile('/var/log/system.log')
    s1 = s.sliding_window(5).map(concat('<br>'), name='system.log日志监控')
    s.start()


    # 实时股票数据

    s2 = timer(func=lambda: NB('sample')['df'].sample(
        5).to_html(), start=True, name='实时股票数据', interval=1)

    # 系统命令执行
    command_s = Stream.from_process(['ping','baidu.com'])
    s3 = command_s.sliding_window(5).map(concat('<br>'), name='系统持续命令')
    command_s.start()


    s1.webview()
    s2.webview()
    s3.webview()
    
    Monitor().start()
    Deva.run()




Features
--------


License
-------

Copyright spark, 2018-2020.





Install
----------


.. code-block:: python

    pip install deva

or

.. code-block:: python

    pip3 install deva


Sample
------------
<b>如果是在jupyter里执行带码，代码尾部不需要添加Deva.run()
</b>

bus
---------
<b>如果使用bus跨进程，需要安装redis 5.0</b>

.. code-block:: python


    from deva import *

    # 每隔一秒写入秒数到bus中
    timer(start=True) >> bus
    # 打印来自bus到数据
    bus >> log
    Deva.run()

.. code-block:: python


    from deva import *

    # bus中的证书进行乘2后打印日志
    bus.filter(lambda x: isinstance(x, int)).map(lambda x: x*2) >> log
    # bus中来的原始数据全部打印报警
    bus >> warn

    Deva.run()


Crawler
-----------------

.. code-block:: python

    from deva import *

    h = http()
    h.map(lambda r: (r.url, r.html.search('<title>{}</title>')[0])) >> log
    'http://www.518.is' >> h


    s = Stream()
    s.rate_limit(1).http(workers=20).map(lambda r: (
        r.url, r.html.search('<title>{}</title>')[0])) >> warn
    'http://www.518.is' >> s

    Deva.run()



timer
-------------
.. code-block:: python

    from deva import timer, log, Deva, warn

    # 默认每秒执行一次，返回当前秒
    timer(start=True) >> log

    # 3秒返回一个yahoo，随后启动，结果报警warn
    s = timer(func=lambda: 'yahoo', interval=3)
    s.start()

    s >> warn
    # 可用stop方法停止一个定时器
    # s.stop()
    Deva.run()


    # python3 每隔n秒执行.py
    # [2020-03-14 10:31:16.847544] INFO: log: 16
    # WARNING:root:yahoo
    # [2020-03-14 10:31:17.849576] INFO: log: 17
    # [2020-03-14 10:31:18.853488] INFO: log: 18
    # WARNING:root:yahoo
    # [2020-03-14 10:31:19.855116] INFO: log: 19
    # [2020-03-14 10:31:20.859602] INFO: log: 20
    # [2020-03-14 10:31:21.865973] INFO: log: 21
    # WARNING:root:yahoo
    # [2020-03-14 10:31:22.868624] INFO: log: 22


scheduler
------------
.. code-block:: python

    from deva import *

    s = Stream.scheduler()

    # 5秒执行一次的任务，返回yahoo到s中

    s.add_job(func=lambda: 'yahoo', seconds=5)
    # 5秒执行一次的任务，发送yamaha到bus，且返回yamaha到s中

    s.add_job(func=lambda: 'yamaha' >> bus, seconds=5)

    # 返回open到s中，每天执行一次，启动时间9点25
    s.add_job(name='open', func=lambda: 'open', days=1, start_date='2019-04-03 09:25:00')

    # 发送关闭到bus，返回值close放到s中，每天执行一次，15点30开始执行


    def foo():
        '关闭' >> bus
        return 'close'


    s.add_job(name='close', func=foo,
              days=1, start_date='2019-04-03 15:30:00')

    # 打印所有任务
    s.get_jobs() | pmap(lambda x: x.next_run_time) | ls | print

    # 放入s中的所有数据都打印日志
    s >> log

    bus.map(lambda x: x*2) >> warn

    Deva.run()


    # $ python3 time_scheduler/scheduler.py

    # [datetime.datetime(2020, 3, 14, 18, 6, 17, 830399, tzinfo=<DstTzInfo 'Asia/Shanghai' CST+8:00:00 STD>), datetime.datetime(2020, 3, 14, 18, 6, 17, 830947, tzinfo=<DstTzInfo 'Asia/Shanghai' CST+8:00:00 STD>), datetime.datetime(2020, 3, 15, 9, 25, tzinfo=<DstTzInfo 'Asia/Shanghai' CST+8:00:00 STD>), datetime.datetime(2020, 3, 15, 15, 30, tzinfo=<DstTzInfo 'Asia/Shanghai' CST+8:00:00 STD>)]
    # [2020-03-14 10:06:17.835725] INFO: log: yahoo
    # [2020-03-14 10:06:17.839594] INFO: log: yamaha
    # WARNING:root:yamahayamaha
    # [2020-03-14 10:06:22.846482] INFO: log: yahoo
    # [2020-03-14 10:06:22.851722] INFO: log: yamaha
    # WARNING:root:yamahayamaha
    # [2020-03-14 10:06:27.840823] INFO: log: yaho



workers
-------------
.. code-block:: python

    from deva import bus, log, when, Deva

    # 开盘任务
    @bus.route(lambda x: x == 'open')
    def onopen(x):
        'open' >> log

    # 收盘任务
    @bus.route(lambda x: x == 'close')
    def onclose(x):
        'close' >> log

    # 另外一种写法

    when('open', source=bus).then(lambda: print(f'开盘啦'))
    Deva.run()

