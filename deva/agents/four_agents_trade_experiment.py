#!/usr/bin/env python3
"""完整启动 - 使用四个智能体完整启动交易实验"""

import logging
from deva import timer
from deva.naja.agent import create_four_agents
from deva.naja.agent.manager import get_agent_manager
from deva.naja.strategy import get_strategy_manager
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_capital_report(xiaohe):
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
        logger.info(f"  持仓数量：{risk_metrics['position_count']}")
        logger.info("=" * 80 + "\n")
    except Exception as e:
        logger.error(f"获取资金报告失败：{e}")


def print_position_report(xiaohe):
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


def print_trade_history(hanxin):
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
            logger.info(f"    原因：{trade.reason}")
            logger.info("")
        
        logger.info("=" * 80 + "\n")
    except Exception as e:
        logger.error(f"获取交易历史失败：{e}")


def check_signals(hanxin):
    """检查信号"""
    try:
        buy_signals = hanxin.analyze_signal_stream()
        if buy_signals:
            logger.info(f"\n【信号检测】发现 {len(buy_signals)} 个买入信号:")
            for signal in buy_signals[:3]:  # 只显示前 3 个
                stock_code = signal.signal_data.get('code', '')
                stock_name = signal.signal_data.get('name', '')
                logger.info(f"  - {stock_name}({stock_code}): 置信度={signal.confidence:.2f}, 策略={signal.strategy_name}")
    except Exception as e:
        logger.error(f"检查信号失败：{e}")


def check_strategy_bindings(hanxin):
    """检查策略数据源绑定状态"""
    try:
        from deva.naja.strategy import get_strategy_manager
        from deva.naja.datasource import get_datasource_manager
        
        strategy_mgr = get_strategy_manager()
        datasource_mgr = get_datasource_manager()
        
        # 注意：不要调用 load_from_db()，否则会覆盖运行时状态
        # datasource_mgr.load_from_db()  # 删除这行
        
        # 获取行情回放数据源
        replay_ds = None
        for ds in datasource_mgr.list_all():
            if "回放" in getattr(ds, "name", ""):
                replay_ds = ds
                break
        
        logger.info("\n" + "=" * 80)
        logger.info("【策略数据源绑定检查】")
        logger.info(f"行情回放数据源：{replay_ds.name if replay_ds else '未找到'} (ID: {replay_ds.id if replay_ds else 'N/A'}, 状态：{'运行中' if replay_ds and replay_ds.is_running else '已停止'})")
        logger.info("")
        
        # 检查 River 策略
        river_strategies = [s for s in strategy_mgr.list_all() if 'river' in s.name.lower()]
        
        bound_to_replay = 0
        total_processed = 0
        total_output = 0
        displayed_count = 0
        
        # 遍历所有策略进行统计
        for strategy in river_strategies:
            datasource_id = getattr(strategy._metadata, 'bound_datasource_id', '')
            
            # 统计绑定情况
            if datasource_id == (replay_ds.id if replay_ds else None):
                bound_to_replay += 1
            
            # 获取处理统计
            processed_count = getattr(strategy._state, 'processed_count', 0)
            output_count = getattr(strategy._state, 'output_count', 0)
            total_processed += processed_count
            total_output += output_count
            
            # 只显示前 5 个
            if displayed_count < 5:
                # 获取数据源名称
                datasource_name = "未绑定"
                datasource_status = "N/A"
                if datasource_id:
                    ds = datasource_mgr.get(datasource_id)
                    if ds:
                        datasource_name = ds.name
                        datasource_status = '运行中' if ds.is_running else '已停止'
                    else:
                        datasource_name = f"未找到 (ID: {datasource_id})"
                
                logger.info(f"策略：{strategy.name}")
                logger.info(f"  状态：{'✓ 运行中' if strategy.is_running else '✗ 已停止'}")
                logger.info(f"  绑定数据源：{datasource_name} (ID: {datasource_id}, 状态：{datasource_status})")
                logger.info(f"  处理数据：{processed_count} 条 | 输出信号：{output_count} 条")
                logger.info("")
                
                displayed_count += 1
        
        if len(river_strategies) > 5:
            logger.info(f"  ... 还有 {len(river_strategies) - 5} 个策略未显示\n")
        
        logger.info(f"统计：{bound_to_replay}/{len(river_strategies)} 个策略绑定到行情回放")
        logger.info(f"      总处理数据：{total_processed} 条 | 总输出信号：{total_output} 条")
        logger.info("=" * 80 + "\n")
        
    except Exception as e:
        logger.error(f"检查策略绑定失败：{e}")


