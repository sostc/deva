"""
微信文章实时学习器
通过openclaw-weixin API接收微信消息，处理文章链接并回复结果
"""
import time
import json
import re
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime

import requests

# ============== 配置 ==============
OPENCLAW_GATEWAY = "http://127.0.0.1:18789"
TOKEN = "2a87d7bf09e81ec6a3a5e79a18c80129615b17f90a361daa"
WECHAT_ACCOUNT = "6fbf95535975-im-bot"  # 微信clawbot账号
POLL_INTERVAL = 2  # 轮询间隔（秒）

# ============== 工具函数 ==============
def get_updates() -> List[Dict[str, Any]]:
    """获取新消息"""
    url = f"{OPENCLAW_GATEWAY}/v1/channels/openclaw-weixin/{WECHAT_ACCOUNT}/getupdates"
    try:
        resp = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN}"
            },
            json={"get_updates_buf": ""},
            timeout=40
        )
        data = resp.json()
        if data.get("ret") == 0:
            return data.get("msgs", [])
        return []
    except Exception as e:
        print(f"[错误] get_updates失败: {e}")
        return []


def send_message(to_user_id: str, text: str, context_token: str = "") -> bool:
    """发送消息"""
    url = f"{OPENCLAW_GATEWAY}/v1/channels/openclaw-weixin/{WECHAT_ACCOUNT}/sendmessage"
    try:
        payload = {
            "msg": {
                "to_user_id": to_user_id,
                "context_token": context_token,
                "item_list": [
                    {
                        "type": 1,  # TEXT
                        "text_item": {"text": text}
                    }
                ]
            }
        }
        resp = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN}"
            },
            json=payload,
            timeout=10
        )
        result = resp.json()
        return result.get("ret") == 0
    except Exception as e:
        print(f"[错误] send_message失败: {e}")
        return False


def extract_url(text: str) -> Optional[str]:
    """从文本中提取URL"""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    return urls[0] if urls else None


def get_processing_emoji() -> str:
    """获取处理中的表情"""
    import random
    emojis = ["🤔", "🔍", "📚", "🧠", "✨"]
    return random.choice(emojis)


def format_learning_result(result: Dict[str, Any]) -> str:
    """格式化学习结果"""
    title = result.get("title", "未知标题")
    source = result.get("source", "未知来源")
    key_points = result.get("key_points", [])
    kpis = result.get("kpis", [])
    causality = result.get("causality", [])

    # 构建回复文本
    reply = f"✅ 已学习完成！\n\n"
    reply += f"📖 {title}\n"
    reply += f"📰 来源: {source}\n\n"

    if kpis:
        reply += f"📊 关键数据:\n"
        for kpi in kpis[:3]:
            reply += f"   • {kpi}\n"
        reply += "\n"

    if key_points:
        reply += f"💡 核心要点:\n"
        for point in key_points[:3]:
            reply += f"   • {point}\n"
        reply += "\n"

    if causality:
        reply += f"🔗 因果洞察:\n"
        for c in causality[:2]:
            reply += f"   • {c}\n"
        reply += "\n"

    reply += f"🧠 已进入知识库观察期，7天后验证有效后将参与决策！"

    return reply


# ============== 文章学习 ==============
def learn_article(url: str) -> Dict[str, Any]:
    """学习文章并提取知识"""
    import sys
    sys.path.insert(0, "/Users/spark/pycharmproject/deva")

    from deva.naja.tasks.article_learner import ArticleLearner

    learner = ArticleLearner()
    return learner.learn(url)


# ============== 主循环 ==============
def run():
    """运行微信消息监听循环"""
    print("🚀 微信文章实时学习器启动！")
    print(f"   监听账号: {WECHAT_ACCOUNT}")
    print(f"   轮询间隔: {POLL_INTERVAL}秒")
    print("-" * 40)

    updates_buf = ""
    processed_ids = set()  # 避免重复处理

    while True:
        try:
            # 获取新消息
            url = f"{OPENCLAW_GATEWAY}/v1/channels/openclaw-weixin/{WECHAT_ACCOUNT}/getupdates"
            resp = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {TOKEN}"
                },
                json={"get_updates_buf": updates_buf},
                timeout=40
            )

            data = resp.json()
            if data.get("ret") == 0:
                updates_buf = data.get("get_updates_buf", "")

            msgs = data.get("msgs", [])

            for msg in msgs:
                msg_id = msg.get("message_id")
                if msg_id and msg_id in processed_ids:
                    continue

                # 只处理用户发送的消息
                if msg.get("message_type") != 1:
                    continue

                # 获取消息文本
                text = ""
                for item in msg.get("item_list", []):
                    if item.get("type") == 1 and item.get("text_item"):
                        text = item.get("text_item", {}).get("text", "")
                        break

                if not text:
                    continue

                from_user = msg.get("from_user_id", "unknown")
                context_token = msg.get("context_token", "")

                print(f"\n📩 收到消息 from {from_user}: {text[:50]}...")

                # 检查是否包含URL
                article_url = extract_url(text)
                if article_url:
                    print(f"🔗 检测到链接: {article_url}")

                    # 发送处理中提示
                    send_message(
                        from_user,
                        f"{get_processing_emoji()} 正在学习文章，请稍候...",
                        context_token
                    )

                    # 学习文章
                    try:
                        result = learn_article(article_url)
                        reply = format_learning_result(result)
                    except Exception as e:
                        print(f"[错误] 学习失败: {e}")
                        reply = f"😅 学习文章时出了点小问题: {str(e)[:50]}"

                    # 发送结果
                    send_message(from_user, reply, context_token)
                    print(f"✅ 已回复")
                else:
                    # 非链接消息，发送帮助提示
                    help_text = "👋 发送给我文章链接，我会帮你学习并提取知识！\n\n例如：https://mp.weixin.qq.com/s/xxxxx"
                    send_message(from_user, help_text, context_token)

                processed_ids.add(msg_id)

            # 清理过期的消息ID
            if len(processed_ids) > 1000:
                processed_ids = set(list(processed_ids)[-500:])

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n👋 退出...")
            break
        except Exception as e:
            print(f"[错误] {e}")
            time.sleep(5)


# ============== 入口 ==============
if __name__ == "__main__":
    run()
