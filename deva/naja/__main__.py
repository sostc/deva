"""Naja 命令行入口

使用方法:
    python -m deva.naja                                    # 默认启动（启用新闻雷达）
    python -m deva.naja --port 8080                       # 指定端口
    python -m deva.naja --lab --lab-table quant_snapshot_5min_window   # 实验室模式
    python -m deva.naja --news-radar-speed 10             # 新闻雷达10倍速
    python -m deva.naja --news-radar-sim                  # 新闻雷达模拟模式
    python -m deva.naja --cognition-debug                  # 完整认知调试模式
    python -m deva.naja --tune --lab-table quant_snapshot_5min_window  # 调参模式
    python -m deva.naja --tune --tune-method random --tune-samples 50  # 随机搜索调参
    python -m deva.naja --no-color                        # 禁用彩色日志

后台服务模式:
    python -m deva.naja -s start      # 后台启动服务
    python -m deva.naja -s stop       # 停止服务
    python -m deva.naja -s reload     # 热重启服务
    python -m deva.naja -s restart    # 重启服务
    python -m deva.naja -s status     # 查看服务状态
"""

import argparse
import logging
import os
import sys
import time

# 在导入 deva 之前设置环境变量，这样 deva.__init__.py 会自动使用彩色日志
if '--no-color' not in sys.argv:
    os.environ['NAJA_COLORFUL_LOG'] = 'true'

try:
    from .. import __version__
except ImportError:
    __version__ = "unknown"

from .application import AppRuntimeConfig, run_web_application
from .infra.runtime.daemon import (
    is_running, get_status,
    stop_service, reload_service, restart_service, stop_tray,
    setup_reload_handler, PID_FILE, LOG_FILE, TRAY_PID_FILE
)


