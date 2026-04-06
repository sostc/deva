"""数据源管理页面加载性能分析"""

import time
import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

print("=" * 60)
print("数据源管理页面加载性能分析")
print("=" * 60)

# 1. 导入模块
t0 = time.time()
from deva.naja.datasource import get_datasource_manager
from deva import NB
t_import = time.time() - t0
print(f"\n[1] 导入模块耗时: {t_import:.3f}s")

# 2. 获取并初始化管理器
t1 = time.time()
mgr = get_datasource_manager()
mgr._ensure_initialized()
t_init = time.time() - t1
print(f"[2] 管理器初始化耗时: {t_init:.3f}s")

# 3. 检查状态
print(f"\n    mgr._initialized = {getattr(mgr, '_initialized', False)}")
print(f"    mgr._loaded_prefer_files = {getattr(mgr, '_loaded_prefer_files', False)}")
print(f"    当前 _items 数量: {len(getattr(mgr, '_items', {}))}")

# 4. list_all
t3 = time.time()
entries = mgr.list_all()
t_list = time.time() - t3
print(f"\n[3] list_all() 耗时: {t_list:.3f}s, 获取了 {len(entries)} 个条目")

# 5. 分别测量 get_stats 的各个部分
print(f"\n[4] 分析 get_stats() 耗时...")
t4 = time.time()
entries_for_stats = mgr.list_all()
t_list_again = time.time() - t4
print(f"    list_all 重试: {t_list_again:.3f}s")

t5 = time.time()
running = sum(1 for e in entries_for_stats if e.is_running)
t_running = time.time() - t5
print(f"    统计 running: {t_running:.3f}s")

t6 = time.time()
error = sum(1 for e in entries_for_stats if e._state.error_count > 0)
t_error = time.time() - t6
print(f"    统计 error: {t_error:.3f}s")

t7 = time.time()
attention_stats = mgr.get_attention_stats()
t_attention = time.time() - t7
print(f"    get_attention_stats: {t_attention:.3f}s")

print(f"\n[5] get_stats 总耗时分解:")
print(f"    list_all:       {t_list_again:.3f}s")
print(f"    统计 running:   {t_running:.3f}s")
print(f"    统计 error:     {t_error:.3f}s")
print(f"    attention_stats: {t_attention:.3f}s (最大瓶颈!)")
print(f"    合计:           {t_list_again + t_running + t_error + t_attention:.3f}s")

# 6. 直接测试 get_attention_stats 内部
print(f"\n[6] 深入分析 get_attention_stats()...")
t8 = time.time()
try:
    from deva.naja.attention.realtime_data_fetcher import get_data_fetcher
    t9 = time.time()
    print(f"    导入 get_data_fetcher: {t9 - t8:.3f}s")

    fetcher = get_data_fetcher()
    t10 = time.time()
    print(f"    get_data_fetcher(): {t10 - t9:.3f}s")

    if fetcher and hasattr(fetcher, 'get_stats'):
        stats = fetcher.get_stats()
        t11 = time.time()
        print(f"    fetcher.get_stats(): {t11 - t10:.3f}s")
except ImportError as e:
    print(f"    ImportError: {e}")
except Exception as e:
    print(f"    Error: {e}")

# 总结
print("\n" + "=" * 60)
print("结论")
print("=" * 60)
print(f"页面加载瓶颈: get_attention_stats() 耗时 {t_attention:.3f}s")
print(f"原因: 实时数据获取器初始化或统计计算耗时")