"""
注册龙虾思想雷达策略到naja策略数据库

创建新的"记忆系统"类别，绑定行情回放数据源
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva.naja.strategy import get_strategy_manager, StrategyMetadata
from deva.naja.datasource import get_datasource_manager
from deva import NB


def register_memory_strategy():
    """注册龙虾思想雷达策略"""
    
    strategy_mgr = get_strategy_manager()
    datasource_mgr = get_datasource_manager()
    
    # 检查是否已存在
    existing = strategy_mgr.get_by_name("龙虾思想雷达")
    if existing:
        print("[INFO] 策略 '龙虾思想雷达' 已存在，ID:", existing.id)
        return existing
    
    # 查找行情回放数据源
    replay_ds = None
    for ds in datasource_mgr.list_all():
        if 'replay' in ds.name.lower() or '回放' in ds.name:
            replay_ds = ds
            print(f"[INFO] 找到行情回放数据源: {ds.name} (ID: {ds.id})")
            break
    
    if not replay_ds:
        print("[WARN] 未找到行情回放数据源，将创建策略但不绑定数据源")
        replay_ds_id = ""
    else:
        replay_ds_id = replay_ds.id
    
    # 策略代码
    strategy_code = '''
"""
龙虾思想雷达策略 - 实时记忆系统
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva.naja.memory import get_memory_engine

# 初始化策略实例（记忆引擎单例）
_radar = get_memory_engine()

def process(record):
    """
    处理单条记录
    
    Args:
        record: 数据源记录
        
    Returns:
        信号列表或处理结果
    """
    signals = _radar.process_record(record)
    
    # 输出信号到日志
    for signal in signals:
        print(f"[LOBSTER_SIGNAL] {signal['type']}: {signal['message']}")
    
    # 返回信号列表
    return {
        "signals": signals,
        "stats": _radar.get_memory_report(),
    }

# 可选：窗口处理函数
def process_window(records):
    """
    处理窗口数据
    
    Args:
        records: 记录列表
        
    Returns:
        处理结果
    """
    signals = _radar.process_window(records)
    return {
        "signals": signals,
        "window_size": len(records),
        "stats": _radar.get_memory_report(),
    }
'''
    
    # 创建策略
    result = strategy_mgr.create(
        name="龙虾思想雷达",
        func_code=strategy_code,
        bound_datasource_id=replay_ds_id,
        description="流式学习 + 分层记忆 + 周期性自我反思。实时分析tick、新闻、文本数据，生成主题信号和注意力信号。",
        compute_mode="record",  # 逐条处理
        category="记忆系统",  # 新类别
        tags=["记忆", "主题分析", "注意力", "流式学习", "River"],
        max_history_count=100,
    )
    
    if result["success"]:
        print(f"[SUCCESS] 策略创建成功!")
        print(f"  ID: {result['id']}")
        print(f"  名称: 龙虾思想雷达")
        print(f"  类别: 记忆系统")
        print(f"  绑定数据源: {replay_ds_id or '无'}")
        
        # 获取策略实例并启动
        entry_id = result['id']
        entry = strategy_mgr.get(entry_id)
        if entry:
            start_result = entry.start()
            if start_result.get("success"):
                print(f"[SUCCESS] 策略已启动")
            else:
                print(f"[WARN] 策略启动失败: {start_result.get('error', '未知错误')}")
        
        return entry
    else:
        print(f"[ERROR] 策略创建失败: {result.get('error')}")
        return None


def create_memory_system_category():
    """创建记忆系统类别（如果不存在）"""
    
    # 获取所有策略
    strategy_mgr = get_strategy_manager()
    all_strategies = strategy_mgr.list_all()
    
    # 收集现有类别
    categories = set()
    for strategy in all_strategies:
        cat = getattr(strategy._metadata, "category", "默认")
        if cat:
            categories.add(cat)
    
    if "记忆系统" in categories:
        print("[INFO] 类别 '记忆系统' 已存在")
    else:
        print("[INFO] 类别 '记忆系统' 将在创建策略时自动创建")
    
    return categories


def bind_replay_datasource():
    """绑定行情回放数据源到策略"""
    
    strategy_mgr = get_strategy_manager()
    datasource_mgr = get_datasource_manager()
    
    # 查找策略
    strategy = strategy_mgr.get_by_name("龙虾思想雷达")
    if not strategy:
        print("[ERROR] 策略 '龙虾思想雷达' 不存在")
        return False
    
    # 查找行情回放数据源
    replay_ds = None
    for ds in datasource_mgr.list_all():
        if 'replay' in ds.name.lower() or '回放' in ds.name or '行情' in ds.name:
            replay_ds = ds
            break
    
    if not replay_ds:
        print("[ERROR] 未找到行情回放数据源")
        return False
    
    # 绑定数据源
    strategy._metadata.bound_datasource_id = replay_ds.id
    strategy.save()
    
    # 重新启动以应用绑定
    strategy.stop()
    start_result = strategy.start()
    
    if start_result.get("success"):
        print(f"[SUCCESS] 已绑定行情回放数据源: {replay_ds.name} (ID: {replay_ds.id})")
        return True
    else:
        print(f"[ERROR] 绑定失败: {start_result.get('error')}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("🦞 龙虾思想雷达策略注册工具")
    print("=" * 60)
    print()
    
    # 1. 检查现有类别
    print("[1/3] 检查策略类别...")
    categories = create_memory_system_category()
    print(f"  现有类别: {', '.join(sorted(categories)) if categories else '无'}")
    print()
    
    # 2. 注册策略
    print("[2/3] 注册龙虾思想雷达策略...")
    strategy = register_memory_strategy()
    print()
    
    # 3. 绑定数据源
    if strategy:
        print("[3/3] 绑定行情回放数据源...")
        bind_replay_datasource()
        print()
    
    print("=" * 60)
    print("✅ 注册完成!")
    print("=" * 60)
    print()
    print("使用说明:")
    print("  1. 启动naja: python -m deva.naja")
    print("  2. 访问策略管理: http://localhost:8080/strategyadmin")
    print("  3. 查看记忆: http://localhost:8080/memory")
    print()
    print("策略信息:")
    if strategy:
        print(f"  名称: 龙虾思想雷达")
        print(f"  类别: 记忆系统")
        print(f"  ID: {strategy.id}")
        print(f"  状态: {'运行中' if strategy.is_running else '已停止'}")


if __name__ == "__main__":
    main()
