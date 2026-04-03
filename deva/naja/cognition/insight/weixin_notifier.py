"""
Weixin Notifier - 通过 openclaw-weixin 发送复盘报告到微信

原理：
  openclaw gateway 已连接微信账号，通过以下命令发消息：
    openclaw agent --session-id <session_id> --message <text> --deliver
  session_id 从 ~/.openclaw/agents/main/sessions/sessions.json 里读取。

用法：
    from deva.naja.cognition.insight.weixin_notifier import WeixinNotifier
    notifier = WeixinNotifier()
    notifier.send("你好，这是一条测试消息")
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Optional

log = logging.getLogger(__name__)

# 爸爸的微信 session ID（从 openclaw sessions.json 读取，固定值）
_WEIXIN_SESSION_ID = "d1e9cecf-6a46-45c2-9357-f476966c7cca"

# openclaw CLI 候选路径（shutil.which 找不到时的兜底）
_OPENCLAW_CLI_FALLBACKS = [
    os.path.expanduser("~/.npm-global/bin/openclaw"),
    "/usr/local/bin/openclaw",
    "/opt/homebrew/bin/openclaw",
]

# 微信消息最大长度（超出则截断）
_MAX_LEN = 2000


def _find_openclaw() -> Optional[str]:
    """找到 openclaw 脚本的绝对路径，找不到返回 None"""
    import shutil
    found = shutil.which("openclaw")
    if found:
        return found
    for c in _OPENCLAW_CLI_FALLBACKS:
        if os.path.isfile(c):
            return c
    return None


class WeixinNotifier:
    """通过 openclaw-weixin 发送文本消息到微信

    使用 openclaw agent --session-id --deliver 命令，无需直接调用底层 API。
    """

    def __init__(self, session_id: str = _WEIXIN_SESSION_ID):
        self.session_id = session_id

    def send(self, text: str, timeout: int = 60) -> bool:
        """发送文本消息到微信

        Args:
            text: 消息内容（不超过 2000 字，超出自动截断）
            timeout: 命令超时秒数

        Returns:
            True = 发送成功，False = 发送失败
        """
        # 截断
        if len(text) > _MAX_LEN:
            text = text[:_MAX_LEN - 20] + "\n...(消息已截断)"

        try:
            node_path = _find_node()
            openclaw_path = _find_openclaw()  # 绝对路径或 None

            if node_path and openclaw_path:
                # openclaw 是 node script，显式用绝对路径的 node 来执行
                cmd = [node_path, openclaw_path,
                       "agent",
                       "--session-id", self.session_id,
                       "--message", text,
                       "--deliver"]
            else:
                # 退路：直接调 openclaw，希望 PATH 里有 node
                cmd = ["openclaw",
                       "agent",
                       "--session-id", self.session_id,
                       "--message", text,
                       "--deliver"]

            log.info(f"[WeixinNotifier] 发送微信消息 session={self.session_id}, len={len(text)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                log.info(f"[WeixinNotifier] 发送成功")
                return True
            else:
                log.warning(
                    f"[WeixinNotifier] 发送失败 rc={result.returncode} "
                    f"stderr={result.stderr[:200]}"
                )
                return False
        except subprocess.TimeoutExpired:
            log.warning(f"[WeixinNotifier] 命令超时 ({timeout}s)")
            return False
        except FileNotFoundError as e:
            log.error(f"[WeixinNotifier] 命令不存在: {e}")
            return False
        except Exception as e:
            log.error(f"[WeixinNotifier] 发送异常: {e}", exc_info=True)
            return False


def _find_node() -> Optional[str]:
    """找到 node 可执行文件路径"""
    candidates = [
        "/opt/homebrew/bin/node",
        "/usr/local/bin/node",
        "/usr/bin/node",
    ]
    import shutil
    if shutil.which("node"):
        return "node"
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _strip_markdown(text: str) -> str:
    """简单去除 Markdown 格式符号，保留可读纯文字"""
    import re
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'^-{3,}$', '──────────', text, flags=re.MULTILINE)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def get_weixin_notifier() -> Optional[WeixinNotifier]:
    """获取 WeixinNotifier 单例"""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = WeixinNotifier()
    return _notifier_instance


_notifier_instance: Optional[WeixinNotifier] = None


def _strip_markdown(text: str) -> str:
    """简单去除 Markdown 格式符号，保留可读纯文字"""
    import re
    # 去除 ## 标题
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # 去除 **加粗**
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # 去除 *斜体*
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # 去除 `代码`
    text = re.sub(r'`(.+?)`', r'\1', text)
    # 去除 --- 分割线
    text = re.sub(r'^-{3,}$', '──────────', text, flags=re.MULTILINE)
    # 去除 _斜体_
    text = re.sub(r'_(.+?)_', r'\1', text)
    # 多个空行压缩成一个
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def get_weixin_notifier() -> Optional[WeixinNotifier]:
    """获取 WeixinNotifier 单例（如果 openclaw 不可用则返回 None）"""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = WeixinNotifier()
    return _notifier_instance


_notifier_instance: Optional[WeixinNotifier] = None
