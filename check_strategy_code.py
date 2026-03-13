#!/usr/bin/env python3
"""
检查策略代码
"""

from deva.naja.strategy import get_strategy_manager


def main():
    """主函数"""
    # 获取策略管理器
    st_mgr = get_strategy_manager()
    
    # 加载数据
    st_mgr.load_from_db()
    
    # 查找 river 策略
    river_strategies = [s for s in st_mgr.list_all() if 'river' in s.name.lower()]
    
    print(f"检查 {len(river_strategies)} 个 river 策略的代码:")
    for s in river_strategies:
        print(f"\n  {s.name} (ID: {s.id}):")
        print(f"    代码长度: {len(s._func_code)} 字符")
        print(f"    前 200 字符: {s._func_code[:200]}...")


if __name__ == "__main__":
    main()
