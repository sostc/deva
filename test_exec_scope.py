#!/usr/bin/env python3
"""
Test script to understand the scope issue with exec and nested functions.
"""

# Simulate how the task code is compiled and executed
def test_exec_scope():
    print("Testing exec scope...")
    
    # The task code with both functions
    code = '''
async def summarize_xinhua_news():
    print("Inside summarize_xinhua_news")
    return "Test news"

async def execute(context=None):
    print("Inside execute")
    result = await summarize_xinhua_news()
    print(f"Got result: {result}")
    return result
'''
    
    # Build a global environment similar to what _build_execution_env provides
    global_env = {
        'print': print,
        'asyncio': __import__('asyncio'),
    }
    
    local_vars = {}
    
    # Execute the code
    exec(code, global_env, local_vars)
    
    # Get the execute function
    execute_func = local_vars.get('execute')
    
    if execute_func:
        print("Found execute function")
        # Check if summarize_xinhua_news is in local_vars
        if 'summarize_xinhua_news' in local_vars:
            print("Found summarize_xinhua_news function in local_vars")
        else:
            print("summarize_xinhua_news NOT found in local_vars")
        
        # Try to execute it
        import asyncio
        result = asyncio.run(execute_func())
        print(f"Execute result: {result}")
    else:
        print("execute function not found")

if __name__ == "__main__":
    test_exec_scope()
