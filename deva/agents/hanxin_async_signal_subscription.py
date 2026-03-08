#!/usr/bin/env python3
"""韩信异步订阅信号流示例

演示韩信智能体如何异步订阅信号流，并根据信号流结果执行交易。

运行方式:
    python deva/examples/agents/hanxin_async_signal_subscription.py
"""

import logging
import time
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent
from deva.naja.agent.manager import create_four_agents
from deva import timer
from deva.naja.signal.stream import get_signal_stream

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """主函数"""
    try:
        logger.info("=" * 80)
        logger.info("=== 韩信异步订阅信号流示例 ===")
        logger.info("=" * 80)
        
        # 1. 创建四个智能体
        logger.info("\n【步骤 1】创建四个智能体...")
        config = {
            'zhangliang': {
                'auto_analyze': True
            },
            'hanxin': {
                'signal_analysis_interval': 5,  # 信号分析间隔（秒）
                'auto_trade_enabled': True      # 启用自动交易
            },
            'xiaohe': {
                'initial_capital': 1000000,     # 初始资金 100 万
                'max_position_ratio': 0.2,      # 单个股票最大仓位 20%
                'max_total_position': 8,        # 最大持仓数量 8
                'risk_control_enabled': True     # 启用风控
            },
            'liubang': {
                'health_check_interval': 30      # 健康检查间隔（秒）
            }
        }
        
        agents = create_four_agents(config)
        hanxin = agents['韩信']
        xiaohe = agents['萧何']
        
        logger.info("✓ 韩信：交易员")
        logger.info("✓ 萧何：风控官")
        
        # 2. 绑定智能体关系
        logger.info("\n【步骤 2】绑定智能体关系...")
        hanxin.set_xiaohe_agent('萧何')
        logger.info("✓ 韩信绑定萧何进行风控")
        
        # 3. 启动所有智能体
        logger.info("\n【步骤 3】启动所有智能体...")
        from deva.naja.agent.manager import get_agent_manager
        manager = get_agent_manager()
        manager.start_all_agents()
        logger.info("✓ 所有智能体已启动")
        
        # 4. 启动 river 策略实验室
        logger.info("\n【步骤 4】启动 river 策略实验室...")
        results = hanxin.start_river_strategies(
            enable_auto_trade=True,        # 启用自动交易
            bind_xiaohe=True,              # 自动绑定萧何智能体
            auto_start_replay_datasource=True  # 自动启动行情回放数据源
        )
        
        # 打印策略启动结果
        logger.info("\n【策略启动结果】")
        if results:
            for strategy_name, success in results.items():
                status = "✓ 成功" if success else "✗ 失败"
                logger.info(f"  - {strategy_name}: {status}")
            logger.info(f"\n✓ 已启动 {len(results)} 个 river 策略")
        else:
            logger.warning("⚠ 未找到 river 类别的策略")
        
        # 5. 监控交易过程
        logger.info("\n【步骤 5】开始监控交易过程...")
        logger.info("按 Ctrl+C 停止监控")
        
        # 定期打印交易状态
        @timer(interval=10, start=True)
        def print_trade_status():
            trades = hanxin.get_trade_history()
            active_strategies = hanxin.get_active_strategies()
            
            logger.info("\n" + "-" * 60)
            logger.info("【交易状态】")
            logger.info(f"  交易次数：{len(trades)}")
            logger.info(f"  活跃策略：{len(active_strategies)}")
            if active_strategies:
                logger.info(f"  策略列表：{', '.join(active_strategies[:3])}{'...' if len(active_strategies) > 3 else ''}")
            
            # 打印最近的交易
            if trades:
                logger.info("\n【最近交易】")
                for trade in trades[-3:]:  # 只显示最近3笔交易
                    logger.info(f"  - {trade.trade_id}: {trade.action} {trade.strategy_name}")
                    logger.info(f"    价格：{trade.price}, 数量：{trade.amount}")
            
            # 打印风控指标
            try:
                risk_metrics = xiaohe.get_risk_metrics()
                logger.info("\n【风控指标】")
                logger.info(f"  总资金：{risk_metrics['total_capital']:.2f}")
                logger.info(f"  可用资金：{risk_metrics['available_capital']:.2f}")
                logger.info(f"  风险等级：{risk_metrics['risk_level']}")
                logger.info(f"  持仓数量：{risk_metrics['position_count']}")
            except Exception as e:
                logger.warning(f"获取风控指标失败：{e}")
            
            # 打印持仓信息
            try:
                positions = xiaohe.get_all_positions()
                if positions:
                    logger.info("\n【持仓信息】")
                    for pos_id, position in positions.items():
                        logger.info(f"  - {pos_id}: {position['strategy_name']}")
                        logger.info(f"    数量：{position['amount']}, 成本价：{position['price']}")
                        logger.info(f"    市值：{position['amount'] * position['price']:.2f}")
            except Exception as e:
                logger.warning(f"获取持仓信息失败：{e}")
        
        # 定期打印信号流信息
        @timer(interval=5, start=True)
        def print_signal_stream():
            signal_stream = get_signal_stream()
            recent_signals = list(signal_stream.cache.values())[-10:]  # 最近10个信号
            
            if recent_signals:
                logger.info("\n" + "-" * 60)
                logger.info("【信号流信息】")
                logger.info(f"  最近信号数量：{len(recent_signals)}")
                
                for i, signal in enumerate(recent_signals[-5:], 1):  # 只显示最近5个信号
                    if hasattr(signal, 'strategy_name') and hasattr(signal, 'output_full'):
                        logger.info(f"\n  信号 {i}：")
                        logger.info(f"    策略：{signal.strategy_name}")
                        logger.info(f"    时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(signal.ts))}")
                        
                        # 打印信号详细信息
                        if signal.output_full:
                            output = signal.output_full
                            logger.info(f"    信号类型：{type(output).__name__}")
                            
                            if isinstance(output, dict):
                                # 打印字典的所有键
                                logger.info(f"    信号键：{list(output.keys())}")
                                
                                # 处理包含picks的信号
                                if 'picks' in output and output['picks']:
                                    logger.info(f"    推荐股票列表：")
                                    for j, pick in enumerate(output['picks'][:3], 1):  # 只显示前3个推荐股票
                                        if isinstance(pick, dict):
                                            stock_name = pick.get('name', '')
                                            stock_code = pick.get('code', '')
                                            price = pick.get('price', 0.0) or pick.get('close', 0.0) or pick.get('current', 0.0)
                                            confidence = pick.get('up_probability', 0.0) or pick.get('confidence', 0.0)
                                            if price <= 0:
                                                logger.info(f"      {j}. {stock_name}({stock_code}) - 价格：{price:.3f} - 置信度：{confidence:.2f} - 策略ID：{signal.strategy_id if hasattr(signal, 'strategy_id') else '未知'}")
                                            else:
                                                logger.info(f"      {j}. {stock_name}({stock_code}) - 价格：{price:.3f} - 置信度：{confidence:.2f}")
                                        else:
                                            logger.info(f"      {j}. {pick}")
                                # 处理包含signals的信号
                                elif 'signals' in output:
                                    logger.info(f"    信号数量：{len(output['signals'])}")
                                    if output['signals']:
                                        logger.info(f"    信号详情：")
                                        for j, sig in enumerate(output['signals'][:3], 1):  # 只显示前3个信号
                                            if isinstance(sig, dict):
                                                stock_name = sig.get('name', '')
                                                stock_code = sig.get('code', '')
                                                price = sig.get('price', 0.0) or sig.get('close', 0.0) or sig.get('current', 0.0)
                                                if stock_name or stock_code:
                                                    if price <= 0:
                                                        logger.info(f"      {j}. {stock_name}({stock_code}) - 价格：{price:.3f} - 策略ID：{signal.strategy_id if hasattr(signal, 'strategy_id') else '未知'}")
                                                    else:
                                                        logger.info(f"      {j}. {stock_name}({stock_code}) - 价格：{price:.3f}")
                                                else:
                                                    logger.info(f"      {j}. {sig}")
                                            else:
                                                logger.info(f"      {j}. {sig}")
                                # 处理其他类型的信号输出
                                elif 'buy' in output or '买入' in str(output):
                                    logger.info(f"    信号类型：买入信号")
                                    if 'price' in output:
                                        logger.info(f"    价格：{output['price']:.3f}")
                                    if 'code' in output:
                                        logger.info(f"    股票代码：{output['code']}")
                                    if 'name' in output:
                                        logger.info(f"    股票名称：{output['name']}")
                                # 处理包含股票信息的其他格式
                                else:
                                    # 尝试查找股票相关字段
                                    if 'code' in output:
                                        logger.info(f"    股票代码：{output['code']}")
                                    if 'name' in output:
                                        logger.info(f"    股票名称：{output['name']}")
                                    if 'price' in output:
                                        logger.info(f"    价格：{output['price']:.3f}")
                                    elif 'close' in output:
                                        logger.info(f"    价格：{output['close']:.3f}")
                            elif isinstance(output, list):
                                logger.info(f"    信号列表长度：{len(output)}")
                                if output:
                                    logger.info(f"    列表前3项：")
                                    for j, item in enumerate(output[:3], 1):
                                        logger.info(f"      {j}. {item}")
                            else:
                                logger.info(f"    信号内容：{output}")
        
        # 保持程序运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n用户中断，正在停止...")
        
        # 6. 停止所有智能体
        logger.info("\n【步骤 6】停止所有智能体...")
        manager.stop_all_agents()
        logger.info("✓ 所有智能体已停止")
        
        # 7. 萧何汇报交易结果
        logger.info("\n" + "=" * 80)
        logger.info("【萧何最终交易总结报告】")
        logger.info("=" * 80)
        
        try:
            # 使用萧何的新方法生成最终报告
            xiaohe.generate_final_report(hanxin)
        except Exception as e:
            logger.error(f"生成最终报告失败：{e}")
            import traceback
            traceback.print_exc()
        
    except Exception as e:
        logger.error(f"运行出错：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
