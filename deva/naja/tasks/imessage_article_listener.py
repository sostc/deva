"""
iMessage文章学习监听器

监控收到的iMessage，当收到包含URL的消息时，自动学习文章内容

原理：
- 使用 imesg CLI 监听新消息
- 检测消息中的URL
- 调用 ArticleLearner 学习文章
"""

import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup

from deva.naja.tasks.article_learner import ArticleLearner, send_notification, _PHONE

log = logging.getLogger(__name__)

# 存储路径
_LEARNING_DIR = Path.home() / ".naja" / "article_learning"
_LEARNING_DIR.mkdir(parents=True, exist_ok=True)

# 处理记录
_PROCESSED_IDS_FILE = _LEARNING_DIR / "processed_messages.json"


def _load_processed_ids() -> set:
    """加载已处理的消息ID"""
    if _PROCESSED_IDS_FILE.exists():
        with open(_PROCESSED_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def _save_processed_id(msg_id: str):
    """保存已处理的消息ID"""
    processed = _load_processed_ids()
    processed.add(msg_id)
    with open(_PROCESSED_IDS_FILE, "w") as f:
        json.dump(list(processed), f)


def extract_urls(text: str) -> List[str]:
    """从文本中提取URL"""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    return list(set(urls))  # 去重


def check_new_messages() -> List[Dict[str, Any]]:
    """检查新收到的消息（来自爸爸的）"""
    try:
        # 使用 imesg 获取最近的对话
        result = subprocess.run(
            ["imesg", "list", "--limit", "20"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            log.warning(f"[iMessageListener] 获取消息失败: {result.stderr}")
            return []

        messages = []
        current_time = datetime.now()
        processed = _load_processed_ids()

        # 解析消息（每行格式: ID|DATE|CHAT|TEXT）
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            parts = line.split("|")
            if len(parts) >= 4:
                msg_id = parts[0].strip()
                date_str = parts[1].strip()
                chat = parts[2].strip()
                text = "|".join(parts[3:]).strip()  # 消息可能包含|

                # 跳过已处理的
                if msg_id in processed:
                    continue

                # 检查是否来自爸爸的对话
                if chat and ("baba" in chat.lower() or "spark" in chat.lower()
                             or "18626880088" in chat or _PHONE in chat):
                    # 解析时间
                    try:
                        msg_time = datetime.fromisoformat(date_str)
                        # 只处理最近5分钟的消息
                        if current_time - msg_time < timedelta(minutes=5):
                            messages.append({
                                "id": msg_id,
                                "time": msg_time,
                                "chat": chat,
                                "text": text
                            })
                    except Exception:
                        pass

        return messages

    except FileNotFoundError:
        log.warning("[iMessageListener] imesg 命令不存在")
        return []
    except Exception as e:
        log.error(f"[iMessageListener] 检查消息失败: {e}")
        return []


def process_article_url(url: str, msg_id: str) -> Dict[str, Any]:
    """处理文章URL"""
    log.info(f"[iMessageListener] 开始学习文章: {url}")

    learner = ArticleLearner()
    result = learner.learn_from_url(url, source="iMessage")

    # 生成反馈消息
    if result["success"]:
        summary = learner.generate_summary(result)

        # 格式化发送给爸爸
        feedback = f"""📚 文章学习完成

{summary}

⏰ {datetime.now().strftime("%H:%M")}"""

        # 发送确认
        send_notification(feedback)

        _save_processed_id(msg_id)

        return {"success": True, "result": result}
    else:
        # 发送失败通知
        send_notification(f"❌ 文章学习失败\n{result.get('error', '请检查链接是否正确')}")
        _save_processed_id(msg_id)

        return {"success": False, "result": result}


def listen_and_learn():
    """
    主监听循环 - 检查新消息并学习文章

    用法：
        from deva.naja.tasks.imessage_article_listener import listen_and_learn
        listen_and_learn()  # 阻塞运行
    """
    log.info("[iMessageListener] 启动文章学习监听器...")
    send_notification("🔔 Naja文章学习器已启动\n发送文章链接给我，我会帮你学习！")

    learner = ArticleLearner()

    while True:
        try:
            messages = check_new_messages()

            for msg in messages:
                urls = extract_urls(msg["text"])

                if urls:
                    for url in urls:
                        log.info(f"[iMessageListener] 检测到URL: {url}")

                        # 发送"正在处理"提示
                        send_notification(f"📥 收到链接: {url[:50]}...\n正在学习...")

                        # 处理文章
                        result = learner.learn_from_url(url, source="iMessage")

                        # 发送结果
                        if result["success"]:
                            summary = learner.generate_summary(result)
                            send_notification(f"{summary}\n⏰ {datetime.now().strftime('%H:%M')}")
                        else:
                            send_notification(f"❌ 学习失败\n{result.get('error', '未知错误')}")

                        _save_processed_id(msg["id"])

                else:
                    _save_processed_id(msg["id"])

            # 每30秒检查一次
            import time
            time.sleep(30)

        except KeyboardInterrupt:
            log.info("[iMessageListener] 监听器已停止")
            break
        except Exception as e:
            log.error(f"[iMessageListener] 监听异常: {e}")
            import time
            time.sleep(30)


# 单次检查并处理（用于定时任务）
def check_and_process() -> Dict[str, Any]:
    """单次检查并处理新消息中的URL"""
    messages = check_new_messages()
    processed = 0

    learner = ArticleLearner()

    for msg in messages:
        urls = extract_urls(msg["text"])

        if urls:
            for url in urls:
                log.info(f"[iMessageListener] 检测到URL: {url}")
                result = learner.learn_from_url(url, source="iMessage")

                if result["success"]:
                    summary = learner.generate_summary(result)
                    send_notification(f"{summary}\n⏰ {datetime.now().strftime('%H:%M')}")

                processed += 1

        _save_processed_id(msg["id"])

    return {
        "messages_checked": len(messages),
        "urls_processed": processed
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    listen_and_learn()
