#!/usr/bin/env python3
"""韩信实验交易 - 增强版（带详细日志和资金汇报）

功能:
1. 启动韩信智能体（交易员）
2. 启动萧何智能体（风控官）
3. 自动绑定萧何进行风控
4. 启动 river 策略实验室
5. 自动启动行情回放数据源
6. 开始自动交易循环
7. 定期汇报资金和持仓情况
"""

import logging
from deva import timer
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent
from deva.naja.strategy import get_strategy_manager
from deva.naja.agent.manager import get_agent_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_capital_report(xiaohe: XiaoHeAgent):
    """打印资金报告"""
    try:
        capital = xiaohe.get_capital_info()
        risk_metrics = xiaohe.get_risk_metrics()
        
        logger.info("\n" + "=" * 80)
        logger.info("【资金报告】")
        logger.info(f"  总资金：¥{capital['total_capital']:,.2f}")
        logger.info(f"  已用资金：¥{capital['used_capital']:,.2f} ({capital['usage_ratio']*100:.1f}%)")
        logger.info(f"  可用资金：¥{capital['available_capital']:,.2f}")
        logger.info("\n【风险指标】")
        logger.info(f"  风险等级：{risk_metrics['risk_level']}")
        logger.info(f"  总风险暴露：¥{risk_metrics['total_exposure']:,.2f}")
        logger.info(f"  持仓集中度：{risk_metrics['position_concentration']*100:.1f}%")
        logger.info(f"  最大回撤：{risk_metrics['max_drawdown']*100:.2f}%")
        logger.info(f"  夏普比率：{risk_metrics['sharpe_ratio']:.2f}")
        logger.info("=" * 80 + "\n")
    except Exception as e:
        logger.error(f"获取资金报告失败：{e}")


def print_position_report(xiaohe: XiaoHeAgent):
    """打印持仓报告"""
    try:
        positions = xiaohe.get_all_positions()
        
        if not positions:
            logger.info("【持仓报告】暂无持仓\n")
            return
        
        logger.info("\n" + "=" * 80)
        logger.info("【持仓报告】")
        logger.info(f"  持仓数量：{len(positions)} 个")
        logger.info("-" * 80)
        
        total_value = 0
        for pos in positions:
            value = pos.amount * pos.current_price
            total_value += value
            profit_loss = (pos.current_price - pos.avg_price) * pos.amount
            profit_loss_pct = ((pos.current_price / pos.avg_price) - 1) * 100 if pos.avg_price > 0 else 0
            
            logger.info(f"  {pos.position_id}")
            logger.info(f"    策略：{pos.strategy_name}")
            logger.info(f"    数量：{pos.amount:.0f} 股")
            logger.info(f"    成本价：¥{pos.avg_price:.2f}")
            logger.info(f"    当前价：¥{pos.current_price:.2f}")
            logger.info(f"    市值：¥{value:,.2f}")
            logger.info(f"    盈亏：¥{profit_loss:,.2f} ({profit_loss_pct:+.2f}%)")
            logger.info("")
        
        logger.info(f"  持仓总市值：¥{total_value:,.2f}")
        logger.info("=" * 80 + "\n")
    except Exception as e:
        logger.error(f"获取持仓报告失败：{e}")


def print_trade_history(hanxin: HanXinAgent):
    """打印交易历史"""
    try:
        trades = hanxin.get_trade_history()
        
        if not trades:
            logger.info("【交易历史】暂无交易\n")
            return
        
        logger.info("\n" + "=" * 80)
        logger.info("【交易历史】")
        logger.info(f"  交易次数：{len(trades)} 次")
        logger.info("-" * 80)
        
        for trade in trades[-10:]:  # 只显示最近 10 笔
            logger.info(f"  {trade.trade_id}")
            logger.info(f"    策略：{trade.strategy_name}")
            logger.info(f"    操作：{'买入' if trade.action == 'buy' else '卖出'}")
            logger.info(f"    价格：¥{trade.price:.2f}")
            logger.info(f"    数量：{trade.amount:.0f} 股")
            logger.info(f"    时间：{trade.timestamp}")
            logger.info("")
        
        logger.info("=" * 80 + "\n")
    except Exception as e:
        logger.error(f"获取交易历史失败：{e}")


def main():
    """主函数 - 启动实验交易环境"""
    try:
        logger.info("=" * 80)
        logger.info("=== 韩信实验交易环境（增强版） ===")
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
        
        def auto_trade():
            """自动交易循环"""
            try:
                hanxin.auto_trade_loop()
            except Exception as e:
                logger.error(f"  自动交易循环错误：{e}")
        
        # 启动自动交易定时器（每 10 秒）
        timer(interval=10, start=True)(auto_trade)
        
        # 9. 定期汇报资金和持仓（每 30 秒）
        def report():
            """定期汇报"""
            try:
                print_capital_report(xiaohe)
                print_position_report(xiaohe)
                print_trade_history(hanxin)
            except Exception as e:
                logger.error(f"  汇报错误：{e}")
        
        # 启动汇报定时器（每 30 秒）
        timer(interval=30, start=True)(report)
        
        # 初始汇报
        logger.info("\n【步骤 9】初始状态汇报...")
        report()
        
        logger.info("\n" + "=" * 80)
        logger.info("✓ 韩信实验交易环境已启动")
        logger.info("✓ 自动交易：开启")
        logger.info("✓ 萧何风控：开启")
        logger.info("✓ 行情回放：已启动")
        logger.info("✓ 信号分析间隔：5 秒")
        logger.info("✓ 自动交易间隔：10 秒")
        logger.info("✓ 资金汇报间隔：30 秒")
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
            
            # 最终汇报
            logger.info("\n【最终汇报】")
            print_capital_report(xiaohe)
            print_position_report(xiaohe)
            print_trade_history(hanxin)
            
            logger.info("交易实验已停止")
            logger.info("=" * 80)
            
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"实验交易启动失败：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