def main():
    """主函数"""
    try:
        logger.info("=" * 80)
        logger.info("=== 四个智能体完整交易实验 ===")
        logger.info("=" * 80)
        
        # 1. 创建四个智能体
        logger.info("\n【步骤 1】创建四个智能体...")
        config = {
            'zhangliang': {
                'auto_analyze': True
            },
            'hanxin': {
                'signal_analysis_interval': 5,
                'auto_trade_enabled': True
            },
            'xiaohe': {
                'initial_capital': 1000000,
                'max_position_ratio': 0.2,
                'max_total_position': 8,
                'risk_control_enabled': True
            },
            'liubang': {
                'health_check_interval': 30
            }
        }
        
        agents = create_four_agents(config)
        zhangliang = agents['张良']
        hanxin = agents['韩信']
        xiaohe = agents['萧何']
        liubang = agents['刘邦']
        
        logger.info("✓ 张良：策略创建师")
        logger.info("✓ 韩信：交易员")
        logger.info("✓ 萧何：风控官")
        logger.info("✓ 刘邦：管理员")
        
        # 2. 绑定智能体关系
        logger.info("\n【步骤 2】绑定智能体关系...")
        hanxin.set_xiaohe_agent('萧何')
        logger.info("✓ 韩信绑定萧何进行风控")
        
        # 3. 启动所有智能体
        logger.info("\n【步骤 3】启动所有智能体...")
        manager = get_agent_manager()
        manager.start_all_agents()
        logger.info("✓ 所有智能体已启动")
        
        # 4. 加载策略
        logger.info("\n【步骤 4】加载策略列表...")
        strategy_mgr = get_strategy_manager()
        strategy_mgr.load_from_db()
        
        river_strategies = [s for s in strategy_mgr.list_all() if 'river' in s.name.lower()]
        logger.info(f"✓ 找到 {len(river_strategies)} 个 river 策略")
        
        # 5. 启动 river 策略
        logger.info("\n【步骤 5】启动 river 策略实验室...")
        logger.info("  → 开始绑定行情回放数据源并启动策略...")
        results = hanxin.start_river_strategies(
            enable_auto_trade=True,
            bind_xiaohe=True,
            auto_start_replay_datasource=True
        )
        logger.info("  → 策略启动完成，检查绑定结果...")
        
        logger.info("\n【步骤 6】策略启动结果:")
        success_count = 0
        if results:
            for strategy_name, success in results.items():
                status = "✓ 成功" if success else "✗ 失败"
                logger.info(f"  {status} - {strategy_name}")
                if success:
                    success_count += 1
        
        # 6. 初始状态汇报
        logger.info("\n【步骤 7】初始状态汇报...")
        print_capital_report(xiaohe)
        print_position_report(xiaohe)
        print_trade_history(hanxin)
        
        # 7. 启动定时器
        logger.info("\n【步骤 8】启动定时任务...")
        
        # 每 10 秒检查信号和交易
        def check_and_trade():
            """检查和交易"""
            try:
                check_signals(hanxin)
                check_strategy_bindings(hanxin)  # 添加策略绑定检查
            except Exception as e:
                logger.error(f"检查信号失败：{e}")
        
        timer(interval=10, start=True)(check_and_trade)
        
        # 每 30 秒汇报一次
        def report():
            """定期汇报"""
            try:
                print_capital_report(xiaohe)
                print_position_report(xiaohe)
                print_trade_history(hanxin)
            except Exception as e:
                logger.error(f"汇报失败：{e}")
        
        timer(interval=30, start=True)(report)
        
        # 初始检查
        check_and_trade()
        
        logger.info("\n" + "=" * 80)
        logger.info("✓ 四个智能体完整交易实验已启动")
        logger.info("✓ 自动交易：开启")
        logger.info("✓ 萧何风控：开启")
        logger.info("✓ 行情回放：已启动")
        logger.info("✓ 信号检测间隔：10 秒")
        logger.info("✓ 资金汇报间隔：30 秒")
        logger.info("=" * 80)
        logger.info("\n按 Ctrl+C 停止交易实验\n")
        
        # 运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n" + "=" * 80)
            logger.info("用户中断，正在停止...")
            logger.info("=" * 80)
            
            # 最终汇报
            logger.info("\n【最终汇报】")
            print_capital_report(xiaohe)
            print_position_report(xiaohe)
            print_trade_history(hanxin)
            
    except Exception as e:
        logger.error(f"实验启动失败：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
