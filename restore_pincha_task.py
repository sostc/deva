#!/usr/bin/env python3
"""
Script to restore the original code for the '品茶' task.
"""

from deva import NB

# Check the legacy tasks table
legacy_db = NB("tasks")

# Get the '品茶' task
pincha_task = legacy_db.get("品茶")

if pincha_task:
    # Restore the original code
    original_code = '''async def summarize_xinhua_news():
    """
    总结“新华社重要新闻”并打印到日志的异步函数。
    """
    # 导入所需的模块
    from deva import write_to_file, httpx, Dtalk
    from deva.admin import watch_topic

    # 定期关注“新华社重要新闻”话题
    content = await watch_topic('新华社重要新闻')

    # 打印日志，记录获取到的新闻内容
    content >> log

    # 将新闻内容写入文件，以便后续分析或存档
    content >> write_to_file('xinhua_news_summary.txt')

    # 发送到钉钉通知，标记为焦点分析
    '@md@焦点分析|' + content >> Dtalk()

    # 返回新闻内容，以便函数调用者可以进一步处理
    return content
'''
    
    # Update the task in the legacy database with the original code
    pincha_task["job_code"] = original_code
    legacy_db["品茶"] = pincha_task
    print("✅ Successfully restored '品茶' task with original code.")
else:
    print("❌ '品茶' task not found in the legacy database.")
