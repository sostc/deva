"""市场热点服务器同步兼容入口。

实际同步实现已收口到 state/system/server_sync_handler.py。保留本模块是为了
兼容旧 import 路径，避免残缺实现导致整个包无法编译。
"""

from deva.naja.state.system.server_sync_handler import (  # noqa: F401
    ServerDataSyncHandler,
    get_cn_events_from_server_or_local,
    get_jin10_news_from_server_or_local,
    get_news_from_server_or_local,
    get_us_events_from_server_or_local,
)
