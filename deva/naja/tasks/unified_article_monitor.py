"""
统一文章监控器 - 合并 iMessage 和微信文章学习功能

支持两种渠道：
- iMessage：通过 imsg CLI 监听（chats + history --json，JSONL 输出）
- 微信：通过 OpenClaw gateway(127.0.0.1:18789) 监听，默认关闭
  （OpenClaw 已于 2026-10-02 卸载，启用需 NAJA_WECHAT_ENABLED=1）

两种运行模式：
- 实时监听：持续运行，定期检查新消息
- 单次检查：用于定时任务
"""

import json
import logging
import os
import re
import shutil
import subprocess
import time
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum

import requests

log = logging.getLogger(__name__)

from deva.naja.tasks.article_learner import ArticleLearner
from deva.naja.infra.observability.fleet_registry import KIND_DATASOURCE, probe

# ============== 日志冷却 ==============
# 同一个 key 在 cooldown 秒内只输出一次 WARNING，避免「每分钟一条」的告警刷屏
_WARN_LAST: Dict[str, float] = {}
_WARN_COOLDOWN_SEC = 3600


def _warn_throttled(key: str, message: str, cooldown: int = _WARN_COOLDOWN_SEC):
    """带冷却的 WARNING（同类问题默认 1 小时最多一条）"""
    now = time.time()
    if now - _WARN_LAST.get(key, 0) < cooldown:
        log.debug(message)
        return
    _WARN_LAST[key] = now
    log.warning(message)


def _imsg_bin() -> Optional[str]:
    """定位 imsg CLI，找不到返回 None（注意：正确的命令名是 imsg，不是 imesg）"""
    return shutil.which("imsg")


# 发送 iMessage 通知的函数
def send_notification(text: str) -> bool:
    """发送 iMessage 通知给爸爸（优先 imsg CLI，失败降级 osascript）"""
    phone = getattr(__import__('deva'), '_PHONE', '+86XXXXXXXXXXX')

    imsg = _imsg_bin()
    if imsg:
        try:
            result = subprocess.run(
                [imsg, "send", "--to", phone, "--text", text],
                capture_output=True,
                text=True,
                timeout=20
            )
            if result.returncode == 0:
                _mark_self_sent(text)
                return True
            log.warning(f"[UnifiedMonitor] imsg send 失败: {(result.stderr or '').strip()[:200]}")
        except Exception as e:
            log.warning(f"[UnifiedMonitor] imsg send 异常: {e}")

    # 降级：osascript（对 text 做转义，避免引号破坏脚本）
    try:
        safe = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "Messages"\nsend "{safe}" to buddy "{phone}"\nend tell'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=15
        )
        if result.returncode == 0:
            _mark_self_sent(text)
        return result.returncode == 0
    except Exception as e:
        log.warning(f"[UnifiedMonitor] 发送通知失败: {e}")
        return False


# ============== 渠道类型枚举 ==============
class ChannelType(Enum):
    IMESSAGE = "imessage"
    WECHAT = "wechat"


# ============== 配置常量 ==============
_LEARNING_DIR = Path.home() / ".naja" / "article_learning"
_LEARNING_DIR.mkdir(parents=True, exist_ok=True)

# iMessage 配置
_IMESSAGE_PROCESSED_FILE = _LEARNING_DIR / "processed_messages.json"
# Naja 自己发出去的消息指纹（用于避免「自己发的链接被自己学到」的自循环）
_SELF_SENT_FILE = _LEARNING_DIR / "self_sent_messages.json"

# 只监听这些会话（identifier 匹配，支持子串）
_IMSG_CHAT_WHITELIST = ("+86XXXXXXXXXXX", "+86XXXXXXXXXXX")
# 只处理最近 N 分钟内到达的消息
_IMSG_LOOKBACK_MIN = 5
# 每次每会话拉取的历史条数（只取最近若干条做增量判断）
_IMSG_HISTORY_LIMIT = 20
# processed 集合上限，防止 JSON 无限膨胀
_PROCESSED_MAX = 500

