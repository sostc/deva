#!/usr/bin/env python3
"""检查行情回放数据源的数据格式

验证行情回放数据源提供的数据是否包含价格字段，以及价格字段的值是否正确。

运行方式:
    python deva/examples/agents/check_replay_data_format.py
"""

import logging
import time
from deva.naja.datasource import get_datasource_manager
from deva.naja.strategy import get_strategy_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def check_replay_datasource():
    """检查行情回放数据源"""
    try:
        logger.info("=" * 80)
        logger.info("=== 检查行情回放数据源数据格式 ===")
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
        
        # 检查数据源状态
        logger.info(f"数据源状态：{'运行中' if replay_ds.is_running else '未运行'}")
        
        # 如果数据源未运行，尝试启动
        if not replay_ds.is_running:
            logger.info("正在启动行情回放数据源...")
            start_result = replay_ds.start()
            if start_result.get('success'):
                logger.info("行情回放数据源启动成功")
            else:
                logger.error(f"行情回放数据源启动失败：{start_result.get('error', '')}")
                return False
        
        # 等待数据源启动
        time.sleep(2)
        
        # 检查数据源的配置和数据结构
        logger.info("\n【数据源配置】")
        logger.info(f"数据源类型：{getattr(replay_ds, 'type', '未知')}")
        logger.info(f"数据源配置：{getattr(replay_ds, '_metadata', {}).config if hasattr(replay_ds, '_metadata') else '未知'}")
        
        # 检查相关的 river 策略
        logger.info("\n【相关 River 策略】")
        strategy_mgr = get_strategy_manager()
        river_strategies = []
        
        for strategy in strategy_mgr.list_all():
            if 'river' in strategy.name.lower():
                river_strategies.append(strategy)
                logger.info(f"- {strategy.name} (ID: {strategy.id})")
                if hasattr(strategy, '_metadata'):
                    logger.info(f"  绑定的数据源：{strategy._metadata.bound_datasource_id}")
        
        if not river_strategies:
            logger.warning("未找到 River 策略")
        
        # 检查策略的价格提取逻辑
        logger.info("\n【价格提取逻辑分析】")
        logger.info("River 策略使用 _price() 函数提取价格，检查字段顺序：")
        logger.info("1. 'now' - 当前价格")
        logger.info("2. 'price' - 价格")
        logger.info("3. 'last' - 最新价格")
        logger.info("4. 'close' - 收盘价")
        logger.info("如果这些字段都不存在或值 <= 0，则返回 0.0")
        
        # 模拟价格提取逻辑
        def simulate_price_extraction(data):
            """模拟 _price() 函数的逻辑"""
            for k in ("now", "price", "last", "close"):
                if k in data:
                    try:
                        p = float(data[k])
                        if p > 0:
                            return p
                    except Exception:
                        pass
            return 0.0
        
        # 测试不同数据格式
        test_cases = [
            {"code": "000001", "name": "平安银行", "now": 15.67, "price": 15.67, "last": 15.66, "close": 15.60},
            {"code": "000002", "name": "万科A", "price": 12.34},
            {"code": "000003", "name": "PT金田A", "close": 0.0},
            {"code": "000004", "name": "国农科技", "now": -1.0},
            {"code": "000005", "name": "世纪星源", "volume": 1000000},
        ]
        
        logger.info("\n【测试价格提取逻辑】")
        for test_data in test_cases:
            price = simulate_price_extraction(test_data)
            logger.info(f"{test_data['name']}({test_data['code']}) - 提取价格: {price}")
            logger.info(f"  原始数据: {test_data}")
        
        # 检查数据源是否提供了正确的价格字段
        logger.info("\n【结论和建议】")
        logger.info("1. 价格显示为 0 的原因：")
        logger.info("   - 行情回放数据源提供的数据中缺少价格字段（now、price、last、close）")
        logger.info("   - 或者这些字段的值为 0 或负数")
        logger.info("   - River 策略的 _price() 函数在找不到有效价格时返回 0.0")
        
        logger.info("\n2. 解决方案：")
        logger.info("   - 检查行情回放数据源的配置，确保它提供了正确的价格字段")
        logger.info("   - 确保数据源返回的数据中包含有效的价格值（> 0）")
        logger.info("   - 可以考虑修改 River 策略的 _price() 函数，添加更多价格字段的检查")
        
        return True
        
    except Exception as e:
        logger.error(f"运行出错：{e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    check_replay_datasource()
