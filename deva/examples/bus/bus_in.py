from deva import *

# 每隔一秒写入秒数到bus中
timer(start=True) >> bus
# 打印来自bus到数据
bus >> log
Deva.run()