def handle_service_command():
    import socket
    import argparse
    import subprocess
    import time
    import signal
    import os
    import sys

    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    def get_pid_using_port(port):
        try:
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True, text=True
            )
            if result.stdout.strip():
                return [int(pid) for pid in result.stdout.strip().split('\n') if pid.strip()]
        except Exception:
            pass
        return []

    def get_process_info(pid):
        """获取进程的详细信息"""
        try:
            result = subprocess.run(
                ['ps', '-p', str(pid), '-o', 'pid,ppid,command'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
        except Exception:
            pass
        return None

    def is_naja_process(pid):
        """判断进程是否是 Naja 相关进程"""
        info = get_process_info(pid)
        if info:
            info_lower = info.lower()
            return any(keyword in info_lower for keyword in ['deva', 'naja', 'python -m'])
        return False

    def confirm_termination(pids):
        """询问用户是否要终止非 Naja 进程"""
        print(f"\n  ⚠️  发现非 Naja 进程占用该端口！")
        for pid in pids:
            info = get_process_info(pid)
            print(f"    - PID: {pid}")
            if info:
                print(f"      命令: {info}")
        
        while True:
            try:
                response = input(f"\n  确定要终止这些进程吗？(y/N): ").strip().lower()
                if response in ['y', 'yes']:
                    return True
                elif response in ['n', 'no', '']:
                    return False
                else:
                    print("  请输入 y 或 n")
            except (KeyboardInterrupt, EOFError):
                print("\n  已取消")
                return False

    def kill_processes(pids):
        killed = []
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                killed.append(pid)
                print(f"  ✓ 发送终止信号给进程 {pid}")
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                    killed.append(pid)
                    print(f"  ✓ 强制终止进程 {pid}")
                except Exception as e:
                    print(f"  ✗ 无法终止进程 {pid}: {e}")
        return killed

    def wait_for_port_free(port, timeout=5):
        start = time.time()
        while time.time() - start < timeout:
            if not is_port_in_use(port):
                return True
            time.sleep(0.2)
        return False

    def is_running_on_port(port):
        try:
            result = subprocess.run(
                ['lsof', '-i', f':{port}'],
                capture_output=True, text=True
            )
            return 'python' in result.stdout.lower() or 'deva' in result.stdout.lower()
        except Exception:
            return False

    parser = argparse.ArgumentParser(description="Naja 服务管理")
    parser.add_argument("action", choices=["start", "stop", "reload", "restart", "status", "log", "debug"])
    parser.add_argument("--port", type=int, default=8080, help="启动端口（仅 start 有效）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="启动地址（仅 start 有效）")
    parser.add_argument("-f", "--force", action="store_true", help="强制终止占用端口的所有进程")
    parser.add_argument("-n", "--lines", type=int, default=50, help="初始显示的日志行数（仅 log/debug 有效）")
    args = parser.parse_args(sys.argv[2:])

    if args.action == "start":
        import platform
        import subprocess
        from pathlib import Path

        if is_running():
            status = get_status()
            print(f"✗ Naja 已在运行 (PID: {status['pid']})")
            return

        if is_port_in_use(args.port):
            print(f"⚠️  端口 {args.port} 已被占用，正在检查...")
            
            # 获取占用端口的进程
            pids = get_pid_using_port(args.port)
            
            if pids:
                # 分离 Naja 进程和其他进程
                naja_pids = []
                other_pids = []
                
                for pid in pids:
                    if is_naja_process(pid):
                        naja_pids.append(pid)
                    else:
                        other_pids.append(pid)
                
                print(f"\n  发现 {len(pids)} 个进程占用该端口:")
                for pid in pids:
                    is_naja = is_naja_process(pid)
                    mark = "[Naja]" if is_naja else "[其他]"
                    info = get_process_info(pid)
                    if info:
                        print(f"    {mark} PID: {pid}")
                        print(f"           {info}")
                    else:
                        print(f"    {mark} PID: {pid}")
                
                pids_to_kill = []
                
                # 自动处理 Naja 进程
                if naja_pids:
                    pids_to_kill.extend(naja_pids)
                    print(f"\n  ✓ 发现 {len(naja_pids)} 个 Naja 相关进程，将自动清理")
                
                # 处理其他进程
                if other_pids:
                    if args.force:
                        print(f"\n  --force 模式：强制终止所有进程")
                        pids_to_kill.extend(other_pids)
                    else:
                        if not confirm_termination(other_pids):
                            print(f"\n✗ 已取消启动，请先解决端口占用问题")
                            return
                        pids_to_kill.extend(other_pids)
                
                # 执行终止操作
                if pids_to_kill:
                    print(f"\n  正在终止进程...")
                    killed = kill_processes(pids_to_kill)
                    
                    if killed:
                        # 等待端口释放
                        print(f"\n  等待端口释放...")
                        if wait_for_port_free(args.port):
                            print(f"✓ 端口 {args.port} 已释放")
                        else:
                            print(f"✗ 端口 {args.port} 未能及时释放，请手动检查")
                            return
                    else:
                        print(f"✗ 无法清理占用端口的进程，请手动处理")
                        return
            else:
                print(f"✗ 无法识别占用端口的进程，请手动检查")
                return

        if platform.system() == "Darwin":
            env = os.environ.copy()
            env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
        else:
            env = None

        naja_dir = str(Path.home() / ".naja")
        os.makedirs(os.path.join(naja_dir, "logs"), exist_ok=True)
        tray_log_file = os.path.join(naja_dir, "logs", "tray.log")

        cmd = [
            sys.executable, "-m", "deva.naja",
            f"--port={args.port}", f"--host={args.host}"
        ]

        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=os.getcwd(),
            start_new_session=True
        )

        tray_proc = None
        if platform.system() == "Darwin":
            try:
                import rumps
                # 先停止旧托盘
                stop_tray()
                
                tray_script = os.path.join(str(Path(__file__).parent), "scripts", "start_tray.py")
                tray_cmd = [sys.executable, tray_script]
                tray_proc = subprocess.Popen(
                    tray_cmd,
                    env=env,
                    stdout=open(tray_log_file, "a"),
                    stderr=subprocess.STDOUT,
                    cwd=os.getcwd(),
                    start_new_session=True
                )
                print("✓ 托盘已启动")
            except ImportError:
                print("⚠ 未安装 rumps，菜单栏托盘将不启动")
                print("  安装命令: pip install rumps")

        time.sleep(0.5)
        if proc.poll() is None:
            with open(PID_FILE, "w") as f:
                f.write(str(proc.pid))
            print(f"✓ Naja 已后台启动 (PID: {proc.pid})")
            print(f"  日志: {LOG_FILE}")
            if tray_proc and tray_proc.poll() is None:
                print(f"  托盘 (PID: {tray_proc.pid})")
        else:
            print("✗ 启动失败，请查看日志")

    elif args.action == "stop":
        stop_service()

    elif args.action == "reload":
        reload_service()

    elif args.action == "restart":
        original_argv = sys.argv
        sys.argv = [sys.argv[0], "-s", "stop"]
        stop_service()
        time.sleep(1)
        sys.argv = [sys.argv[0], "-s", "start", "--port", str(args.port), "--host", args.host]
        handle_service_command()
        sys.argv = original_argv

    elif args.action == "status":
        status = get_status()
        if status["running"]:
            print(f"✓ Naja 正在运行 (PID: {status['pid']})")
            print(f"  PID文件: {status['pid_file']}")
            print(f"  日志文件: {status['log_file']}")
        else:
            print("✗ Naja 未在运行")
            print(f"  PID文件: {status['pid_file']}")
            print(f"  日志文件: {status['log_file']}")
    elif args.action == "log":
        from .infra.runtime.daemon import follow_log
        if not is_running():
            print("✗ Naja 未在运行，无法查看日志")
            status = get_status()
            print(f"  日志文件: {status['log_file']}")
            return
        follow_log(LOG_FILE, level_filter=None, lines=args.lines)
    elif args.action == "debug":
        from .infra.runtime.daemon import follow_log
        if not is_running():
            print("✗ Naja 未在运行，无法查看调试日志")
            status = get_status()
            print(f"  日志文件: {status['log_file']}")
            return
        follow_log(LOG_FILE, level_filter="DEBUG", lines=args.lines)


def main():
    import argparse
    import logging

    parser = argparse.ArgumentParser(description="Naja - 实时数据流与策略系统")

    parser.add_argument("-s", "--service", type=str, default=None, choices=["start", "stop", "reload", "restart", "status", "log", "debug"],
                        help="服务管理模式: start(后台启动) | stop(停止) | reload(热重启) | restart(重启) | status(状态) | log(查看日志) | debug(查看调试日志)")

    if len(sys.argv) > 1 and sys.argv[1] in ("-s", "--service"):
        handle_service_command()
        return

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
                        help="启用实验室模式（回放历史数据测试）")
    parser.add_argument("--lab-table", type=str, default=None,
                        help="实验室模式回放数据表名 (如: quant_snapshot_5min_window)")
    parser.add_argument("--lab-interval", type=float, default=1.0,
                        help="实验室模式回放间隔（秒），默认 1.0")
    parser.add_argument("--lab-speed", type=float, default=1.0,
                        help="实验室模式回放速度倍数，默认 1.0")
    parser.add_argument("--lab-debug", action="store_true",
                        help="实验室模式调试日志，输出详细处理信息")

    # 强制实盘调试模式参数
    parser.add_argument("--force-realtime", action="store_true",
                        help="强制实盘调试模式（忽略交易时间限制，用于非交易时间调试）")

    # 调试市场模式参数（仅用于开发调试，生产环境不应使用）
    parser.add_argument("--debug-market", type=str, default=None,
                        choices=["a_share", "us", "closed"],
                        help="调试模式：强制指定市场状态 (a_share=A股交易中, us=美股交易中, closed=休市)")

    # 新闻雷达模式参数（统一命名）
    # --news-radar: 默认启用新闻雷达（使用真实数据源）
    # --news-radar-speed: 新闻雷达加速倍数（可与 --news-radar-sim 互斥）
    # --news-radar-sim: 使用模拟数据源（与真实数据源互斥）
    parser.add_argument("--news-radar", action="store_true", default=True,
                        help="启用新闻雷达（默认启用，使用真实数据源）")
    parser.add_argument("--news-radar-speed", type=float, default=1.0,
                        help="新闻雷达加速倍数，默认 1.0（真实数据源模式）")
    parser.add_argument("--news-radar-sim", action="store_true",
                        help="启用新闻雷达模拟模式（使用模拟数据源）")
    parser.add_argument("--cognition-debug", action="store_true",
                        help="启用认知系统调试日志，输出认知核心产出信息（自动启用新闻雷达+实验室模式）")

    # 调参模式参数
    parser.add_argument("--tune", action="store_true",
                        help="启用调参模式，用历史数据搜索最优参数")
    parser.add_argument("--tune-method", type=str, default="grid", choices=["grid", "random"],
                        help="调参搜索方法: grid(网格搜索) 或 random(随机搜索)，默认 grid")
    parser.add_argument("--tune-samples", type=int, default=100,
                        help="随机搜索模式下的最大采样数，默认 100")
    parser.add_argument("--tune-export", type=str, default=None,
                        help="导出调参结果到指定文件路径")
    parser.add_argument("--no-color", action="store_true",
                        help="禁用彩色日志输出")

    args = parser.parse_args()

    use_color = not args.no_color

    if args.tune:
        from .infra.observability.tuning_logger import setup_tuning_mode_logger, print_tuning_banner
        setup_tuning_mode_logger(level=logging.INFO)
        print_tuning_banner()
    else:
        from .infra.log.colorful_logger import setup_colorful_logger, StartupVisualizer
        from pathlib import Path
        naja_log_dir = Path.home() / ".naja" / "logs"
        naja_log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = str(naja_log_dir / "naja.log")
        setup_colorful_logger(
            level=getattr(logging, args.log_level.upper()),
            force_color=use_color,
            log_file=log_file_path,
            max_bytes=100 * 1024 * 1024,  # 100MB per file
            backup_count=10,
        )

        sv = StartupVisualizer(width=65)
        sv.banner('Naja 管理平台启动中...', '🚀')

    # 如果请求了注意力系统报告
    if args.attention_report:
        show_attention_report()
        return

    # 设置环境变量以控制注意力系统
    if args.attention_enabled is not None:
        os.environ["NAJA_ATTENTION_ENABLED"] = "true" if args.attention_enabled else "false"

    # 处理实验室模式参数
    lab_config = None
    if args.lab or args.tune:
        os.environ['NAJA_LAB_MODE'] = '1'
        lab_config = {
            "enabled": True,
            "table_name": args.lab_table,
            "interval": args.lab_interval,
            "speed": args.lab_speed,
            "debug": args.lab_debug,
        }
        if not args.lab_table:
            print("警告: --lab 已启用但未指定 --lab-table，将仅启动注意力系统而不回放数据")

    # 处理强制实盘调试模式参数
    if args.force_realtime:
        os.environ['NAJA_FORCE_REALTIME'] = '1'
        print("⚠️ 强制实盘调试模式已启用 (--force-realtime)")

    # 处理调试市场模式参数
    if args.debug_market:
        from .market_hotspot.data.global_market_futures import set_debug_market_mode
        set_debug_market_mode(args.debug_market)
        print(f"⚠️ 调试市场模式已启用 (--debug-market={args.debug_market})")

    # 调参模式配置
    tune_config = None
    if args.tune:
        tune_config = {
            "enabled": True,
            "search_method": args.tune_method,
            "max_samples": args.tune_samples,
            "export_path": args.tune_export,
        }
        print(f"🎯 调参模式已启用 (方法: {args.tune_method}, 最大采样: {args.tune_samples})")

    # 新闻雷达模式配置（默认启用，除非明确禁用）
    # --news-radar-sim: 使用模拟数据源
    # --news-radar-speed: 新闻雷达加速倍数（真实数据源模式）

    news_radar_config = None
    news_radar_enabled = args.news_radar

    with sv.section('⚙️ 参数配置'):
        sv.item(f"Web Server", '→', f"http://{args.host}:{args.port}")
        if args.lab:
            sv.item("实验室模式", '✓', f"table={args.lab_table}")
        if args.tune:
            sv.item("调参模式", '✓', f"method={args.tune_method}")
        if args.news_radar_sim:
            sv.item("新闻雷达", '✓', "模拟模式")
            news_radar_config = {
                "enabled": True,
                "mode": "sim",
                "interval": args.news_radar_speed if args.news_radar_speed > 1.0 else 0.5,
                "speed": args.news_radar_speed,
            }
        elif args.news_radar_speed != 1.0:
            sv.item("新闻雷达", '✓', f"加速 {args.news_radar_speed}x")
            news_radar_config = {
                "enabled": True,
                "mode": "speed",
                "speed": args.news_radar_speed,
            }
        elif news_radar_enabled:
            sv.item("新闻雷达", '✓', "真实数据源")
            news_radar_config = {
                "enabled": True,
                "mode": "normal",
            }
        else:
            sv.item("新闻雷达", '✗', "已禁用")

    # 认知系统调试配置
    cognition_debug_config = None
    if args.cognition_debug:
        cognition_debug_config = {"enabled": True}
        os.environ["NAJA_COGNITION_DEBUG"] = "true"
        os.environ["NAJA_LAB_DEBUG"] = "true"
        os.environ["NAJA_NEWS_RADAR_DEBUG"] = "true"
        if not lab_config:
            lab_config = {
                "enabled": True,
                "table_name": args.lab_table or "quant_snapshot_5min_window",
                "interval": args.lab_interval or 0.5,
                "speed": args.lab_speed or 1.0,
                "debug": True,
            }
        if not news_radar_config:
            sv.item("认知调试", '✓', "自动启用实验室+雷达模拟")
            news_radar_config = {
                "enabled": True,
                "mode": "sim",
                "interval": 0.3,
                "speed": 2.0,
            }
        sv.success("🧠 认知系统调试模式已启用")

    config = AppRuntimeConfig.from_legacy(
        host=args.host,
        port=args.port,
        lab_config=lab_config,
        news_radar_config=news_radar_config,
        cognition_debug_config=cognition_debug_config,
        tune_config=tune_config,
    )
    run_web_application(config)


def show_attention_report():
    """显示注意力系统状态报告"""
    try:
        from .market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration
        
        integration = get_market_hotspot_integration()
        report = integration.get_hotspot_report()
        
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
