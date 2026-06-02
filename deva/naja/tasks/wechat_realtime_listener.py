"""
兼容性模块 - 重定向到 unified_article_monitor
原模块已合并到 unified_article_monitor.py
"""

# 提供一些兼容性的函数定义
def get_updates():
    """兼容性函数（已废弃）"""
    return []

def send_message(to_user_id, text, context_token=""):
    """兼容性函数（已废弃）"""
    from deva.naja.tasks.unified_article_monitor import _send_wechat_reply
    return _send_wechat_reply(to_user_id, context_token, text)

def extract_url(text):
    """兼容性函数（已废弃）"""
    from deva.naja.tasks.unified_article_monitor import extract_urls
    urls = extract_urls(text)
    return urls[0] if urls else None

def get_processing_emoji():
    """兼容性函数（已废弃）"""
    import random
    emojis = ["🤔", "🔍", "📚", "🧠", "✨"]
    return random.choice(emojis)

def format_learning_result(result):
    """兼容性函数（已废弃）"""
    from deva.naja.tasks.unified_article_monitor import _format_wechat_result
    return _format_wechat_result(result)

def learn_article(url):
    """兼容性函数（已废弃）"""
    from deva.naja.tasks.article_learner import ArticleLearner
    return ArticleLearner().learn(url)

def run():
    """兼容性函数 - 调用统一的监听器"""
    from deva.naja.tasks.unified_article_monitor import start_realtime_listener
    start_realtime_listener()

__all__ = [
    "get_updates",
    "send_message",
    "extract_url",
    "get_processing_emoji",
    "format_learning_result",
    "learn_article",
    "run",
]
