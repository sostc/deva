#!/usr/bin/env python3
"""检查行情回放数据源的代码

验证行情回放数据源的代码，了解它如何从 quant_snapshot_5min_window 表中读取数据并生成信号。

运行方式:
    python deva/examples/agents/check_replay_datasource_code.py
"""

import logging
from deva.naja.datasource import get_datasource_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def check_replay_datasource_code():
    """检查行情回放数据源的代码"""
    try:
        logger.info("=" * 80)
        logger.info("=== 检查行情回放数据源代码 ===")
        logger.info("=" * 80)
        
        # 获取数据源管理器
        ds_mgr = get_datasource_manager()
        
        # 加载数据源
        ds_mgr.load_from_db()
        
        # 查找行情回放数据源
        replay_ds = None
        for ds in ds_mgr.list_all():
            ds_name = getattr(ds, "name", "")
            if "回放" in ds_name or "replay" in ds_name.lower():
                replay_ds = ds
                break
        
        if not replay_ds:
            logger.error("未找到行情回放数据源")
            return False
        
        logger.info(f"找到行情回放数据源：{replay_ds.name} (ID: {replay_ds.id})")
        
        # 检查数据源的代码
        logger.info("\n【数据源代码】")
        if hasattr(replay_ds, '_metadata') and hasattr(replay_ds._metadata, 'code'):
            code = replay_ds._metadata.code
            logger.info("数据源代码:")
            logger.info(code)
        else:
            logger.warning("未找到数据源的代码")
        
        # 检查数据源的配置
        logger.info("\n【数据源配置】")
        if hasattr(replay_ds, '_metadata'):
            config = getattr(replay_ds, '_metadata', {}).config
            logger.info(f"配置：{config}")
            table_name = config.get('table_name', 'unknown')
            logger.info(f"回放表名：{table_name}")
        
        # 分析数据源代码的逻辑
        logger.info("\n【代码分析】")
        logger.info("行情回放数据源的工作原理：")
        logger.info("1. 从指定的表中读取数据")
        logger.info("2. 按时间间隔回放数据")
        logger.info("3. 将数据发送给绑定的策略")
        
        logger.info("\n【可能的问题】")
        logger.info("1. 数据格式问题：quant_snapshot_5min_window 表使用键值对存储，value 是 BLOB 类型")
        logger.info("2. 数据解析问题：数据源可能没有正确解析 BLOB 数据，导致策略无法提取价格")
        logger.info("3. 字段映射问题：数据源可能没有将 BLOB 中的价格字段映射到策略期望的字段名")
        
        logger.info("\n【解决方案】")
        logger.info("1. 检查数据源代码，确保它正确解析 BLOB 数据")
        logger.info("2. 确保数据源将价格字段映射到策略期望的字段名（如 'price', 'current', 'close' 等）")
        logger.info("3. 如果数据源代码有问题，修改它以正确处理数据格式")
        
        return True
        
    except Exception as e:
        logger.error(f"运行出错：{e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    check_replay_datasource_code()
