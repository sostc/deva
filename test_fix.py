#!/usr/bin/env python3
"""
Test script to verify that the fix for the scope issue works.
"""

from deva.admin_ui.strategy.executable_unit import ExecutableUnit, ExecutableUnitMetadata, ExecutableUnitState

# Create a mock executable unit
class MockExecutableUnit(ExecutableUnit):
    def _validate_function(self, func):
        return {"success": True}
    
    def _do_start(self):
        return {"success": True}
    
    def _do_stop(self):
        return {"success": True}

# Create test metadata and state
metadata = ExecutableUnitMetadata(
    id="test_unit",
    name="Test Unit",
    func_code='''
async def summarize_xinhua_news():
    """
    总结“新华社重要新闻”并打印到日志的异步函数。
    """
    # 导入所需的模块
    from deva import log

    # 打印日志
    'Inside summarize_xinhua_news' >> log
    return "Test news"

async def execute(context=None):
    """
    执行品茶任务
    """
    from deva import log
    
    'Inside execute' >> log
    
    try:
        result = await summarize_xinhua_news()
        f'Got result: {result}' >> log
        return result
    except Exception as e:
        error_msg = f'Error: {e}'
        error_msg >> log
        raise
'''
)

state = ExecutableUnitState()

# Create the executable unit
unit = MockExecutableUnit(metadata=metadata, state=state, func_name="execute")

# Compile the code
compile_result = unit.compile_code(metadata.func_code)

if compile_result["success"]:
    print("✅ Code compiled successfully")
    
    # Get the execute function
    execute_func = compile_result["func"]
    
    # Execute it
    import asyncio
    result = asyncio.run(execute_func())
    print(f"✅ Execute result: {result}")
else:
    print(f"❌ Compilation failed: {compile_result['error']}")
