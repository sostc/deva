#!/usr/bin/env python3
"""韩信 River 策略测试

启动韩信智能体，执行 river 类别的策略，分析信号并执行买入。
"""

import sys
import logging
from deva.naja.agent.hanxin import HanXinAgent
from deva import when
from deva.core.utils.ioloop import get_io_loop

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """主函数"""
    try:
        logger.info("=== 启动韩信 River 策略测试 ===")
        
        # 创建韩信智能体
        hanxin = HanXinAgent({
            'signal_analysis_interval': 5,  # 信号分析间隔（秒）
            'auto_trade_enabled': True  # 启用自动交易
        })
        
        # 启动智能体
        hanxin.start()
        
        # 启动 river 策略
        logger.info("启动 river 类别的策略...")
        
        # 确保策略已从数据库加载
        from deva.naja.strategy import get_strategy_manager
        strategy_mgr = get_strategy_manager()
        strategy_mgr.load_from_db()
        
        results = hanxin.start_river_strategies()
        
        # 打印启动结果
        if results:
            logger.info("策略启动结果:")
            for strategy_name, success in results.items():
                status = "成功" if success else "失败"
                logger.info(f"  - {strategy_name}: {status}")
        else:
            logger.warning("未找到 river 策略")
        
        # 开始自动交易循环
        logger.info("开始自动交易循环...")
        
        # 使用timer代替when
        from deva import timer
        
        @timer(interval=10, start=True)
        def auto_trade():
            """自动交易"""
            try:
                hanxin.auto_trade_loop()
            except Exception as e:
                logger.error(f"自动交易循环错误: {e}")
        
        logger.info("韩信 River 策略测试已启动")
        logger.info("按 Ctrl+C 停止")
        
        # 运行事件循环
        loop = get_io_loop()
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
