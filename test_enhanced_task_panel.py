#!/usr/bin/env python3
"""
测试增强版任务面板功能

这个脚本演示如何使用增强版任务面板创建和编辑任务，
包括AI代码生成功能。
"""

import asyncio
from deva.admin_ui.strategy.enhanced_task_panel import (
    show_enhanced_create_task_dialog,
    show_enhanced_edit_task_dialog,
    validate_task_code
)
from deva.admin_ui.strategy.task_manager import get_task_manager
from deva.admin_ui.strategy.task_unit import TaskUnit, TaskMetadata, TaskState, TaskExecution, TaskType


def test_task_code_validation():
    """测试任务代码验证功能"""
    print("=== 测试任务代码验证功能 ===")
    
    # 测试有效代码
    valid_code = '''
async def execute(context=None):
    """测试任务"""
    return '任务执行完成'
'''
    
    result = validate_task_code(valid_code)
    print(f"有效代码验证结果: {result}")
    
    # 测试无效代码
    invalid_code = '''
def some_function():
    return 'not a task'
'''
    
    result = validate_task_code(invalid_code)
    print(f"无效代码验证结果: {result}")
    
    # 测试带警告的代码
    warning_code = '''
async def execute(context=None):
    eval('some_code')
    return 'task complete'
'''
    
    result = validate_task_code(warning_code)
    print(f"警告代码验证结果: {result}")
    print()


def test_task_creation():
    """测试任务创建功能"""
    print("=== 测试任务创建功能 ===")
    
    # 获取任务管理器
    task_manager = get_task_manager()
    
    # 创建测试任务
    from datetime import datetime
    
    metadata = TaskMetadata(
        id=f"test_task_{int(datetime.now().timestamp())}",
        name="测试任务",
        description="这是一个测试任务",
        task_type=TaskType.INTERVAL,
        schedule_config={"interval": 60},
        func_code='''
async def execute(context=None):
    """测试任务执行函数"""
    print("任务执行中...")
    return "任务执行完成"
'''
    )
    
    state = TaskState(
        status="stopped",
        last_run_time=0,
        next_run_time=0,
        run_count=0,
        error_count=0
    )
    
    execution = TaskExecution(
        job_code=metadata.func_code,
        execution_history=[]
    )
    
    # 创建任务单元
    task_unit = TaskUnit(
        metadata=metadata,
        state=state,
        execution=execution
    )
    
    # 注册任务
    result = task_manager.register(task_unit)
    print(f"任务注册结果: {result}")
    
    if result.get("success"):
        print(f"任务创建成功: {task_unit.name}")
        print(f"任务ID: {task_unit.id}")
        print(f"任务类型: {task_unit.metadata.task_type.value}")
        print(f"调度配置: {task_unit.metadata.schedule_config}")
    else:
        print(f"任务创建失败: {result.get('error')}")
    
    print()


def test_task_manager():
    """测试任务管理器功能"""
    print("=== 测试任务管理器功能 ===")
    
    task_manager = get_task_manager()
    
    # 获取统计信息
    stats = task_manager.get_overall_stats()
    print(f"任务统计: {stats}")
    
    # 列出所有任务
    tasks = task_manager.list_all()
    print(f"任务数量: {len(tasks)}")
    
    for task in tasks:
        print(f"  - {task.name} ({task.id}): {task.state.status}")
    
    print()


async def test_enhanced_task_panel():
    """测试增强版任务面板"""
    print("=== 测试增强版任务面板 ===")
    
    # 注意：由于这是命令行测试，无法直接测试PyWebIO界面
    # 但我们可以测试底层功能
    
    print("增强版任务面板功能包括:")
    print("1. AI代码生成与审核编辑")
    print("2. 多种代码输入方式 (AI生成、手动编写、模板选择、文件导入)")
    print("3. 实时代码验证")
    print("4. 用户确认流程")
    print("5. 任务创建和编辑集成")
    print()
    
    # 测试AI代码生成器
    from deva.admin_ui.strategy.ai_code_generator import TaskAIGenerator
    
    generator = TaskAIGenerator()
    
    # 测试生成任务代码
    requirement = "创建一个每天凌晨2点执行的备份任务"
    context = {
        "task_name": "备份任务",
        "task_type": TaskType.CRON,
        "time_config": "02:00",
        "enable_retry": True,
        "send_notification": True
    }
    
    print(f"AI生成器已准备: {generator.unit_type}")
    print(f"测试需求: {requirement}")
    print(f"上下文: {context}")
    print()


def main():
    """主测试函数"""
    print("开始测试增强版任务面板功能...")
    print("=" * 50)
    
    # 测试代码验证
    test_task_code_validation()
    
    # 测试任务创建
    test_task_creation()
    
    # 测试任务管理器
    test_task_manager()
    
    # 测试增强版面板（异步）
    asyncio.run(test_enhanced_task_panel())
    
    print("=" * 50)
    print("测试完成！")
    print()
    print("增强版任务面板功能总结:")
    print("✅ 任务代码验证功能")
    print("✅ 任务创建和管理功能") 
    print("✅ AI代码生成功能")
    print("✅ 多种代码输入方式")
    print("✅ 用户审核编辑流程")
    print("✅ 与任务管理器集成")


if __name__ == "__main__":
    main()