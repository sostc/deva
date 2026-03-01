#!/usr/bin/env python3
"""
Script to properly fix the '测试' task by updating its code to have a valid execute function.
"""

from deva import NB

# Check the legacy tasks table
legacy_db = NB("tasks")

# Get the '测试' task
test_task = legacy_db.get("测试")

if test_task:
    print("Current task code:")
    print("=" * 60)
    print(test_task.get("job_code", ""))
    print("=" * 60)
    
    # Create a proper execute function
    fixed_code = '''async def execute(context=None):
    """
    打印日志 "helloworld" 的异步函数。
    """
    # 导入所需的模块
    from deva import write_to_file, httpx, Dtalk, log
    from deva.admin import watch_topic
    
    # 打印日志 "helloworld"
    'hello' >> log
    'Hello World' >> log
    return 'Task completed successfully'
'''
    
    print("\nFixed task code:")
    print("=" * 60)
    print(fixed_code)
    print("=" * 60)
    
    # Update the task in the legacy database
    test_task["job_code"] = fixed_code
    legacy_db["测试"] = test_task
    print("\n✅ Successfully updated '测试' task with valid execute function.")
else:
    print("❌ '测试' task not found in the legacy database.")
