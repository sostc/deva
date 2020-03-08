from .core import Stream
from .sources import from_redis
from .endpoint import to_redis

import logging
import os

logger = logging.getLogger(__name__)


def Topic(name='', **kwargs):
    try:
        in_stream = from_redis(
            topics=[name],
            group=str(os.getpid()),
            start=True,
            name=name,
            **kwargs
        )
        out_stream = Stream().to_redis(topic=name)
        in_stream.emit = out_stream.emit

    except Exception as e:
        logger.exception(f'Warn:{e}, start a single process topic ')
        return Stream(name=name)

    return in_stream


# @Stream.register_api()
# class Topic(from_redis):
#     """
#     所有输入都会被作为字典在sqlite中做持久存储，若指定tablename，则将所有数据单独存储一个table。
#     使用方式和字典一样

#     Parameters
#     ----------
#     :tuple:: 输入是元组时，第一个值作为key，第二个作为value。
#     :value:: 输入时一个值时，默认时间作为key，moment.unix(key)可还原为moment时间
#     :dict:: 输入是字典时，更新字典
#     :maxsize::定长字典
#     :name::表名
#     :fname:: 文件路径和文件名
#     :log::日志流

#     Returns
#     ----------
#     是一个流，也是一个字典对象
#     """

#     def __init__(self,  name='', maxsize=None,  **kwargs):
#         super().__init__(topics=[name],
#                          group=str(os.getpid()),
#                          start=True,
#                          name=name,
#                          **kwargs)
#         self.out_stream = Stream().to_redis(topic=[name])

#     def emit(self, x, asynchronous=False):
#         self.out_stream.emit(x, asynchronous=asynchronous)
