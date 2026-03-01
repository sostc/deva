#!/usr/bin/env python3
"""
Script to check the legacy tasks table for the '测试' task.
"""

from deva import NB

# Check the legacy tasks table
legacy_db = NB("tasks")
print(f"Found {len(legacy_db)} legacy tasks:")

# Look for the '测试' task
test_task = None
for name, info in legacy_db.items():
    print(f"  - Task name: {name}")
    
    if name == "测试":
        test_task = info
        print(f"\nFound '测试' task!")
        break

if test_task:
    print("\nTask information:")
    print("=" * 60)
    for key, value in test_task.items():
        print(f"{key}: {value}")
    print("=" * 60)
    
    # Check if the job code contains log_hello_world
    job_code = test_task.get("job_code", "")
    if "log_hello_world" in job_code:
        print("\nFound 'log_hello_world' in the job code!")
        print("This is the function that's causing the NameError.")
        
        # Fix the job code
        fixed_code = job_code.replace("log_hello_world", '"Hello World" >> log')
        
        print("\nFixed job code:")
        print("=" * 60)
        print(fixed_code)
        print("=" * 60)
        
        # Update the task in the legacy database
        test_task["job_code"] = fixed_code
        legacy_db["测试"] = test_task
        print("\n✅ Successfully updated '测试' task in the legacy database.")
    else:
        print("\n'log_hello_world' not found in the job code.")
else:
    print("\n❌ '测试' task not found in the legacy database.")
