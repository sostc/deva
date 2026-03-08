#!/usr/bin/env python3
"""监控策略信号 - 检查策略是否在生成信号"""

import logging
import time
from deva.naja.strategy import get_strategy_manager
from deva.naja.signal.stream import get_signal_stream
from deva.naja.strategy.result_store import StrategyResult

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_strategy_status():
    """检查策略状态"""
    strategy_mgr = get_strategy_manager()
    strategy_mgr.load_from_db()
    
    strategies = strategy_mgr.list_all()
    river_strategies = [s for s in strategies if 'river' in s.name.lower()]
    
    logger.info("=" * 80)
    logger.info("【策略状态检查】")
    logger.info(f"总策略数：{len(strategies)}")
    logger.info(f"River 策略数：{len(river_strategies)}")
    logger.info("")
    
    for strategy in river_strategies:
        logger.info(f"策略：{strategy.name}")
        logger.info(f"  ID: {strategy.id}")
        logger.info(f"  状态：{'运行中' if strategy.is_running else '已停止'}")
        logger.info(f"  数据源：{strategy.datasource_name if hasattr(strategy, 'datasource_name') else 'N/A'}")
        logger.info("")
    
    return river_strategies


def check_signal_stream():
    """检查信号流"""
    try:
        signal_stream = get_signal_stream()
        
        logger.info("=" * 80)
        logger.info("【信号流检查】")
        logger.info(f"信号流缓存大小：{len(signal_stream.cache)}")
        logger.info("")
        
        if signal_stream.cache:
            logger.info("最近的信号:")
            count = 0
            for key, signal in list(signal_stream.cache.items())[-20:]:
                if isinstance(signal, StrategyResult):
                    count += 1
                    logger.info(f"  {count}. 策略={signal.strategy_name}")
                    logger.info(f"     时间={signal.timestamp}")
                    logger.info(f"     成功={signal.success}")
                    logger.info(f"     结果={signal.result}")
                    logger.info(f"     信号={signal.signal}")
                    logger.info("")
            
            if count == 0:
                logger.info("  没有找到 StrategyResult 类型的信号")
        else:
            logger.info("信号流缓存为空")
        
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"检查信号流失败：{e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    logger.info("\n开始监控策略信号...\n")
    
    # 初始检查
    check_strategy_status()
    check_signal_stream()
    
    # 定期检查
    for i in range(10):
        time.sleep(5)
        logger.info(f"\n--- 第 {i+1} 次检查 (5 秒间隔) ---\n")
        check_signal_stream()
    
    logger.info("\n监控结束\n")


if __name__ == "__main__":
    main()
