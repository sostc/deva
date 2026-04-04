"""
iMessage文章检查任务 - 定时检查并学习收到的文章链接

注册到任务调度器，每5分钟检查一次iMessage中的新链接
"""

import logging
from datetime import datetime

from deva.naja.tasks.imessage_article_listener import check_and_process

log = logging.getLogger(__name__)


def execute():
    """
    定时任务入口：检查iMessage中的新文章链接

    这个函数会被任务调度器定期调用
    """
    log.info("[iMessage_Article_Check] 开始检查iMessage文章...")

    try:
        result = check_and_process()

        messages_checked = result.get("messages_checked", 0)
        urls_processed = result.get("urls_processed", 0)

        log.info(f"[iMessage_Article_Check] 完成: 检查{messages_checked}条消息, 处理{urls_processed}个链接")

        return {
            "success": True,
            "messages_checked": messages_checked,
            "urls_processed": urls_processed,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        log.error(f"[iMessage_Article_Check] 检查失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# 直接运行测试
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = execute()
    print(f"\n结果: {result}")
