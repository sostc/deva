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