# 微信配置
# OpenClaw（含 18789 gateway）已于 2026-10-02 卸载，端口不再监听。
# 默认关闭该渠道，避免每分钟一条 ConnectionError 噪声。
# 如需恢复：export NAJA_WECHAT_ENABLED=1
_WECHAT_ENABLED = os.environ.get("NAJA_WECHAT_ENABLED", "0").lower() in ("1", "true", "yes")
_WECHAT_GATEWAY_URL = "http://127.0.0.1:18789"
_WECHAT_AUTH_TOKEN = "2a87d7bf09e81ec6a3a5e79a18c80129615b17f90a361daa"
_WECHAT_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {_WECHAT_AUTH_TOKEN}"
}
_WECHAT_BOT_ID = "6fbf95535975-im-bot"
_WECHAT_CURSOR_FILE = _LEARNING_DIR / "wechat_cursor.json"
_WECHAT_PROCESSED_FILE = _LEARNING_DIR / "processed_wechat_ids.json"


# ============== 通用工具函数 ==============
def extract_urls(text: str) -> List[str]:
    """从文本中提取URL"""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    return list(set(urls))  # 去重


def get_processing_emoji() -> str:
    """获取处理中的表情"""
    import random
    emojis = ["🤔", "🔍", "📚", "🧠", "✨"]
    return random.choice(emojis)


def _load_set_from_json(file_path: Path) -> set:
    """从JSON文件加载集合"""
    if file_path.exists():
        with open(file_path, "r") as f:
            return set(json.load(f))
    return set()


def _save_set_to_json(file_path: Path, item: Any):
    """保存项到JSON文件的集合中（保留最近 _PROCESSED_MAX 条，防止无限膨胀）"""
    processed = _load_set_from_json(file_path)
    processed.add(str(item))
    if len(processed) > _PROCESSED_MAX:
        processed = set(list(processed)[-_PROCESSED_MAX:])
    with open(file_path, "w") as f:
        json.dump(list(processed), f)


def _norm_digits(value: Any) -> str:
    """只保留数字，用于号码归一化匹配"""
    return re.sub(r"\D", "", str(value or ""))


def _self_fingerprint(text: str) -> str:
    """消息文本指纹，用于识别 Naja 自己发出去的消息"""
    return "self:" + hashlib.md5((text or "").strip().encode("utf-8")).hexdigest()[:16]


def _mark_self_sent(text: str):
    """记录 Naja 自己发出去的消息，抓取时跳过（防止自循环）"""
    if not text:
        return
    try:
        _save_set_to_json(_SELF_SENT_FILE, _self_fingerprint(text))
    except Exception as e:
        log.debug(f"[iMessage] 记录自发消息失败: {e}")


# ============== iMessage 相关 ==============
def _parse_ts(value: Any) -> Optional[datetime]:
    """解析 ISO8601 时间戳（兼容 Z 后缀 / 小数秒），返回本地朴素时间"""
    if not value:
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().replace(tzinfo=None)


