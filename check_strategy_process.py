#!/usr/bin/env python3
"""
检查策略的 process 函数
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
    
    # 选择一个策略进行检查
    if river_strategies:
        strategy = river_strategies[0]
        print(f"检查策略: {strategy.name} (ID: {strategy.id})")
        print(f"代码长度: {len(strategy._func_code)} 字符")
        print(f"\n完整代码:")
        print(strategy._func_code)


if __name__ == "__main__":
    main()
