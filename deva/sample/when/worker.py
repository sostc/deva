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
