"""
服务器数据同步模块
功能：
- 从远程服务器 (ai.secsay.com) 获取市场数据
- 本地数据缺失时自动补全
- 支持 A股题材、美股热点、高分新闻、金十要闻
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.error
import socket

log = logging.getLogger(__name__)

# 服务器配置
SERVER_HOST = "ai.secsay.com"
SERVER_PORT = 8080
SERVER_BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# 超时设置
DEFAULT_TIMEOUT = 10  # 秒


def _http_get(path: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[dict]:
    """向服务器发送 GET 请求"""
    url = f"{SERVER_BASE_URL}{path}"
    try:
        req = urllib.request