#!/usr/bin/env python3
"""韩信实验交易 - 启动完整的交易实验环境

功能:
1. 启动韩信智能体（交易员）
2. 启动萧何智能体（风控官）
3. 自动绑定萧何进行风控
4. 启动 river 策略实验室
5. 自动启动行情回放数据源
6. 开始自动交易循环
"""

import logging
from deva import timer
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent
from deva.naja.strategy import get_strategy_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数 - 启动实验交易环境"""
    try:
        logger.info("=" * 80)
        logger.info("=== 韩信实验交易环境 ===")
        logger.info("=" * 80)
        
        # 1. 启动萧何智能体（风控官）
        logger.info("\n【步骤 1】启动萧何智能体（风控官）...")
        xiaohe = XiaoHeAgent({
            'initial_capital': 1000000,  # 初始资金 100 万
            'max_position_ratio': 0.2,   # 单个股票最大仓位 20%
            'max_total_position': 8,     # 最大持仓数量 8
            'risk_control_enabled': True, # 启用风控
        })
        xiaohe.start()
        logger.info("✓ 萧何智能体已启动")
        
        # 2. 创建并启动韩信智能体（交易员）
        logger.info("\n【步骤 2】创建韩信智能体（交易员）...")
        hanxin = HanXinAgent({
            'signal_analysis_interval': 5,  # 信号分析间隔（秒）
            'auto_trade_enabled': True,     # 启用自动交易
        })
        hanxin.start()
        logger.info("✓ 韩信智能体已启动")
        
        # 3. 手动绑定萧何智能体
        logger.info("\n【步骤 3】绑定萧何智能体进行风控...")
        hanxin.set_xiaohe_agent('萧何')
        logger.info("✓ 萧何智能体绑定成功")
        
        # 4. 确保策略已从数据库加载
        logger.info("\n【步骤 4】加载策略列表...")
        strategy_mgr = get_strategy_manager()
        strategy_mgr.load_from_db()
        
        river_strategies = [s for s in strategy_mgr.list_all() if 'river' in s.name.lower()]
        logger.info(f"✓ 找到 {len(river_strategies)} 个 river 策略")
        for s in river_strategies:
            logger.info(f"  - {s.name}")
        
        # 5. 启动 river 策略实验室（自动绑定萧何 + 启用自动交易 + 启动行情回放）
        logger.info("\n【步骤 5】启动 river 策略实验室...")
        results = hanxin.start_river_strategies(
            enable_auto_trade=True,      # 启用自动交易
            bind_xiaohe=True,            # 自动绑定萧何智能体
            auto_start_replay_datasource=True  # 自动启动行情回放数据源
        )
        
        # 6. 打印启动结果
        logger.info("\n【步骤 6】策略启动结果:")
        success_count = 0
        fail_count = 0
        if results:
            for strategy_name, success in results.items():
                status = "✓ 成功" if success else "✗ 失败"
                logger.info(f"  {status} - {strategy_name}")
                if success:
                    success_count += 1
                else:
                    fail_count += 1
        else:
            logger.warning("  未找到 river 策略")
        
        # 7. 查看交易闭环状态
        logger.info("\n【步骤 7】交易闭环状态:")
        logger.info(f"  - 自动交易模式：{'✓ 已启用' if hanxin._auto_trade_enabled else '✗ 未启用'}")
        logger.info(f"  - 萧何智能体绑定：{'✓ 已绑定' if hanxin._xiaohe_agent else '✗ 未绑定'}")
        logger.info(f"  - 活跃策略数量：{len(hanxin.get_active_strategies())}")
        logger.info(f"  - 成功启动策略：{success_count} 个")
        logger.info(f"  - 启动失败策略：{fail_count} 个")
        
        # 8. 开始自动交易循环
        logger.info("\n【步骤 8】开始自动交易循环...")
        
        @timer(interval=10, start=True)
        def auto_trade():
            """自动交易循环"""
            try:
                hanxin.auto_trade_loop()
            except Exception as e:
                logger.error(f"  自动交易循环错误：{e}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✓ 韩信实验交易环境已启动")
        logger.info("✓ 自动交易：开启")
        logger.info("✓ 萧何风控：开启")
        logger.info("✓ 行情回放：已启动")
        logger.info("✓ 信号分析间隔：5 秒")
        logger.info("✓ 自动交易间隔：10 秒")
        logger.info("=" * 80)
        logger.info("\n按 Ctrl+C 停止交易实验\n")
        
        # 运行事件循环
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n" + "=" * 80)
            logger.info("用户中断，正在停止交易实验...")
            logger.info("=" * 80)
            
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"实验交易启动失败：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
