#!/usr/bin/env python3
"""检查策略绑定的数据源"""

import logging
from deva.naja.strategy import get_strategy_manager
from deva.naja.datasource import get_datasource_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("【检查策略绑定的数据源】")
    logger.info("=" * 80)
    
    # 加载策略
    strategy_mgr = get_strategy_manager()
    strategy_mgr.load_from_db()
    
    # 加载数据源
    datasource_mgr = get_datasource_manager()
    datasource_mgr.load_from_db()
    
    # 获取所有策略
    strategies = strategy_mgr.list_all()
    river_strategies = [s for s in strategies if 'river' in s.name.lower()]
    
    logger.info(f"\n总策略数：{len(strategies)}")
    logger.info(f"River 策略数：{len(river_strategies)}")
    
    # 获取所有数据源
    datasources = datasource_mgr.list_all()
    logger.info(f"数据源数：{len(datasources)}")
    logger.info("")
    
    # 打印数据源列表
    logger.info("【数据源列表】")
    for ds in datasources:
        status = "运行中" if ds.is_running else "已停止"
        logger.info(f"  - {ds.name} (ID: {ds.id}) - {status}")
    logger.info("")
    
    # 打印策略绑定的数据源
    logger.info("【River 策略绑定的数据源】")
    for strategy in river_strategies:
        datasource_id = getattr(strategy._metadata, 'bound_datasource_id', '')
        datasource_name = "未绑定"
        
        if datasource_id:
            # 查找数据源名称
            for ds in datasources:
                if ds.id == datasource_id:
                    datasource_name = ds.name
                    break
            else:
                datasource_name = f"未找到 (ID: {datasource_id})"
        
        status = "运行中" if strategy.is_running else "已停止"
        logger.info(f"  - {strategy.name}")
        logger.info(f"    策略 ID: {strategy.id}")
        logger.info(f"    状态：{status}")
        logger.info(f"    绑定数据源 ID: {datasource_id}")
        logger.info(f"    绑定数据源名称：{datasource_name}")
        logger.info("")
    
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
