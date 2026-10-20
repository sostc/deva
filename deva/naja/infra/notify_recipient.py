"""通知接收人（手机号）的**唯一入口** —— 任何地方都不许硬编码号码。

============================================================================
为什么要有这个文件
============================================================================

仓库 ``github.com/sostc/deva`` 是**公开的**（``private: false``）。而手机号
曾硬编码在 8 个 .py 与 2 个根目录文档里 —— 等于长期公开暴露。

本模块把「往哪个号码发」收敛成一个函数，并把**取不到**的情况显式化：

    1. 环境变量 ``NAJA_NOTIFY_PHONE``
    2. 本机文件 ``~/.naja/notify.json`` 的 ``phone`` 字段（**不入库**）
    3. Naja 内存配置 ``notify.phone``（启动流程 / UI 可设置）
    4. 都没有 → 返回 ``""``

============================================================================
❗第 4 条不许拿硬编码兜底
============================================================================

拿一个写死的号码兜底，等于把「**没配置**」伪装成「**配置好了**」：
换台机器、换个部署，消息会静默发到错误（或无人）的号码上，而日志看起来
一切正常 —— 这正是本项目反复踩的「静默失效」家族。

所以约定：**取不到就留痕并跳过推送**，绝不猜一个号码出来。

用法::

    from deva.naja.infra.notify_recipient import get_notify_phone

    phone = get_notify_phone()
    if not phone:
        log.warning("[X] 未配置通知手机号，跳过推送（设 NAJA_NOTIFY_PHONE 或写 ~/.naja/notify.json）")
        return False
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)

#: 环境变量名
ENV_PHONE = "NAJA_NOTIFY_PHONE"

#: 本机配置文件（不入库）
LOCAL_FILE = Path.home() / ".naja" / "notify.json"

#: 内存配置的 key
CONFIG_KEY = "notify.phone"

#: 额外监听的会话白名单（逗号分隔的号码/identifier）
ENV_CHAT_WHITELIST = "NAJA_IMSG_CHAT_WHITELIST"

#: 缓存：进程内只读一次磁盘，避免每次推送都读文件。
#: 置空（调用 ``reset_cache()``）后可强制重读 —— 测试与热更新用。
_cache: Optional[str] = None
_cache_checked = False

_NON_DIGIT = re.compile(r"[^\d+]")


def normalize_phone(value: Optional[str]) -> str:
    """归一化号码，用于比对（去掉空格/横线/括号，保留 +）。

    ``+8613800000000`` 与 ``13800000000`` 必须判为同一个号码，否则
    「是不是本人发来的」这类白名单判断会因写法不同而漏判。
    """
    if not value:
        return ""
    s = str(value).strip()
    s = _NON_DIGIT.sub("", s)
    s = s.lstrip("+")
    # 剥掉国家码 86：``+8613800000000``（13 位）与 ``13800000000``（11 位）
    # 必须是同一个号码，否则「是不是本人发来的」这类白名单判断会漏判。
    if s.startswith("86") and len(s) == len("86") + 11:
        s = s[2:]
    return s


def _read_local_file() -> str:
    try:
        if not LOCAL_FILE.exists():
            return ""
        data = json.loads(LOCAL_FILE.read_text(encoding="utf-8") or "{}")
        if isinstance(data, dict):
            return str(data.get("phone") or "").strip()
    except Exception as e:
        # ❗读配置失败也要留痕：否则「文件写坏了」表现为「没配置」，无法区分
        log.warning("[notify] 读取 %s 失败（%s: %s），按未配置处理",
                    LOCAL_FILE, type(e).__name__, e)
    return ""


def _read_naja_config() -> str:
    try:
        from deva.naja.config import get_config
        return str(get_config(CONFIG_KEY, "") or "").strip()
    except Exception:
        return ""


def get_notify_phone(refresh: bool = False) -> str:
    """取通知手机号；取不到返回 ``""``（**不猜、不兜底硬编码**）。"""
    global _cache, _cache_checked
    if _cache_checked and not refresh:
        return _cache or ""

    phone = ""
    source = ""
    for value, name in (
        (os.environ.get(ENV_PHONE, ""), f"环境变量 {ENV_PHONE}"),
        (_read_local_file(), f"本机文件 {LOCAL_FILE}"),
        (_read_naja_config(), f"Naja 配置 {CONFIG_KEY}"),
    ):
        v = str(value or "").strip()
        if v:
            phone, source = v, name
            break

    _cache, _cache_checked = phone, True
    if not phone:
        log.warning(
            "[notify] 未配置通知手机号 —— 推送将跳过（三处都没配：%s / %s / %s）",
            ENV_PHONE, LOCAL_FILE, CONFIG_KEY,
        )
    else:
        log.debug("[notify] 通知号码来自 %s", source)
    return phone


def phone_source(refresh: bool = False) -> Tuple[str, str]:
    """返回 ``(号码, 来源说明)``，供诊断页/日志使用（来源不许含号码本身）。"""
    global _cache, _cache_checked
    if refresh:
        _cache_checked = False
    phone = get_notify_phone(refresh=refresh)
    if not phone:
        return "", "未配置"
    if os.environ.get(ENV_PHONE, "").strip():
        return phone, f"环境变量 {ENV_PHONE}"
    if _read_local_file():
        return phone, f"本机文件 {LOCAL_FILE}"
    return phone, f"Naja 配置 {CONFIG_KEY}"


def chat_whitelist() -> Tuple[str, ...]:
    """iMessage 监听白名单（只处理这些会话）。

    默认 = 通知号码本人（避免把群聊/别人发的内容当成指令学进去）；
    额外号码用 ``NAJA_IMSG_CHAT_WHITELIST`` 逗号分隔追加。
    """
    out = []
    phone = get_notify_phone()
    if phone:
        out.append(phone)
    extra = os.environ.get(ENV_CHAT_WHITELIST, "")
    for item in (extra or "").split(","):
        item = item.strip()
        if item:
            out.append(item)
    return tuple(out)


def reset_cache() -> None:
    """清空缓存（测试 / 配置热更新用）。"""
    global _cache, _cache_checked
    _cache, _cache_checked = None, False


__all__ = [
    "get_notify_phone", "phone_source", "chat_whitelist",
    "normalize_phone", "reset_cache",
    "ENV_PHONE", "ENV_CHAT_WHITELIST", "LOCAL_FILE", "CONFIG_KEY",
]
