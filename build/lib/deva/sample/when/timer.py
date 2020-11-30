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
