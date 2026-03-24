"""Naja 命令行入口

使用方法:
    python -m deva.naja
    python -m deva.naja --port 8080
    python -m deva.naja --lab --lab-table quant_snapshot_5min_window
    python -m deva.naja --radar-debug --lab --lab-table quant_snapshot_5min_window
"""

import argparse
import logging
import os

try:
    from .. import __version__
except ImportError:
    __version__ = "unknown"


def main():
    parser = argparse.ArgumentParser(description="Naja - 实时数据流与策略系统")
    parser.add_argument("--port", type=int, default=8080, help="Web 服务器端口")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="绑定地址")
    parser.add_argument("--log-level", "-l", default="INFO", help="日志级别")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")

    # 注意力系统相关参数
    parser.add_argument("--attention", dest="attention_enabled", action="store_true",
                        default=None, help="启用注意力调度系统")
    parser.add_argument("--no-attention", dest="attention_enabled", action="store_false",
                        help="禁用注意力调度系统")
    parser.add_argument("--attention-report", action="store_true",
                        help="显示注意力系统状态报告")

    # 实验室模式参数
    parser.add_argument("--lab", action="store_true",
                        help="启用实验室模式，自动启动注意力系统测试")
    parser.add_argument("--lab-table", type=str, default=None,
                        help="实验室模式回放数据表名 (如: quant_snapshot_5min_window)")
    parser.add_argument("--lab-interval", type=float, default=1.0,
                        help="实验室模式回放间隔（秒），默认 1.0")
    parser.add_argument("--lab-speed", type=float, default=1.0,
                        help="实验室模式回放速度倍数，默认 1.0")
    parser.add_argument("--lab-debug", action="store_true",
                        help="实验室模式调试日志，输出详细处理信息")

    # 雷达调试模式参数
    parser.add_argument("--radar-debug", action="store_true",
                        help="启用雷达调试模式，输出雷达核心产出日志")
    parser.add_argument("--radar-interval", type=float, default=0.5,
                        help="雷达模拟数据源间隔（秒），默认 0.5")
    parser.add_argument("--news-speed", type=float, default=1.0,
                        help="新闻模拟速度倍数，默认 1.0")
    parser.add_argument("--news-radar", action="store_true",
                        help="启动新闻舆情策略，启用新闻数据处理和雷达检测")
    parser.add_argument("--cognition-debug", action="store_true",
                        help="启用认知系统调试日志，输出认知核心产出信息")

    args = parser.parse_args()

    # 设置日志级别
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 如果请求了注意力系统报告
    if args.attention_report:
        show_attention_report()
        return

    # 设置环境变量以控制注意力系统
    if args.attention_enabled is not None:
        os.environ["NAJA_ATTENTION_ENABLED"] = "true" if args.attention_enabled else "false"

    # 处理实验室模式参数
    lab_config = None
    if args.lab:
        lab_config = {
            "enabled": True,
            "table_name": args.lab_table,
            "interval": args.lab_interval,
            "speed": args.lab_speed,
            "debug": args.lab_debug,
        }
        if not args.lab_table:
            print("警告: --lab 已启用但未指定 --lab-table，将仅启动注意力系统而不回放数据")

    # 雷达调试模式参数
    radar_debug_config = None
    if args.radar_debug:
        radar_debug_config = {
            "enabled": True,
            "interval": args.radar_interval,
            "news_speed": args.news_speed,
        }
        os.environ["NAJA_RADAR_DEBUG"] = "true"
        print(f"🛸 雷达调试模式已启用，模拟间隔: {args.radar_interval}s")

    # 新闻舆情策略配置
    news_radar_config = None
    if args.news_radar or args.cognition_debug:
        news_radar_config = {
            "enabled": True,
            "datasource_id": radar_debug_config.get("datasource_id") if radar_debug_config else None,
        }
        print("📰 新闻舆情策略已启用")

    # 认知系统调试配置
    cognition_debug_config = None
    if args.cognition_debug:
        cognition_debug_config = {"enabled": True}
        os.environ["NAJA_COGNITION_DEBUG"] = "true"
        os.environ["NAJA_RADAR_DEBUG"] = "true"
        os.environ["NAJA_LAB_DEBUG"] = "true"
        if not lab_config:
            lab_config = {
                "enabled": True,
                "table_name": args.lab_table or "quant_snapshot_5min_window",
                "interval": args.lab_interval or 0.5,
                "speed": args.lab_speed or 1.0,
                "debug": True,
            }
        if not radar_debug_config:
            radar_debug_config = {
                "enabled": True,
                "interval": args.radar_interval or 0.3,
                "news_speed": args.news_speed or 2.0,
            }
        print("🧠 认知系统调试模式已启用（自动启用实验室+雷达+新闻舆情）")

    # 启动 Web UI
    from .web_ui import run_server
    run_server(port=args.port, host=args.host, lab_config=lab_config, radar_debug_config=radar_debug_config, news_radar_config=news_radar_config, cognition_debug_config=cognition_debug_config)


def show_attention_report():
    """显示注意力系统状态报告"""
    try:
        from .attention.integration import get_attention_integration
        
        integration = get_attention_integration()
        report = integration.get_attention_report()
        
        print("\n" + "=" * 60)
        print("Naja Attention Scheduling System 状态报告")
        print("=" * 60)
        
        print(f"\n系统状态: {report.get('status', 'unknown')}")
        print(f"处理快照数: {report.get('processed_snapshots', 0)}")
        print(f"平均延迟: {report.get('avg_latency_ms', 0):.2f} ms")
        print(f"全局注意力: {report.get('global_attention', 0):.3f}")
        
        freq_summary = report.get('frequency_summary', {})
        print(f"\n频率分布:")
        print(f"  高频: {freq_summary.get('high_frequency', 0)} 只")
        print(f"  中频: {freq_summary.get('medium_frequency', 0)} 只")
        print(f"  低频: {freq_summary.get('low_frequency', 0)} 只")
        
        strategy_summary = report.get('strategy_summary', {})
        print(f"\n策略状态:")
        print(f"  活跃策略: {strategy_summary.get('active_count', 0)} 个")
        
        dual_summary = report.get('dual_engine_summary', {})
        if dual_summary:
            print(f"\n双引擎状态:")
            print(f"  触发次数: {dual_summary.get('trigger_count', 0)}")
            river_stats = dual_summary.get('river_stats', {})
            print(f"  River处理: {river_stats.get('processed_count', 0)}")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"获取报告失败: {e}")
        print("注意: 注意力系统可能尚未启动")


if __name__ == "__main__":
    main()
