"""
微信文章实时学习器

通过openclaw-weixin插件实时接收微信消息，学习文章链接并回复反馈

工作流程：
1. 轮询微信新消息
2. 检测URL
3. 学习文章内容
4. 通过微信发送学习结果
"""

import json
import logging
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests

from deva.naja.tasks.article_learner import ArticleLearner

log = logging.getLogger(__name__)

# OpenClaw配置
_GATEWAY_URL = "http://127.0.0.1:18789"
_AUTH_TOKEN = "2a87d7bf09e81ec6a3a5e79a18c80129615b17f90a361daa"
_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {_AUTH_TOKEN}"
}

# 微信账号
_WECHAT_BOT_ID = "6fbf95535975-im-bot"

# 存储路径
_LEARNING_DIR = Path.home() / ".naja" / "article_learning"
_LEARNING_DIR.mkdir(parents=True, exist_ok=True)

# 已处理的游标
_CURSOR_FILE = _LEARNING_DIR / "wechat_cursor.json"


def _load_cursor() -> str:
    """加载上次处理的游标"""
    if _CURSOR_FILE.exists():
        with open(_CURSOR_FILE, "r") as f:
            data = json.load(f)
            return data.get("cursor", "")
    return ""


def _save_cursor(cursor: str):
    """保存游标"""
    with open(_CURSOR_FILE, "w") as f:
        json.dump({"cursor": cursor}, f)


def extract_urls(text: str) -> List[str]:
    """从文本中提取URL"""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    return list(set(urls))


def fetch_wechat_messages() -> List[Dict[str, Any]]:
    """从微信获取新消息"""
    try:
        cursor = _load_cursor()

        # 调用openclaw-weixin API
        response = requests.post(
            f"{_GATEWAY_URL}/v1/channels/openclaw-weixin/{_WECHAT_BOT_ID}/getupdates",
            headers=_HEADERS,
            json={"get_updates_buf": cursor},
            timeout=40
        )

        if response.status_code != 200:
            log.warning(f"[WechatRealtime] API调用失败: {response.status_code}")
            return []

        data = response.json()
        if data.get("ret") != 0:
            log.warning(f"[WechatRealtime] 获取消息失败: {data}")
            return []

        # 保存新的游标
        if "get_updates_buf" in data:
            _save_cursor(data["get_updates_buf"])

        messages = []
        for msg in data.get("msgs", []):
            # 只处理用户发送的消息
            if msg.get("message_type") == 1:  # USER message
                # 提取文本内容
                text = ""
                for item in msg.get("item_list", []):
                    if item.get("type") == 1:  # TEXT
                        text = item.get("text_item", {}).get("text", "")
                        break

                if text:
                    messages.append({
                        "message_id": msg.get("message_id"),
                        "from_user_id": msg.get("from_user_id"),
                        "to_user_id": msg.get("to_user_id"),
                        "text": text,
                        "session_id": msg.get("session_id"),
                        "context_token": msg.get("context_token"),
                        "create_time": msg.get("create_time_ms")
                    })

        return messages

    except requests.exceptions.ConnectionError:
        log.warning("[WechatRealtime] 无法连接到Gateway")
        return []
    except Exception as e:
        log.error(f"[WechatRealtime] 获取消息失败: {e}")
        return []


