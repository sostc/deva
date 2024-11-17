from deva import *

# bus中的证书进行乘2后打印日志
bus.filter(lambda x: isinstance(x, int)).map(lambda x: x*2) >> log
# bus中来的原始数据全部打印报警
bus >> warn

Deva.run()
