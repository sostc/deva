#!/usr/bin/env python3
"""
测试优雅的美林时钟目录结构

验证新目录结构和导入是否正常工作。
"""

import sys
import os

# 添加路径以便导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_module_imports():
    """测试模块导入是否正常"""
    print("🔍 测试美林时钟模块导入...")
    
    try:
        # 测试标准导入
        from deva.naja.cognition.merrill_clock import (
            get_engine,
            get_merrill_clock_engine,
            initialize_merrill_clock,
            MerrillClockPhase,
            get_macro_signal,
            get_merrill_phase_display,
            EconomicData,
            render_web_ui,
            generate_markdown_report,
        )
        
        print("✅ 所有标准导入成功！")
        
        # 测试优雅的别名
        assert get_engine == get_merrill_clock_engine, "get_engine 别名不正确"
        print("✅ 优雅别名功能正常")
        
        # 测试枚举
        assert MerrillClockPhase.RECOVERY.value == "RECOVERY", "枚举值不正确"
        print("✅ 枚举类型可访问")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except AssertionError as e:
        print(f"❌ 断言失败: {e}")
        return False

def test_function_calls():
    """测试函数调用是否正常"""
    print("\n🔍 测试美林时钟函数调用...")
    
    try:
        from deva.naja.cognition.merrill_clock import (
            get_engine,
            MerrillClockPhase,
            get_merrill_phase_display,
        )
        
        # 获取引擎实例
        engine = get_engine()
        print("✅ 成功获取引擎实例")
        
        # 测试枚举转换函数
        phase_display = get_merrill_phase_display(MerrillClockPhase.RECOVERY)
        assert phase_display == "复苏", f"阶段显示不正确: {phase_display}"
        print(f"✅ 阶段显示转换正常: {phase_display}")
        
        # 测试空值处理
        unknown_display = get_merrill_phase_display(None)
        assert unknown_display == "未知", f"空值显示不正确: {unknown_display}"
        print(f"✅ 空值处理正常: {unknown_display}")
        
        return True
        
    except Exception as e:
        print(f"❌ 函数调用失败: {e}")
        return False

def test_integration():
    """测试与其他系统的集成"""
    print("\n🔍 测试与认知信号总线的集成...")
    
    try:
        # 测试是否能导入认知信号总线并访问相关功能
        from deva.naja.events import NajaEventBus, get_event_bus
        
        print("✅ 可以访问Naja事件总线")
        
        # 测试经济数据获取器是否能工作
        from deva.naja.cognition.merrill_clock.economic_data_fetcher import EconomicDataFetcher
        
        print("✅ 经济数据获取器可导入")
        
        return True
        
    except Exception as e:
        print(f"⚠️ 集成测试警告: {e} (这可能是正常现象)")
        return False

def main():
    print("=" * 80)
    print("🧪 测试优雅的美林时钟目录结构")
    print("=" * 80)
    
    all_passed = True
    
    # 运行测试
    if not test_module_imports():
        all_passed = False
        
    if not test_function_calls():
        all_passed = False
        
    if not test_integration():
        all_passed = False
    
    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 所有测试通过！美林时钟目录结构优雅可用！")
        print("✨ 目录重构完成，系统保持向后兼容性")
    else:
        print("⚠️ 部分测试失败，请检查导入路径")
    
    print("=" * 80)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())