def _imsg_jsonl(args: List[str], timeout: int = 20) -> List[Dict[str, Any]]:
    """
    调用 imsg CLI 并解析 JSONL 输出。

    注意两点历史坑：
    1) 命令名是 imsg，不是 imesg；
    2) imsg 没有 `list` 子命令，只有 chats / history / watch / send / rpc，
       且 --json 输出是「每行一个 JSON 对象」的 JSONL，不是数组，
       也不是 `id|date|chat|text` 的管道分隔格式。
    """
    imsg = _imsg_bin()
    if not imsg:
        _warn_throttled("imsg_missing", "[iMessage] imsg CLI 不存在（PATH 中找不到），跳过文章监听")
        return []

    try:
        proc = subprocess.run(
            [imsg, *args, "--json"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        _warn_throttled("imsg_timeout", f"[iMessage] imsg {' '.join(args)} 超时（{timeout}s）")
        return []
    except Exception as e:
        _warn_throttled("imsg_exec", f"[iMessage] imsg 执行异常: {e}")
        return []

    if proc.returncode != 0:
        _warn_throttled(
            "imsg_rc",
            f"[iMessage] imsg {' '.join(args)} 失败 rc={proc.returncode}: "
            f"{(proc.stderr or '').strip()[:200]}"
        )
        return []

    rows: List[Dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _select_imsg_chat_ids() -> List[int]:
    """选出需要监听的会话 chat id（按号码白名单匹配）"""
    targets = {_norm_digits(w) for w in _IMSG_CHAT_WHITELIST}
    targets = {t for t in targets if t}

    if not targets:
        # 白名单为空时不监听任何会话，避免误听全部会话
        return []

    chat_ids: List[int] = []
    for row in _imsg_jsonl(["chats"]):
        cid = row.get("id")
        if cid is None:
            continue
        ident = _norm_digits(row.get("identifier"))
        name = str(row.get("name") or "").lower()

        hit = False
        if ident:
            # 号码可能带/不带国家码，双向后缀匹配
            hit = any(ident == t or ident.endswith(t) or t.endswith(ident)
                      for t in targets)
        if not hit and name:
            hit = "baba" in name or "spark" in name

        if hit:
            try:
                chat_ids.append(int(cid))
            except (TypeError, ValueError):
                continue
    return chat_ids


@probe(KIND_DATASOURCE, "ds:imessage_monitor", "iMessage 文章监控（imsg CLI）", cadence="定时轮询")
def _check_new_imessage_messages() -> List[Dict[str, Any]]:
    """检查新收到的 iMessage 消息（仅最近 _IMSG_LOOKBACK_MIN 分钟内、非本人发出）"""
    try:
        chat_ids = _select_imsg_chat_ids()
        if not chat_ids:
            log.debug("[iMessage] 未匹配到目标会话")
            return []

        cutoff = datetime.now() - timedelta(minutes=_IMSG_LOOKBACK_MIN)
        self_sent = _load_set_from_json(_SELF_SENT_FILE)
        messages: List[Dict[str, Any]] = []

        for cid in chat_ids:
            rows = _imsg_jsonl([
                "history", "--chat-id", str(cid),
                "--limit", str(_IMSG_HISTORY_LIMIT),
            ])
            for row in rows:
                if row.get("is_from_me"):
                    continue  # 跳过自己发出去的消息

                text = (row.get("text") or "").strip()
                if not text:
                    continue

                # chat.db 里本机发出的消息有时 is_from_me 仍为 False，用指纹兜底
                if _self_fingerprint(text) in self_sent:
                    continue

                msg_time = _parse_ts(row.get("created_at"))
                if msg_time is None or msg_time < cutoff:
                    continue

                messages.append({
                    "id": str(row.get("guid") or row.get("id") or ""),
                    "time": msg_time,
                    "chat": str(cid),
                    "text": text,
                    "channel": ChannelType.IMESSAGE
                })

        return messages

    except Exception as e:
        log.error(f"[iMessage] 检查消息失败: {e}")
        return []


def _send_imessage_reply(text: str):
    """发送iMessage回复"""
    send_notification(text)


def _save_imessage_processed(msg_id: str):
    """保存已处理的iMessage消息ID"""
    _save_set_to_json(_IMESSAGE_PROCESSED_FILE, msg_id)


# ============== 微信相关 ==============
def _load_wechat_cursor() -> str:
    """加载微信上次处理的游标"""
    if _WECHAT_CURSOR_FILE.exists():
        with open(_WECHAT_CURSOR_FILE, "r") as f:
            data = json.load(f)
            return data.get("cursor", "")
    return ""


def _save_wechat_cursor(cursor: str):
    """保存微信游标"""
    with open(_WECHAT_CURSOR_FILE, "w") as f:
        json.dump({"cursor": cursor}, f)


def _fetch_wechat_messages() -> List[Dict[str, Any]]:
    """从微信获取新消息（渠道默认关闭，见 _WECHAT_ENABLED）"""
    if not _WECHAT_ENABLED:
        log.debug("[WeChat] 渠道已关闭（依赖的 OpenClaw gateway 18789 已卸载，"
                  "如需启用请设置 NAJA_WECHAT_ENABLED=1）")
        return []

    try:
        cursor = _load_wechat_cursor()

        response = requests.post(
            f"{_WECHAT_GATEWAY_URL}/v1/channels/openclaw-weixin/{_WECHAT_BOT_ID}/getupdates",
            headers=_WECHAT_HEADERS,
            json={"get_updates_buf": cursor},
            timeout=40
        )

        if response.status_code != 200:
            log.warning(f"[WeChat] API调用失败: {response.status_code}")
            return []

        data = response.json()
        if data.get("ret") != 0:
            log.warning(f"[WeChat] 获取消息失败: {data}")
            return []

        if "get_updates_buf" in data:
            _save_wechat_cursor(data["get_updates_buf"])

        messages = []
        for msg in data.get("msgs", []):
            if msg.get("message_type") == 1:
                text = ""
                for item in msg.get("item_list", []):
                    if item.get("type") == 1:
                        text = item.get("text_item", {}).get("text", "")
                        break

                if text:
                    messages.append({
                        "id": msg.get("message_id"),
                        "from_user_id": msg.get("from_user_id"),
                        "to_user_id": msg.get("to_user_id"),
                        "text": text,
                        "session_id": msg.get("session_id"),
                        "context_token": msg.get("context_token"),
                        "create_time": msg.get("create_time_ms"),
                        "channel": ChannelType.WECHAT
                    })

        return messages

    except requests.exceptions.ConnectionError:
        log.warning("[WeChat] 无法连接到Gateway")
        return []
    except Exception as e:
        log.error(f"[WeChat] 获取消息失败: {e}")
        return []


def _send_wechat_reply(to_user_id: str, context_token: str, text: str) -> bool:
    """发送微信回复"""
    try:
        response = requests.post(
            f"{_WECHAT_GATEWAY_URL}/v1/channels/openclaw-weixin/{_WECHAT_BOT_ID}/sendmessage",
            headers=_WECHAT_HEADERS,
            json={
                "msg": {
                    "to_user_id": to_user_id,
                    "context_token": context_token,
                    "item_list": [
                        {
                            "type": 1,
                            "text_item": {"text": text}
                        }
                    ]
                }
            },
            timeout=30
        )

        if response.status_code == 200:
            log.info("[WeChat] 回复发送成功")
            return True
        else:
            log.warning(f"[WeChat] 回复发送失败: {response.status_code}")
            return False

    except Exception as e:
        log.error(f"[WeChat] 回复发送失败: {e}")
        return False


def _save_wechat_processed(msg_id: str):
    """保存已处理的微信消息ID"""
    _save_set_to_json(_WECHAT_PROCESSED_FILE, msg_id)


# ============== 文章处理 ==============
def _format_imessage_result(learner: ArticleLearner, result) -> str:
    """格式化 iMessage 学习结果（兼容 LearningResult 对象）"""
    try:
        title = result.title if hasattr(result, 'title') else "未知标题"
        source = result.source if hasattr(result, 'source') else "未知来源"
        confidence = result.confidence if hasattr(result, 'confidence') else 0.5
        return f"📖 {title}\n📰 {source}\n🧠 置信度: {confidence:.0%}\n\n⏰ {datetime.now().strftime('%H:%M')}"
    except Exception:
        return f"📖 学习完成（详情已记录）\n\n⏰ {datetime.now().strftime('%H:%M')}"


def _format_wechat_result(result) -> str:
    """格式化微信学习结果（兼容 LearningResult 对象）"""
    try:
        title = result.title if hasattr(result, 'title') else "未知标题"
        source = result.source if hasattr(result, 'source') else "未知来源"
        confidence = result.confidence if hasattr(result, 'confidence') else 0.5

        reply = f"""📚 文章已学习完成！

� 标题: {title[:50]}...
📰 来源: {source}
🧠 置信度: {confidence:.0%}

✅ 知识已进入验证期
   观察一段时间后会参与 Naja 决策~

⏰ {datetime.now().strftime('%H:%M')}"""

        if hasattr(result, 'causality_chains') and result.causality_chains:
            chain = result.causality_chains[0]
            cause = chain.cause if hasattr(chain, 'cause') else ""
            effect = chain.effect if hasattr(chain, 'effect') else ""
            if cause and effect:
                reply += f"\n\n💡 因果洞察: {cause} → {effect}"

        return reply
    except Exception as e:
        return f"""❌ 文章学习失败

原因: {str(e)}

请检查链接是否正确~
⏰ {datetime.now().strftime('%H:%M')}"""


def _process_message(learner: ArticleLearner, msg: Dict[str, Any]) -> Dict[str, Any]:
    """处理单条消息"""
    msg_id = msg.get("id")
    channel = msg.get("channel")
    text = msg.get("text", "")
    urls = extract_urls(text)

    if not urls:
        return {"processed": False, "urls_count": 0}

    processed_count = 0

    for url in urls:
        log.info(f"[{channel.value}] 检测到 URL: {url}")

        if channel == ChannelType.IMESSAGE:
            _send_imessage_reply(f"📥 收到链接: {url[:50]}...\n正在学习...")
            try:
                result = learner.learn(url)
                reply = _format_imessage_result(learner, result)
            except Exception as e:
                reply = f"❌ 学习失败\n{str(e)}"
            _send_imessage_reply(reply)
            _save_imessage_processed(msg_id)

        elif channel == ChannelType.WECHAT:
            _send_wechat_reply(
                msg.get("from_user_id", ""),
                msg.get("context_token", ""),
                f"{get_processing_emoji()} 收到链接，正在学习...\n{url[:30]}..."
            )
            try:
                result = learner.learn(url)
                reply = _format_wechat_result(result)
            except Exception as e:
                reply = f"❌ 学习失败\n{str(e)}"
            _send_wechat_reply(
                msg.get("from_user_id", ""),
                msg.get("context_token", ""),
                reply
            )
            _save_wechat_processed(msg_id)

        processed_count += 1

    return {"processed": True, "urls_count": processed_count}


# ============== 主功能 ==============
def check_all_once(channels: Optional[List[ChannelType]] = None) -> Dict[str, Any]:
    """
    单次检查所有渠道的消息并处理

    Args:
        channels: 要检查的渠道列表，None表示检查所有渠道

    Returns:
        处理结果统计
    """
    if channels is None:
        channels = [ChannelType.IMESSAGE]
        if _WECHAT_ENABLED:
            channels.append(ChannelType.WECHAT)

    learner = ArticleLearner()
    stats = {
        "messages_checked": 0,
        "articles_handled": 0,
        "channels": {}
    }

    for channel in channels:
        channel_stats = {"messages_checked": 0, "articles_handled": 0}

        if channel == ChannelType.IMESSAGE:
            messages = _check_new_imessage_messages()
            processed = _load_set_from_json(_IMESSAGE_PROCESSED_FILE)

            for msg in messages:
                msg_id = msg.get("id")
                if str(msg_id) in processed:
                    continue

                result = _process_message(learner, msg)
                channel_stats["messages_checked"] += 1
                channel_stats["articles_handled"] += result.get("urls_count", 0)

        elif channel == ChannelType.WECHAT:
            messages = _fetch_wechat_messages()
            processed = _load_set_from_json(_WECHAT_PROCESSED_FILE)

            for msg in messages:
                msg_id = msg.get("id")
                if str(msg_id) in processed:
                    continue

                result = _process_message(learner, msg)
                channel_stats["messages_checked"] += 1
                channel_stats["articles_handled"] += result.get("urls_count", 0)

        stats["messages_checked"] += channel_stats["messages_checked"]
        stats["articles_handled"] += channel_stats["articles_handled"]
        stats["channels"][channel.value] = channel_stats

    return stats


def start_listener(channels: Optional[List[ChannelType]] = None, interval: int = 30):
    """
    启动实时监听器

    Args:
        channels: 要监听的渠道列表，None表示监听所有渠道
        interval: 检查间隔（秒）
    """
    if channels is None:
        channels = [ChannelType.IMESSAGE]
        if _WECHAT_ENABLED:
            channels.append(ChannelType.WECHAT)

    log.info("[UnifiedMonitor] 启动统一文章监听器...")
    log.info(f"[UnifiedMonitor] 监听渠道: {[c.value for c in channels]}")
    log.info(f"[UnifiedMonitor] 检查间隔: {interval}秒")

    for channel in channels:
        if channel == ChannelType.IMESSAGE:
            _send_imessage_reply("🔔 Naja文章学习器已启动\n发送文章链接给我，我会帮你学习！")

    learner = ArticleLearner()

    while True:
        try:
            for channel in channels:
                if channel == ChannelType.IMESSAGE:
                    messages = _check_new_imessage_messages()
                    processed = _load_set_from_json(_IMESSAGE_PROCESSED_FILE)

                    for msg in messages:
                        msg_id = msg.get("id")
                        if str(msg_id) in processed:
                            continue

                        _process_message(learner, msg)

                elif channel == ChannelType.WECHAT:
                    messages = _fetch_wechat_messages()
                    processed = _load_set_from_json(_WECHAT_PROCESSED_FILE)

                    for msg in messages:
                        msg_id = msg.get("id")
                        if str(msg_id) in processed:
                            continue

                        _process_message(learner, msg)

            time.sleep(interval)

        except KeyboardInterrupt:
            log.info("[UnifiedMonitor] 监听器已停止")
            break
        except Exception as e:
            log.error(f"[UnifiedMonitor] 监听异常: {e}")
            time.sleep(interval)


# ============== 兼容入口 ==============
def check_and_process() -> Dict[str, Any]:
    """单次检查iMessage（与原imessage_article_listener兼容）"""
    result = check_all_once([ChannelType.IMESSAGE])
    return {
        "messages_checked": result["messages_checked"],
        "urls_processed": result["articles_handled"]
    }


def check_once() -> Dict[str, Any]:
    """单次检查微信（与原wechat_article_realtime兼容）"""
    return check_all_once([ChannelType.WECHAT])


def start_realtime_listener():
    """启动微信监听（与原wechat_article_realtime兼容）"""
    start_listener([ChannelType.WECHAT], interval=5)


def listen_and_learn():
    """启动iMessage监听（与原imessage_article_listener兼容）"""
    start_listener([ChannelType.IMESSAGE], interval=30)


# ============== 定时任务入口 ==============
def execute() -> Dict[str, Any]:
    """
    定时任务入口：检查所有渠道的文章

    这个函数会被任务调度器定期调用
    """
    log.info("[UnifiedMonitor] 开始检查文章...")

    try:
        result = check_all_once()

        log.info(f"[UnifiedMonitor] 完成: 检查{result['messages_checked']}条消息, 处理{result['articles_handled']}个链接")

        return {
            "success": True,
            "messages_checked": result["messages_checked"],
            "articles_handled": result["articles_handled"],
            "channels": result["channels"],
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        log.error(f"[UnifiedMonitor] 检查失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# ============== 入口 ==============
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "imessage":
            listen_and_learn()
        elif sys.argv[1] == "wechat":
            start_realtime_listener()
        elif sys.argv[1] == "once":
            result = check_all_once()
            print(f"\n结果: {result}")
        else:
            print("用法:")
            print("  python -m deva.naja.tasks.unified_article_monitor [imessage|wechat|once]")
            print("\n默认监听所有渠道:")
            start_listener()
    else:
        start_listener()
