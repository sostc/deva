"""信号迁移脚本

将之前存储在 result_store 中的信号迁移到新的 SignalStream 中
"""

from deva.naja.strategy.result_store import get_result_store
from deva.naja.signal.stream import get_signal_stream


def migrate_signals(limit: int = 30):
    """迁移信号
    
    Args:
        limit: 迁移的信号数量
    """
    print(f"开始迁移最近 {limit} 条信号到新的 SignalStream...")
    
    # 获取结果存储和信号流
    result_store = get_result_store()
    signal_stream = get_signal_stream()
    
    # 直接从数据库中获取所有信号
    all_results = result_store.query(limit=1000)  # 获取足够多的信号
    
    # 按时间戳排序，取最近的 limit 条
    all_results.sort(key=lambda x: x.ts, reverse=True)
    recent_results = all_results[:limit]
    
    print(f"找到 {len(recent_results)} 条信号，开始迁移...")
    
    # 迁移信号
    for i, result in enumerate(recent_results):
        try:
            signal_stream.update(result)
            print(f"迁移信号 {i+1}/{len(recent_results)}: {result.id}")
        except Exception as e:
            print(f"迁移信号 {result.id} 失败: {e}")
    
    print(f"迁移完成，共迁移 {len(recent_results)} 条信号")
    print(f"当前 SignalStream 缓存大小: {len(signal_stream.cache)}")
    
    # 验证持久化
    try:
        # 重新获取信号流实例，验证数据是否持久化
        new_signal_stream = get_signal_stream()
        print(f"重新加载后 SignalStream 缓存大小: {len(new_signal_stream.cache)}")
        if len(new_signal_stream.cache) > 0:
            print("持久化成功！")
        else:
            print("持久化失败！")
    except Exception as e:
        print(f"验证持久化失败: {e}")


if __name__ == "__main__":
    migrate_signals(limit=30)
