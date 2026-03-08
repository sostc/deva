#!/usr/bin/env python3
"""检查策略数据源绑定和执行状态"""

import logging
from deva.naja.strategy import get_strategy_manager
from deva.naja.datasource import get_datasource_manager
from deva.naja.signal.stream import get_signal_stream

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("【检查策略数据源绑定和执行状态】")
    logger.info("=" * 80)
    
    # 加载数据源
    datasource_mgr = get_datasource_manager()
    datasource_mgr.load_from_db()
    
    # 加载策略
    strategy_mgr = get_strategy_manager()
    strategy_mgr.load_from_db()
    
    # 获取行情回放数据源
    replay_ds = None
    for ds in datasource_mgr.list_all():
        if "回放" in getattr(ds, "name", ""):
            replay_ds = ds
            break
    
    logger.info("\n【行情回放数据源】")
    if replay_ds:
        logger.info(f"  名称：{replay_ds.name}")
        logger.info(f"  ID: {replay_ds.id}")
        logger.info(f"  状态：{'运行中' if replay_ds.is_running else '已停止'}")
    else:
        logger.info("  未找到行情回放数据源")
        return
    
    # 检查 River 策略
    logger.info("\n【River 策略数据源绑定检查】")
    river_strategies = [s for s in strategy_mgr.list_all() if 'river' in s.name.lower()]
    
    bound_to_replay = 0
    bound_to_other = 0
    not_bound = 0
    
    for strategy in river_strategies:
        datasource_id = getattr(strategy._metadata, 'bound_datasource_id', '')
        
        # 获取数据源名称
        datasource_name = "未绑定"
        datasource_status = "N/A"
        if datasource_id:
            ds = datasource_mgr.get(datasource_id)
            if ds:
                datasource_name = ds.name
                datasource_status = '运行中' if ds.is_running else '已停止'
            else:
                datasource_name = f"未找到 (ID: {datasource_id})"
                datasource_status = "N/A"
        
        # 统计
        if not datasource_id:
            not_bound += 1
        elif datasource_id == replay_ds.id:
            bound_to_replay += 1
        else:
            bound_to_other += 1
        
        # 打印策略信息
        logger.info(f"\n  策略：{strategy.name}")
        logger.info(f"    策略 ID: {strategy.id}")
        logger.info(f"    策略状态：{'运行中' if strategy.is_running else '已停止'}")
        logger.info(f"    绑定数据源 ID: {datasource_id}")
        logger.info(f"    绑定数据源名称：{datasource_name}")
        logger.info(f"    数据源状态：{datasource_status}")
        
        # 检查策略是否真的在使用数据源
        if strategy.is_running:
            processed_count = getattr(strategy._state, 'processed_count', 0)
            output_count = getattr(strategy._state, 'output_count', 0)
            logger.info(f"    处理数据条数：{processed_count}")
            logger.info(f"    输出信号条数：{output_count}")
            
            if processed_count > 0:
                logger.info(f"    ✓ 策略正在处理数据")
            else:
                logger.info(f"    ⚠ 策略未处理任何数据")
    
    # 汇总统计
    logger.info("\n" + "=" * 80)
    logger.info("【绑定统计】")
    logger.info(f"  River 策略总数：{len(river_strategies)}")
    logger.info(f"  绑定到行情回放：{bound_to_replay} 个")
    logger.info(f"  绑定到其他数据源：{bound_to_other} 个")
    logger.info(f"  未绑定数据源：{not_bound} 个")
    logger.info("=" * 80)
    
    # 检查信号流
    logger.info("\n【信号流检查】")
    signal_stream = get_signal_stream()
    logger.info(f"  信号流缓存大小：{len(signal_stream.cache)}")
    
    if signal_stream.cache:
        logger.info(f"  最近信号:")
        for key, signal in list(signal_stream.cache.items())[-10:]:
            logger.info(f"    - {key}: {type(signal).__name__}")
    else:
        logger.info("  信号流缓存为空")
    
    logger.info("\n" + "=" * 80)


if __name__ == "__main__":
    main()
