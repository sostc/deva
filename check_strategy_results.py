#!/usr/bin/env python3
"""
检查策略执行结果
"""

import time
from deva.naja.strategy import get_strategy_manager


def main():
    """主函数"""
    # 等待一段时间，让策略有时间执行
    print("等待 10 秒，让策略有时间执行...")
    time.sleep(10)
    
    # 获取策略管理器
    st_mgr = get_strategy_manager()
    
    # 加载数据
    st_mgr.load_from_db()
    
    # 查找 river 策略
    river_strategies = [s for s in st_mgr.list_all() if 'river' in s.name.lower()]
    
    print(f"检查 {len(river_strategies)} 个 river 策略的执行结果:")
    for s in river_strategies:
        recent_results = s.get_recent_results(limit=3)
        print(f"\n  {s.name}:")
        print(f"    运行中: {s.is_running}")
        print(f"    最近执行结果: {len(recent_results)} 条")
        
        if recent_results:
            for i, result in enumerate(recent_results):
                timestamp = result.get('ts')
                success = result.get('success')
                output_data = result.get('output_full')
                output_str = str(output_data)[:50] + '...' if output_data else 'None'
                print(f"    {i+1}. 时间: {timestamp}, 成功: {success}, 输出: {output_str}")


if __name__ == "__main__":
    main()