def send_wechat_reply(to_user_id: str, context_token: str, text: str) -> bool:
    """发送微信回复"""
    try:
        response = requests.post(
            f"{_GATEWAY_URL}/v1/channels/openclaw-weixin/{_WECHAT_BOT_ID}/sendmessage",
            headers=_HEADERS,
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
            log.info(f"[WechatRealtime] 回复发送成功")
            return True
        else:
            log.warning(f"[WechatRealtime] 回复发送失败: {response.status_code}")
            return False

    except Exception as e:
        log.error(f"[WechatRealtime] 回复发送失败: {e}")
        return False


def process_article(learner: ArticleLearner, url: str) -> str:
    """处理文章并生成回复文本"""
    result = learner.learn_from_url(url, source="wechat")

    if result["success"]:
        title = result.get("title", "未知标题")
        knowledge_count = len(result.get("knowledge_extracted", []))

        reply = f"""📚 文章已学习完成！

📝 标题: {title[:50]}...
🧠 提取知识: {knowledge_count}条

✅ 知识已进入验证期
   观察一段时间后会参与Naja决策~

⏰ {datetime.now().strftime("%H:%M")}"""

        # 如果有具体知识内容
        if knowledge_count > 0:
            entries = result.get("knowledge_extracted", [])
            if entries:
                entry = entries[0]
                cause = entry.get("cause", "")
                effect = entry.get("effect", "")
                if cause and effect:
                    reply += f"\n\n💡 因果洞察: {cause} → {effect}"

        return reply
    else:
        return f"""❌ 文章学习失败

原因: {result.get('error', '未知错误')}

请检查链接是否正确~
⏰ {datetime.now().strftime("%H:%M")}"""


def start_realtime_listener():
    """
    启动实时监听器

    持续运行，定期检查微信消息并处理
    """
    log.info("[WechatRealtime] 启动微信文章实时学习器...")
    learner = ArticleLearner()

    # 处理记录
    processed_ids_file = _LEARNING_DIR / "processed_wechat_ids.json"

    def load_processed_ids() -> set:
        if processed_ids_file.exists():
            with open(processed_ids_file, "r") as f:
                return set(json.load(f))
        return set()

    def save_processed_id(msg_id):
        processed = load_processed_ids()
        processed.add(str(msg_id))
        with open(processed_ids_file, "w") as f:
            json.dump(list(processed), f)

    # 发送启动通知
    try:
        # 发送到爸爸的微信（需要先获取user_id）
        log.info("[WechatRealtime] 监听器已启动，等待消息...")
    except Exception as e:
        log.warning(f"[WechatRealtime] 启动通知发送失败: {e}")

    while True:
        try:
            messages = fetch_wechat_messages()
            processed = load_processed_ids()

            for msg in messages:
                msg_id = msg.get("message_id")

                if str(msg_id) in processed:
                    continue

                text = msg.get("text", "")
                urls = extract_urls(text)

                if urls:
                    log.info(f"[WechatRealtime] 收到消息含URL: {text[:50]}...")

                    # 处理每个URL
                    for url in urls:
                        # 发送"正在处理"提示
                        send_wechat_reply(
                            msg.get("from_user_id", ""),
                            msg.get("context_token", ""),
                            f"📥 收到链接，正在学习...\n{url[:30]}..."
                        )

                        # 处理文章
                        reply = process_article(learner, url)

                        # 发送结果
                        send_wechat_reply(
                            msg.get("from_user_id", ""),
                            msg.get("context_token", ""),
                            reply
                        )

                    save_processed_id(msg_id)
                else:
                    # 非URL消息也标记为已处理
                    save_processed_id(msg_id)

            # 长轮询间隔
            time.sleep(5)

        except KeyboardInterrupt:
            log.info("[WechatRealtime] 监听器已停止")
            break
        except Exception as e:
            log.error(f"[WechatRealtime] 监听异常: {e}")
            time.sleep(10)


def check_once() -> Dict[str, Any]:
    """单次检查并处理（用于定时任务）"""
    learner = ArticleLearner()
    processed_file = _LEARNING_DIR / "processed_wechat_ids.json"

    def load_processed() -> set:
        if processed_file.exists():
            with open(processed_file, "r") as f:
                return set(json.load(f))
        return set()

    def save_processed(msg_id):
        processed = load_processed()
        processed.add(str(msg_id))
        with open(processed_file, "w") as f:
            json.dump(list(processed), f)

    messages = fetch_wechat_messages()
    processed = load_processed()
    handled = 0

    for msg in messages:
        msg_id = msg.get("message_id")
        if str(msg_id) in processed:
            continue

        text = msg.get("text", "")
        urls = extract_urls(text)

        if urls:
            for url in urls:
                reply = process_article(learner, url)
                send_wechat_reply(
                    msg.get("from_user_id", ""),
                    msg.get("context_token", ""),
                    reply
                )
            handled += 1

        save_processed(msg_id)

    return {
        "messages_checked": len(messages),
        "articles_handled": handled
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_realtime_listener()
