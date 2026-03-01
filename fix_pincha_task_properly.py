#!/usr/bin/env python3
"""
Script to properly fix the '品茶' task by creating an execute function that calls the original summarize_xinhua_news function.
"""

from deva import NB

# Check the legacy tasks table
legacy_db = NB("tasks")

# Get the '品茶' task
pincha_task = legacy_db.get("品茶")

if pincha_task:
    # Create a fixed code that includes both the original function and an execute function
    fixed_code = '''async def summarize_xinhua_news():
    """
    总结“新华社重要新闻”并打印到日志的异步函数。
    """
    # 导入所需的模块
    from deva import write_to_file, httpx, Dtalk, log
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

async def execute(context=None):
    """
    执行品茶任务
    """
    from deva import log
    
    '开始执行品茶任务' >> log
    
    try:
        result = await summarize_xinhua_news()
        '品茶任务执行成功' >> log
        return result
    except Exception as e:
        error_msg = f'品茶任务执行失败: {e}'
        error_msg >> log
        raise
'''
    
    # Update the task in the legacy database with the fixed code
    pincha_task["job_code"] = fixed_code
    legacy_db["品茶"] = pincha_task
    print("✅ Successfully fixed '品茶' task with proper execute function.")
else:
    print("❌ '品茶' task not found in the legacy database.")
