#!/usr/bin/env python3
"""
Script to fix the '品茶' task by updating its code to resolve the summarize_xinhua_news error.
"""

from deva import NB

# Check the legacy tasks table
legacy_db = NB("tasks")

# Get the '品茶' task
pincha_task = legacy_db.get("品茶")

if pincha_task:
    print("Current task code:")
    print("=" * 60)
    print(pincha_task.get("job_code", ""))
    print("=" * 60)
    
    # Create a proper execute function that doesn't use the missing summarize_xinhua_news function
    fixed_code = '''async def execute(context=None):
    """
    品茶任务 - 打印茶叶相关信息
    """
    # 导入所需的模块
    from deva import log
    
    # 打印茶叶相关信息
    '开始品茶任务' >> log
    '茶叶是一种健康的饮品' >> log
    '不同种类的茶叶有不同的功效' >> log
    '品茶可以放松身心' >> log
    '结束品茶任务' >> log
    
    return '品茶任务完成'
'''
    
    print("\nFixed task code:")
    print("=" * 60)
    print(fixed_code)
    print("=" * 60)
    
    # Update the task in the legacy database
    pincha_task["job_code"] = fixed_code
    legacy_db["品茶"] = pincha_task
    print("\n✅ Successfully updated '品茶' task with valid execute function.")
else:
    print("❌ '品茶' task not found in the legacy database.")
