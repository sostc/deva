#!/usr/bin/env python3
"""检查数据源和策略运行状态"""

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
    logger.info("【检查数据源和策略运行状态】")
    logger.info("=" * 80)
    
    # 加载数据源
    datasource_mgr = get_datasource_manager()
    datasource_mgr.load_from_db()
    
    # 加载策略
    strategy_mgr = get_strategy_manager()
    strategy_mgr.load_from_db()
    
    # 检查行情回放数据源
    logger.info("\n【行情回放数据源】")
    replay_ds = None
    for ds in datasource_mgr.list_all():
        if "回放" in getattr(ds, "name", ""):
            replay_ds = ds
            break
    
    if replay_ds:
        logger.info(f"  名称：{replay_ds.name}")
        logger.info(f"  ID: {replay_ds.id}")
        logger.info(f"  状态：{'运行中' if replay_ds.is_running else '已停止'}")
    else:
        logger.info("  未找到行情回放数据源")
    
    # 检查 River 策略
    logger.info("\n【River 策略状态】")
    river_strategies = [s for s in strategy_mgr.list_all() if 'river' in s.name.lower()]
    
    for strategy in river_strategies[:3]:  # 只显示前 3 个
        datasource_id = getattr(strategy._metadata, 'bound_datasource_id', '')
        datasource_name = "未绑定"
        if datasource_id:
            ds = datasource_mgr.get(datasource_id)
            if ds:
                datasource_name = ds.name
        
        logger.info(f"  - {strategy.name}")
        logger.info(f"    状态：{'运行中' if strategy.is_running else '已停止'}")
        logger.info(f"    绑定数据源：{datasource_name} (ID: {datasource_id})")
        logger.info(f"    处理计数：{strategy._state.processed_count if hasattr(strategy, '_state') else 'N/A'}")
        logger.info(f"    输出计数：{strategy._state.output_count if hasattr(strategy, '_state') else 'N/A'}")
        logger.info("")
    
    # 检查信号流
    logger.info("【信号流】")
    signal_stream = get_signal_stream()
    logger.info(f"  缓存大小：{len(signal_stream.cache)}")
    
    if signal_stream.cache:
        logger.info(f"  最近信号:")
        for key, signal in list(signal_stream.cache.items())[-5:]:
            logger.info(f"    - {key}: {signal}")
    else:
        logger.info("  缓存为空")
    
    logger.info("\n" + "=" * 80)


if __name__ == "__main__":
    main()
