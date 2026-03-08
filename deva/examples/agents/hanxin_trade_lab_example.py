#!/usr/bin/env python3
"""韩信交易闭环测试

演示韩信智能体启动策略实验室时自动绑定萧何并启用自动交易的完整流程。

运行方式:
    python deva/examples/agents/hanxin_trade_lab_example.py
"""

import sys
import logging
from deva.naja.agent.hanxin import HanXinAgent
from deva import timer
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
        logger.info("=" * 60)
        logger.info("=== 韩信交易闭环实验室测试 ===")
        logger.info("=" * 60)
        
        # 创建韩信智能体
        logger.info("\n1. 创建韩信智能体...")
        hanxin = HanXinAgent({
            'signal_analysis_interval': 5,  # 信号分析间隔（秒）
            'auto_trade_enabled': True      # 启用自动交易
        })
        
        # 启动智能体
        logger.info("2. 启动韩信智能体...")
        hanxin.start()
        
        # 启动 river 策略（自动绑定萧何 + 启用自动交易）
        logger.info("\n3. 启动 river 策略实验室（自动绑定萧何 + 启用自动交易）...")
        
        # 确保策略已从数据库加载
        from deva.naja.strategy import get_strategy_manager
        strategy_mgr = get_strategy_manager()
        strategy_mgr.load_from_db()
        
        # 启动 river 策略，默认参数：enable_auto_trade=True, bind_xiaohe=True
        results = hanxin.start_river_strategies(
            enable_auto_trade=True,  # 启用自动交易
            bind_xiaohe=True        # 自动绑定萧何智能体
        )
        
        # 打印启动结果
        logger.info("\n4. 策略启动结果:")
        if results:
            for strategy_name, success in results.items():
                status = "✓ 成功" if success else "✗ 失败"
                logger.info(f"  {status} - {strategy_name}")
        else:
            logger.warning("  未找到 river 策略")
        
        # 查看交易状态
        logger.info("\n5. 交易闭环状态:")
        logger.info(f"  - 自动交易模式：{'✓ 已启用' if hanxin._auto_trade_enabled else '✗ 未启用'}")
        logger.info(f"  - 萧何智能体绑定：{'✓ 已绑定' if hanxin._xiaohe_agent else '✗ 未绑定'}")
        logger.info(f"  - 活跃策略数量：{len(hanxin.get_active_strategies())}")
        logger.info(f"  - 活跃策略列表：{hanxin.get_active_strategies()}")
        
        # 开始自动交易循环
        logger.info("\n6. 开始自动交易循环...")
        
        @timer(interval=10, start=True)
        def auto_trade():
            """自动交易"""
            try:
                hanxin.auto_trade_loop()
            except Exception as e:
                logger.error(f"  自动交易循环错误：{e}")
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ 韩信交易闭环实验室已启动")
        logger.info("✓ 自动交易：开启")
        logger.info("✓ 萧何绑定：开启")
        logger.info("✓ 信号分析间隔：5 秒")
        logger.info("✓ 自动交易间隔：10 秒")
        logger.info("=" * 60)
        logger.info("\n按 Ctrl+C 停止测试\n")
        
        # 运行事件循环
        loop = get_io_loop()
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n" + "=" * 60)
            logger.info("用户中断，正在停止...")
            logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"测试失败：{e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
