#!/usr/bin/env python3
"""
Script to find the '测试' task and examine its code to fix the log_hello_world error.
"""

from deva.admin_ui.strategy.persistence import get_global_persistence_manager
from deva.admin_ui.tasks.task_unit import TaskUnit

# Get the persistence manager
persistence = get_global_persistence_manager()

# List all task IDs
task_ids = persistence.list_units("task")
print(f"Found {len(task_ids)} tasks:")

# Find the '测试' task
test_task = None
for task_id in task_ids:
    # Load the task data
    task_data = persistence.load_unit("task", task_id)
    if task_data:
        # Check if this is the '测试' task
        task_name = task_data.get("metadata", {}).get("name", "")
        print(f"  - Task ID: {task_id}, Name: {task_name}")
        
        if task_name == "测试":
            test_task = task_data
            print(f"\nFound '测试' task with ID: {task_id}")
            break

if test_task:
    # Examine the task code
    func_code = test_task.get("metadata", {}).get("func_code", "")
    print("\nTask code:")
    print("=" * 60)
    print(func_code)
    print("=" * 60)
    
    # Check if log_hello_world is in the code
    if "log_hello_world" in func_code:
        print("\nFound 'log_hello_world' in the code!")
        print("This is the function that's causing the NameError.")
        
        # Fix the code by replacing log_hello_world with the correct log usage
        fixed_code = func_code.replace("log_hello_world", '"Hello World" >> log')
        
        print("\nFixed code:")
        print("=" * 60)
        print(fixed_code)
        print("=" * 60)
        
        # Update the task data with the fixed code
        test_task["metadata"]["func_code"] = fixed_code
        test_task["metadata"]["version"] = test_task["metadata"].get("version", 1) + 1
        
        # Save the fixed task
        task_id = test_task.get("metadata", {}).get("id", "")
        if task_id:
            success = persistence.save_unit("task", task_id, test_task)
            if success:
                print(f"\n✅ Successfully updated task '{task_id}' with fixed code.")
            else:
                print(f"\n❌ Failed to update task '{task_id}'.")
        else:
            print("\n❌ Task ID not found in task data.")
else:
    print("\n❌ '测试' task not found.")
