"""任务模块优化使用指南和迁移示例

展示如何使用新的统一架构来重构和优化任务模块。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# 导入新的统一架构组件
from deva.admin_ui.strategy.task_unit import TaskUnit, TaskMetadata, TaskState, TaskExecution, TaskType, TaskStatus
from deva.admin_ui.strategy.task_manager import TaskManager, get_task_manager
from deva.admin_ui.strategy.task_ai_generator import TaskAIGenerator
from deva.admin_ui.strategy.task_stream_integration import TaskStreamManager, get_task_stream_manager
from deva.admin_ui.strategy.error_handler import ErrorHandler, ErrorLevel, ErrorCategory
from deva.admin_ui.strategy.persistence import get_global_persistence_manager


# ==========================================================================
# 示例1: 创建和配置任务单元
# ==========================================================================

def create_sample_task() -> TaskUnit:
    """创建示例任务"""
    
    # 创建任务元数据
    metadata = TaskMetadata(
        id="sample_task_001",
        name="数据备份任务",
        description="每天凌晨2点执行数据备份",
        task_type=TaskType.CRON,
        schedule_config={"hour": 2, "minute": 0},
        retry_config={"max_retries": 3, "retry_interval": 300},
        tags=["backup", "daily", "critical"]
    )
    
    # 创建任务状态
    state = TaskState(
        status=TaskStatus.STOPPED,
        last_run_time=0,
        next_run_time=0,
        run_count=0,
        error_count=0
    )
    
    # 创建任务执行信息
    execution = TaskExecution(
        job_code='''async def execute(context=None):
    """数据备份任务"""
    import asyncio
    import time
    from datetime import datetime
    from deva import log, write_to_file
    
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    start_time = time.time()
    
    try:
        # 任务开始
        f'数据备份任务 {task_name} 开始执行' >> log
        
        # 模拟数据备份
        backup_data = f"备份数据 - {datetime.now().isoformat()}"
        backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        # 写入备份文件
        backup_data >> write_to_file(backup_file)
        
        # 模拟备份过程
        await asyncio.sleep(2)
        
        result = f'数据备份完成: {backup_file} (耗时: {time.time() - start_time:.2f}s)'
        result >> log
        
        return result
        
    except Exception as e:
        error_msg = f'数据备份任务失败: {e}'
        error_msg >> log
        raise
''',
        execution_history=[]
    )
    
    # 创建任务单元
    task_unit = TaskUnit(
        metadata=metadata,
        state=state,
        execution=execution
    )
    
    return task_unit


# ==========================================================================
# 示例2: 使用任务管理器
# ==========================================================================

async def demo_task_manager():
    """演示任务管理器的使用"""
    
    # 获取任务管理器
    task_manager = get_task_manager()
    
    # 创建示例任务
    task = create_sample_task()
    
    # 注册任务
    register_result = task_manager.register(task)
    print(f"任务注册结果: {register_result}")
    
    # 启动任务
    start_result = task_manager.start(task.id)
    print(f"任务启动结果: {start_result}")
    
    # 获取任务统计
    task_stats = task_manager.get_task_stats(task.id)
    print(f"任务统计: {task_stats}")
    
    # 获取整体统计
    overall_stats = task_manager.get_overall_stats()
    print(f"整体统计: {overall_stats}")
    
    # 等待任务执行
    await asyncio.sleep(5)
    
    # 停止任务
    stop_result = task_manager.stop(task.id)
    print(f"任务停止结果: {stop_result}")


# ==========================================================================
# 示例3: 使用AI代码生成器
# ==========================================================================

def demo_ai_code_generation():
    """演示AI代码生成"""
    
    # 创建AI生成器
    ai_generator = TaskAIGenerator()
    
    # 生成监控任务代码
    requirement = "监控网站可用性，如果网站无法访问则发送钉钉通知"
    
    result = ai_generator.generate_task_code(
        requirement=requirement,
        task_type=TaskType.INTERVAL,
        context={"monitoring_url": "https://example.com"},
        include_monitoring=True,
        include_retry=True
    )
    
    if result["success"]:
        print("=== 生成的任务代码 ===")
        print(result["code"])
        print("\n=== 代码说明 ===")
        print(result["explanation"])
        
        # 验证代码
        validation_result = ai_generator.validate_task_code(result["code"], TaskType.INTERVAL)
        print(f"\n=== 代码验证结果 ===")
        print(f"验证成功: {validation_result['success']}")
        if validation_result.get("warnings"):
            print(f"警告: {validation_result['warnings']}")
    else:
        print(f"代码生成失败: {result['error']}")


# ==========================================================================
# 示例4: 任务流处理集成
# ==========================================================================

async def demo_task_stream_integration():
    """演示任务流处理集成"""
    
    # 获取任务流管理器
    stream_manager = get_task_stream_manager()
    task_manager = get_task_manager()
    
    # 创建数据生产任务
    producer_metadata = TaskMetadata(
        id="data_producer_001",
        name="数据生产者",
        description="生成模拟数据",
        task_type=TaskType.INTERVAL,
        schedule_config={"interval": 5},
        func_code='''async def execute(context=None):
    import random
    import time
    from deva import log
    
    # 生成模拟数据
    data = {
        "timestamp": time.time(),
        "value": random.randint(1, 100),
        "type": "sensor_data"
    }
    
    f'生成数据: {data["value"]}' >> log
    return data
'''
    )
    
    producer_task = TaskUnit(
        metadata=producer_metadata,
        state=TaskState(),
        execution=TaskExecution()
    )
    
    # 创建数据处理任务
    processor_metadata = TaskMetadata(
        id="data_processor_001", 
        name="数据处理器",
        description="处理和分析数据",
        task_type=TaskType.INTERVAL,
        schedule_config={"interval": 1},
        func_code='''async def execute(context=None):
    import time
    from deva import log
    
    # 获取流数据（如果有）
    stream_data = context.get("stream_data") if context else None
    
    if stream_data:
        # 处理流数据
        processed_value = stream_data.get("value", 0) * 2
        result = {
            "original": stream_data,
            "processed": {"value": processed_value, "processed_at": time.time()}
        }
        f'处理数据: {processed_value}' >> log
    else:
        # 独立处理
        result = {"status": "no_data", "timestamp": time.time()}
        f'无流数据，独立处理' >> log
    
    return result
'''
    )
    
    processor_task = TaskUnit(
        metadata=processor_metadata,
        state=TaskState(),
        execution=TaskExecution()
    )
    
    # 注册任务
    task_manager.register(producer_task)
    task_manager.register(processor_task)
    
    # 创建任务流
    producer_output = stream_manager.create_task_output_stream(producer_task)
    processor_input = stream_manager.create_task_input_stream(processor_task)
    
    # 连接任务流
    stream_manager.connect_tasks(
        source_task_id=producer_task.id,
        target_task_id=processor_task.id,
        transform_func=lambda data: {"value": data.get("value", 0), "source": "producer"},
        filter_func=lambda data: data.get("value", 0) > 50
    )
    
    # 启动任务
    task_manager.start(producer_task.id)
    task_manager.start(processor_task.id)
    
    # 等待数据流转
    await asyncio.sleep(10)
    
    # 获取流指标
    producer_metrics = stream_manager.get_task_stream_metrics(producer_task.id)
    processor_metrics = stream_manager.get_task_stream_metrics(processor_task.id)
    
    print("=== 生产者任务流指标 ===")
    print(producer_metrics)
    print("\n=== 处理器任务流指标 ===")
    print(processor_metrics)
    
    # 停止任务
    task_manager.stop(producer_task.id)
    task_manager.stop(processor_task.id)


# ==========================================================================
# 示例5: 错误处理和监控
# ==========================================================================

def demo_error_handling():
    """演示错误处理"""
    
    # 创建任务
    task = create_sample_task()
    
    # 获取错误处理器
    error_handler = ErrorHandler(task)
    
    # 模拟不同类型的错误
    try:
        # 模拟代码执行错误
        raise ValueError("测试错误")
    except Exception as e:
        # 处理错误
        error_record = error_handler.handle_code_error(
            e,
            context="测试错误处理",
            data={"test": "data"}
        )
        
        print(f"错误已记录: {error_record.error_id}")
        print(f"错误级别: {error_record.level}")
        print(f"错误分类: {error_record.category}")
    
    # 获取错误统计
    from deva.admin_ui.strategy.error_handler import get_global_error_collector
    error_collector = get_global_error_collector()
    error_stats = error_collector.get_error_stats()
    
    print(f"\n错误统计: {error_stats}")


# ==========================================================================
# 示例6: 迁移指南 - 从旧任务系统迁移
# ==========================================================================

def migration_guide():
    """迁移指南"""
    
    print("=== 任务模块迁移指南 ===")
    print("\n1. 旧系统任务结构:")
    old_task = {
        "type": "interval",
        "time": "60",
        "status": "运行中",
        "description": "旧任务描述",
        "job_code": "async def old_task(): pass",
        "retry_count": 3,
        "retry_interval": 5
    }
    print(f"旧任务: {old_task}")
    
    print("\n2. 新系统任务结构:")
    # 转换旧任务到新格式
    new_task = convert_old_task_to_new(old_task, "old_task_001", "迁移的旧任务")
    print(f"新任务: {new_task.to_dict()}")
    
    print("\n3. 迁移步骤:")
    print("a) 使用TaskUnit.from_dict()转换旧数据")
    print("b) 注册到新的TaskManager")
    print("c) 启动任务并验证功能")
    print("d) 使用新的错误处理和监控功能")
    
    print("\n4. 新增功能:")
    print("- ✅ 统一的生命周期管理")
    print("- ✅ 专业的错误处理系统")
    print("- ✅ 流处理集成能力")
    print("- ✅ AI代码生成功能")
    print("- ✅ 详细的执行统计")
    print("- ✅ 任务依赖管理")
    print("- ✅ 事件驱动机制")


def convert_old_task_to_new(old_task: dict, task_id: str, name: str) -> TaskUnit:
    """转换旧任务到新格式"""
    
    # 转换任务类型
    task_type = TaskType.INTERVAL if old_task["type"] == "interval" else TaskType.CRON
    
    # 转换调度配置
    schedule_config = {}
    if task_type == TaskType.INTERVAL:
        schedule_config["interval"] = int(old_task["time"])
    else:
        # 假设cron格式为 HH:MM
        hour, minute = map(int, old_task["time"].split(":"))
        schedule_config["hour"] = hour
        schedule_config["minute"] = minute
    
    # 转换重试配置
    retry_config = {
        "max_retries": old_task.get("retry_count", 0),
        "retry_interval": old_task.get("retry_interval", 5)
    }
    
    # 创建新任务元数据
    metadata = TaskMetadata(
        id=task_id,
        name=name,
        description=old_task["description"],
        task_type=task_type,
        schedule_config=schedule_config,
        retry_config=retry_config,
        func_code=old_task["job_code"]
    )
    
    # 创建任务状态
    state = TaskState(
        status=TaskStatus.STOPPED,  # 默认停止状态
        last_run_time=0,
        next_run_time=0,
        run_count=0,
        error_count=0
    )
    
    # 创建执行信息
    execution = TaskExecution(
        job_code=old_task["job_code"],
        execution_history=[]
    )
    
    # 创建任务单元
    return TaskUnit(metadata=metadata, state=state, execution=execution)


# ==========================================================================
# 主函数 - 运行所有演示
# ==========================================================================

async def main():
    """主函数"""
    
    print("=== 任务模块统一架构演示 ===\n")
    
    # 1. 演示任务管理器
    print("1. 任务管理器演示...")
    await demo_task_manager()
    print("\n" + "="*50 + "\n")
    
    # 2. 演示AI代码生成
    print("2. AI代码生成演示...")
    demo_ai_code_generation()
    print("\n" + "="*50 + "\n")
    
    # 3. 演示流处理集成
    print("3. 流处理集成演示...")
    await demo_task_stream_integration()
    print("\n" + "="*50 + "\n")
    
    # 4. 演示错误处理
    print("4. 错误处理演示...")
    demo_error_handling()
    print("\n" + "="*50 + "\n")
    
    # 5. 迁移指南
    print("5. 迁移指南...")
    migration_guide()
    print("\n" + "="*50 + "\n")
    
    print("=== 演示完成 ===")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(main())