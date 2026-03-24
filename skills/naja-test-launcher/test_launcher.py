#!/usr/bin/env python3
"""
Naja 测试启动器

便捷启动各种测试模式：
1. 实验室模式（数据回放）
2. 雷达调试模式
3. 认知系统调试模式

使用方法:
    python test_launcher.py lab --table quant_snapshot_5min_window --interval 1.0
    python test_launcher.py radar --interval 0.5
    python test_launcher.py cognition
"""

import argparse
import os
import sys
import subprocess
import signal
import time


def kill_process_on_port(port):
    """停止占用指定端口的进程"""
    try:
        result = subprocess.run(
            f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true",
            shell=True,
            capture_output=True
        )
    except Exception:
        pass


def start_lab_mode(table, interval, speed, debug, port):
    """启动实验室模式"""
    cmd = [
        sys.executable, "-m", "deva.naja",
        "--lab",
        "--lab-table", table,
        "--lab-interval", str(interval),
        "--lab-speed", str(speed),
        "--port", str(port)
    ]
    if debug:
        cmd.append("--lab-debug")

    print(f"启动实验室模式...")
    print(f"  数据表: {table}")
    print(f"  间隔: {interval}s")
    print(f"  速度: {speed}x")
    print(f"  端口: {port}")
    print(f"  命令: {' '.join(cmd)}")

    subprocess.Popen(cmd, cwd=os.getcwd())


def start_radar_mode(interval, port):
    """启动雷达调试模式"""
    cmd = [
        sys.executable, "-m", "deva.naja",
        "--radar-debug",
        "--radar-interval", str(interval),
        "--port", str(port)
    ]

    print(f"启动雷达调试模式...")
    print(f"  间隔: {interval}s")
    print(f"  端口: {port}")

    subprocess.Popen(cmd, cwd=os.getcwd())


def start_cognition_mode(port):
    """启动认知系统调试模式"""
    cmd = [
        sys.executable, "-m", "deva.naja",
        "--cognition-debug",
        "--port", str(port)
    ]

    print(f"启动认知系统调试模式...")
    print(f"  端口: {port}")

    subprocess.Popen(cmd, cwd=os.getcwd())


def start_live_mode(force_trading, port):
    """启动实盘模式"""
    if force_trading:
        os.environ['NAJA_FORCE_TRADING'] = 'true'
        print("强制交易模式已启用（忽略真实时间）")

    cmd = [
        sys.executable, "-m", "deva.naja",
        "--attention",
        "--port", str(port)
    ]

    print(f"启动实盘模式...")
    print(f"  端口: {port}")

    subprocess.Popen(cmd, cwd=os.getcwd())


def stop_all():
    """停止所有 Naja 进程"""
    print("停止所有 Naja 进程...")
    subprocess.run("pkill -f 'python -m deva.naja' || true", shell=True)
    print("已停止")


def status():
    """查看运行状态"""
    result = subprocess.run(
        "ps aux | grep 'deva.naja' | grep -v grep",
        shell=True,
        capture_output=True,
        text=True
    )
    if result.stdout:
        print("运行中的 Naja 进程:")
        print(result.stdout)
    else:
        print("没有运行中的 Naja 进程")


def main():
    parser = argparse.ArgumentParser(description="Naja 测试启动器")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # lab 子命令
    lab_parser = subparsers.add_parser("lab", help="实验室模式（数据回放）")
    lab_parser.add_argument("--table", default="quant_snapshot_5min_window", help="数据表名")
    lab_parser.add_argument("--interval", type=float, default=1.0, help="回放间隔（秒）")
    lab_parser.add_argument("--speed", type=float, default=1.0, help="回放速度倍数")
    lab_parser.add_argument("--debug", action="store_true", help="启用调试日志")
    lab_parser.add_argument("--port", type=int, default=8080, help="端口")

    # radar 子命令
    radar_parser = subparsers.add_parser("radar", help="雷达调试模式")
    radar_parser.add_argument("--interval", type=float, default=0.5, help="雷达间隔（秒）")
    radar_parser.add_argument("--port", type=int, default=8080, help="端口")

    # cognition 子命令
    cog_parser = subparsers.add_parser("cognition", help="认知系统调试模式")
    cog_parser.add_argument("--port", type=int, default=8080, help="端口")

    # live 子命令
    live_parser = subparsers.add_parser("live", help="实盘模式")
    live_parser.add_argument("--force", action="store_true", help="强制交易模式（忽略时间）")
    live_parser.add_argument("--port", type=int, default=8080, help="端口")

    # stop 子命令
    subparsers.add_parser("stop", help="停止所有 Naja 进程")

    # status 子命令
    subparsers.add_parser("status", help="查看运行状态")

    args = parser.parse_args()

    if args.command == "lab":
        start_lab_mode(args.table, args.interval, args.speed, args.debug, args.port)
    elif args.command == "radar":
        start_radar_mode(args.interval, args.port)
    elif args.command == "cognition":
        start_cognition_mode(args.port)
    elif args.command == "live":
        start_live_mode(args.force, args.port)
    elif args.command == "stop":
        stop_all()
    elif args.command == "status":
        status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
