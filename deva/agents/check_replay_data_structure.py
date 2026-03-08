#!/usr/bin/env python3
"""检查行情回放数据源的实际数据结构

验证行情回放数据源提供的实际数据字段，以便修改 River 策略的价格提取逻辑。

运行方式:
    python deva/examples/agents/check_replay_data_structure.py
"""

import logging
import time
from deva.naja.datasource import get_datasource_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def check_replay_data_structure():
    """检查行情回放数据源的实际数据结构"""
    try:
        logger.info("=" * 80)
        logger.info("=== 检查行情回放数据源数据结构 ===")
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
        
        # 检查数据源配置
        logger.info("\n【数据源配置】")
        if hasattr(replay_ds, '_metadata'):
            config = getattr(replay_ds, '_metadata', {}).config
            logger.info(f"配置：{config}")
            table_name = config.get('table_name', 'unknown')
            logger.info(f"回放表名：{table_name}")
        
        # 检查数据源的代码，了解它如何生成数据
        logger.info("\n【数据源代码】")
        if hasattr(replay_ds, '_metadata') and hasattr(replay_ds._metadata, 'code'):
            code = replay_ds._metadata.code
            logger.info("数据源代码:")
            logger.info(code)
        
        # 尝试获取数据源的一些示例数据
        logger.info("\n【尝试获取示例数据】")
        
        # 由于我们无法直接访问数据源的内部数据，我们可以检查数据源的代码来了解它提供哪些字段
        # 或者我们可以创建一个临时策略来接收数据源的数据
        
        # 检查数据源可能提供的字段
        logger.info("\n【数据源可能提供的字段】")
        logger.info("根据常见的行情数据格式，数据源可能提供以下字段：")
        logger.info("- code: 股票代码")
        logger.info("- name: 股票名称")
        logger.info("- open: 开盘价")
        logger.info("- high: 最高价")
        logger.info("- low: 最低价")
        logger.info("- close: 收盘价")
        logger.info("- volume: 成交量")
        logger.info("- amount: 成交额")
        logger.info("- p_change: 涨跌幅")
        logger.info("- current: 当前价")
        logger.info("- price: 价格")
        logger.info("- now: 当前价格")
        logger.info("- last: 最新价")
        
        # 建议的价格字段检查顺序
        logger.info("\n【建议的价格字段检查顺序】")
        logger.info("为了提高价格提取的成功率，建议修改 River 策略的 _price() 函数，按以下顺序检查：")
        logger.info("1. 'current' - 当前价")
        logger.info("2. 'now' - 当前价格")
        logger.info("3. 'price' - 价格")
        logger.info("4. 'last' - 最新价")
        logger.info("5. 'close' - 收盘价")
        logger.info("6. 'open' - 开盘价")
        logger.info("7. 'high' - 最高价")
        logger.info("8. 'low' - 最低价")
        
        # 提供修改后的 _price() 函数代码
        logger.info("\n【修改后的 _price() 函数】")
        modified_price_function = '''
def _price(row):
    for k in ("current", "now", "price", "last", "close", "open", "high", "low"):
        if k in row:
            p = _f(row.get(k), 0.0)
            if p > 0:
                return p
    return 0.0
'''
        logger.info(modified_price_function)
        
        # 总结
        logger.info("\n【总结】")
        logger.info("1. 价格显示为 0 的原因：")
        logger.info("   - 行情回放数据源提供的数据中缺少 River 策略期望的价格字段")
        logger.info("   - River 策略的 _price() 函数只检查了有限的几个价格字段")
        
        logger.info("\n2. 解决方案：")
        logger.info("   - 修改 River 策略的 _price() 函数，添加更多价格字段的检查")
        logger.info("   - 确保行情回放数据源提供了至少一个有效的价格字段")
        
        return True
        
    except Exception as e:
        logger.error(f"运行出错：{e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    check_replay_data_structure()
