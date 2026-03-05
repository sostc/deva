"""测试信号流持久化

验证信号流数据在程序重启后是否能够正确加载
"""

from deva.naja.signal.stream import get_signal_stream


def test_persistence():
    """测试持久化功能"""
    print("测试信号流持久化功能...")
    
    # 获取信号流实例
    signal_stream = get_signal_stream()
    
    # 打印当前缓存大小
    print(f"当前 SignalStream 缓存大小: {len(signal_stream.cache)}")
    
    # 打印最近的几条信号
    recent_signals = signal_stream.get_recent(limit=5)
    print(f"最近 {len(recent_signals)} 条信号:")
    for i, signal in enumerate(recent_signals):
        print(f"  {i+1}. {signal.id} - {signal.strategy_name} - {signal.ts}")
    
    # 验证缓存大小是否大于0
    if len(signal_stream.cache) > 0:
        print("\n✓ 持久化测试成功！信号数据已正确加载")
    else:
        print("\n✗ 持久化测试失败！缓存为空")


if __name__ == "__main__":
    test_persistence()
