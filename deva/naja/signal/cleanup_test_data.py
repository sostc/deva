"""清理测试数据脚本

删除所有 test_strategy 开头的策略执行数据
"""

from deva.naja.strategy.result_store import get_result_store
from deva.naja.signal.stream import get_signal_stream


def cleanup_test_data():
    """清理测试数据"""
    print("开始清理 test_strategy 开头的策略执行数据...")
    
    # 获取结果存储
    result_store = get_result_store()
    
    # 获取所有策略执行结果
    all_results = result_store.query(limit=10000)  # 获取足够多的结果
    
    # 过滤出 test_strategy 开头的策略
    test_results = [r for r in all_results if r.strategy_name.startswith('test_strategy')]
    
    print(f"找到 {len(test_results)} 条 test_strategy 开头的策略执行数据")
    
    # 删除这些数据
    deleted_count = 0
    for i, result in enumerate(test_results):
        try:
            if result_store.delete(result.id):
                deleted_count += 1
                print(f"删除数据 {i+1}/{len(test_results)}: {result.id} - {result.strategy_name}")
        except Exception as e:
            print(f"删除数据 {result.id} 失败: {e}")
    
    print(f"删除完成，共删除 {deleted_count} 条数据")
    
    # 清理 SignalStream 中的数据
    print("清理 SignalStream 中的数据...")
    signal_stream = get_signal_stream()
    signal_stream.clear()
    print("SignalStream 数据清理完成")


if __name__ == "__main__":
    cleanup_test_data()
