#!/usr/bin/env python3
"""实时监控策略数据源绑定和执行状态"""

import logging
import time
from deva.naja.strategy import get_strategy_manager
from deva.naja.datasource import get_datasource_manager
from deva.naja.signal.stream import get_signal_stream

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_realtime():
    """实时检查"""
    try:
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
        
        logger.info("=" * 80)
        logger.info("【实时监控】")
        logger.info(f"行情回放数据源：{replay_ds.name if replay_ds else '未找到'} - {'运行中' if replay_ds and replay_ds.is_running else '已停止'}")
        logger.info("")
        
        # 检查 River 策略
        river_strategies = [s for s in strategy_mgr.list_all() if 'river' in s.name.lower()]
        
        running_count = 0
        bound_to_replay = 0
        
        for strategy in river_strategies[:3]:  # 只显示前 3 个
            datasource_id = getattr(strategy._metadata, 'bound_datasource_id', '')
            
            # 获取数据源名称
            datasource_name = "未绑定"
            if datasource_id:
                ds = datasource_mgr.get(datasource_id)
                if ds:
                    datasource_name = ds.name
            
            is_running = strategy.is_running
            if is_running:
                running_count += 1
            
            if datasource_id == (replay_ds.id if replay_ds else None):
                bound_to_replay += 1
            
            logger.info(f"策略：{strategy.name}")
            logger.info(f"  状态：{'✓ 运行中' if is_running else '✗ 已停止'}")
            logger.info(f"  绑定数据源：{datasource_name} ({datasource_id})")
            
            if is_running:
                processed_count = getattr(strategy._state, 'processed_count', 0)
                output_count = getattr(strategy._state, 'output_count', 0)
                logger.info(f"  处理数据：{processed_count} 条")
                logger.info(f"  输出信号：{output_count} 条")
            
            logger.info("")
        
        logger.info(f"统计：{running_count}/{len(river_strategies)} 个策略运行中，{bound_to_replay}/{len(river_strategies)} 个绑定到行情回放")
        logger.info("=" * 80)
        
        # 检查信号流
        signal_stream = get_signal_stream()
        if signal_stream.cache:
            logger.info(f"信号流缓存：{len(signal_stream.cache)} 条信号")
            for key, signal in list(signal_stream.cache.items())[-3:]:
                logger.info(f"  - {key}: {type(signal).__name__}")
        else:
            logger.info("信号流缓存：空")
        
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"检查失败：{e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    logger.info("启动实时监控...（按 Ctrl+C 停止）")
    logger.info("每 5 秒检查一次策略状态\n")
    
    try:
        while True:
            check_realtime()
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("\n监控已停止")


if __name__ == "__main__":
    main()
