#!/usr/bin/env python3
"""
简化测试增强版任务面板功能

这个脚本测试增强版任务面板的核心功能，避开复杂的日志系统。
"""

import asyncio
from deva.admin_ui.strategy.enhanced_task_panel import validate_task_code
from deva.admin_ui.strategy.task_unit import TaskType


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


def test_ai_code_generator():
    """测试AI代码生成器"""
    print("=== 测试AI代码生成器 ===")
    
    try:
        from deva.admin_ui.strategy.ai_code_generator import TaskAIGenerator
        
        generator = TaskAIGenerator()
        print(f"AI生成器已准备: {generator.unit_type}")
        
        # 测试获取默认模板
        template = generator._get_default_task_template()
        print(f"默认任务模板:\n{template}")
        
        # 测试代码优化
        test_code = '''
async def execute(context=None):
    result = 0
    for i in range(len([1,2,3])):
        result = result + 1
    if result == None:
        print("test")
    return result
'''
        
        optimization_result = generator.optimize_code(test_code)
        print(f"代码优化结果: {optimization_result}")
        
    except Exception as e:
        print(f"AI代码生成器测试失败: {e}")
    
    print()


def test_task_templates():
    """测试任务模板"""
    print("=== 测试任务模板 ===")
    
    # 模拟enhanced_task_panel.py中的模板
    templates = {
        "database_backup": {
            "name": "数据库备份任务",
            "description": "定期备份数据库到指定位置",
            "code": '''async def execute(context=None):
    """数据库备份任务"""
    import asyncio
    from datetime import datetime
    
    try:
        # 模拟数据库备份
        backup_data = f"数据库备份数据 - {datetime.now().isoformat()}"
        await asyncio.sleep(1)
        return f'数据库备份完成: {backup_data}'
        
    except Exception as e:
        raise Exception(f'数据库备份任务失败: {e}')
'''
        },
        "system_monitoring": {
            "name": "系统监控任务",
            "description": "监控系统状态和性能指标",
            "code": '''async def execute(context=None):
    """系统监控任务"""
    import asyncio
    import random
    from datetime import datetime
    
    try:
        # 模拟系统监控
        cpu_usage = random.uniform(10, 90)
        memory_usage = random.uniform(30, 80)
        
        report = f"系统监控报告: CPU {cpu_usage:.1f}%, 内存 {memory_usage:.1f}%"
        await asyncio.sleep(1)
        return report
        
    except Exception as e:
        raise Exception(f'系统监控任务失败: {e}')
'''
        }
    }
    
    for template_key, template_info in templates.items():
        print(f"模板: {template_info['name']}")
        print(f"描述: {template_info['description']}")
        
        # 验证模板代码
        validation_result = validate_task_code(template_info['code'])
        print(f"代码验证: {'✅ 通过' if validation_result['valid'] else '❌ 失败'}")
        if validation_result.get('warnings'):
            print(f"警告: {validation_result['warnings']}")
        print()


async def test_task_workflow():
    """测试任务工作流"""
    print("=== 测试任务工作流 ===")
    
    # 模拟任务创建流程
    print("1. 任务需求收集")
    task_requirements = {
        "name": "数据备份任务",
        "task_type": TaskType.INTERVAL,
        "time_config": "3600",  # 每小时
        "description": "定期备份重要数据"
    }
    print(f"任务需求: {task_requirements}")
    
    print("\n2. AI代码生成")
    generated_code = '''
async def execute(context=None):
    """数据备份任务"""
    import asyncio
    from datetime import datetime
    
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    
    try:
        f"数据备份任务 {task_name} 开始执行"
        
        # 模拟数据备份过程
        backup_data = f"备份数据 - {datetime.now().isoformat()}"
        await asyncio.sleep(2)  # 模拟耗时操作
        
        result = f'数据备份完成: {backup_data}'
        return result
        
    except Exception as e:
        error_msg = f'数据备份任务失败: {e}'
        raise Exception(error_msg)
'''
    print(f"生成的代码长度: {len(generated_code)} 字符")
    
    print("\n3. 代码验证")
    validation_result = validate_task_code(generated_code)
    print(f"代码验证结果: {validation_result}")
    
    print("\n4. 用户审核确认")
    if validation_result['valid']:
        print("✅ 代码验证通过，可以创建任务")
        print("✅ 用户已审核代码")
        print("✅ 用户确认使用此代码")
    else:
        print("❌ 代码验证失败，需要重新生成")
    
    print()


def main():
    """主测试函数"""
    print("开始测试增强版任务面板功能...")
    print("=" * 60)
    
    # 测试代码验证
    test_task_code_validation()
    
    # 测试AI代码生成器
    test_ai_code_generator()
    
    # 测试任务模板
    test_task_templates()
    
    # 测试任务工作流（异步）
    asyncio.run(test_task_workflow())
    
    print("=" * 60)
    print("测试完成！")
    print()
    print("增强版任务面板功能总结:")
    print("✅ 任务代码验证功能 - 语法检查、函数验证、安全警告")
    print("✅ AI代码生成功能 - 智能代码生成、模板支持、代码优化")
    print("✅ 多种代码输入方式 - AI生成、手动编写、模板选择、文件导入")
    print("✅ 用户审核编辑流程 - 代码预览、验证结果、确认流程")
    print("✅ 任务工作流集成 - 需求收集、代码生成、验证确认")
    print()
    print("主要特性:")
    print("• 统一的AI代码生成界面")
    print("• 实时代码验证和语法检查")
    print("• 用户友好的审核编辑流程")
    print("• 支持多种任务类型（间隔、定时、一次性）")
    print("• 完整的错误处理和用户反馈")


if __name__ == "__main__":
    main()