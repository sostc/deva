#!/usr/bin/env python3
"""
Naja Lab Monitor - 监控并自动重启 naja lab 程序

功能：
1. 实时监控程序输出
2. 检测文件修改后自动重启
3. 集成信号调参器，显示调参状态

使用方式：
python scripts/naja_lab_monitor.py
"""

import subprocess
import signal
import sys
import time
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Set, List, Tuple

NAJA_DIR = Path(__file__).parent.parent.parent
WATCH_PATTERNS = [
    "deva/naja/**/*.py",
]
COMMAND = [
    sys.executable, "-m", "deva.naja",
    "--lab", "--lab-table", "quant_snapshot_5min_window",
    "--lab-interval", "1.0",
    "--tuning-mode",
]


class NajaLabMonitor:
    def __init__(self, watch_dir: Optional[str] = None):
        self.watch_dir = Path(watch_dir) if watch_dir else NAJA_DIR
        self.process: Optional[subprocess.Popen] = None
        self.last_restart_time = time.time()
        self.restart_count = 0
        self.running = True
        self.last_modified_files: dict = {}

        self.signal_count = 0
        self.last_signal_time = 0
        self.last_tuner_check = time.time()

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        print("\n收到退出信号，正在停止...")
        self.running = False
        self.stop()
        sys.exit(0)

    def _get_py_files(self) -> List[Path]:
        """获取所有 Python 文件及其修改时间"""
        files = []
        for pattern in WATCH_PATTERNS:
            files.extend(self.watch_dir.glob(pattern))
        return [f for f in files if f.suffix == '.py']

    def _check_file_changes(self) -> bool:
        """检查是否有文件被修改"""
        current_mtimes = {}
        changed = False

        for f in self._get_py_files():
            try:
                mtime = f.stat().st_mtime
                current_mtimes[str(f)] = mtime

                if str(f) in self.last_modified_files:
                    if mtime > self.last_modified_files[str(f)] + 0.5:
                        changed = True
                        print(f"  📝 检测到文件修改: {f.relative_to(self.watch_dir)}")
            except Exception:
                pass

        self.last_modified_files = current_mtimes
        return changed

    def _parse_output_line(self, line: str):
        """解析输出行，提取关键信息"""
        line = line.strip()
        if not line:
            return

        if 'Signal' in line or 'signal' in line:
            if 'BUY' in line.upper() or 'buy' in line.lower():
                self.signal_count += 1
                self.last_signal_time = time.time()

        if '调整' in line and ('param' in line.lower() or 'threshold' in line.lower()):
            print(f"  ⚙️  参数调整: {line[:100]}")

        if '[SignalTuner]' in line:
            print(f"  🎛️  {line}")

        if '[AttentionTracker]' in line:
            print(f"  👁️  {line}")

        if '[Cognition]' in line and 'Insight' in line:
            print(f"  🧠  {line}")

    def _print_status(self):
        """打印当前状态"""
        elapsed = time.time() - self.last_restart_time
        uptime_str = datetime.fromtimestamp(self.last_restart_time).strftime('%H:%M:%S')

        print("\n" + "=" * 60)
        print(f"  🟢 Naja Lab Monitor 运行中")
        print(f"  ⏱️  启动时间: {uptime_str} (已运行 {elapsed:.0f}秒)")
        print(f"  🔄 重启次数: {self.restart_count}")
        print(f"  📊 信号计数: {self.signal_count}")

        if self.last_signal_time > 0:
            signal_gap = time.time() - self.last_signal_time
            print(f"  ⏰ 距上次信号: {signal_gap:.0f}秒")

        print("=" * 60)

    def start(self):
        """启动监控"""
        print("=" * 60)
        print("  🚀 Naja Lab Monitor 启动")
        print(f"  📁 监控目录: {self.watch_dir}")
        print(f"  🔍 文件数: {len(self._get_py_files())}")
        print("=" * 60)

        self._check_file_changes()

        while self.running:
            self._launch_process()
            self._monitor_loop()

    def _launch_process(self):
        """启动子进程"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 启动 naja lab...")

        self.process = subprocess.Popen(
            COMMAND,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(self.watch_dir),
            text=True,
            bufsize=1
        )

        self.last_restart_time = time.time()
        print(f"  PID: {self.process.pid}")

    def _monitor_loop(self):
        """监控循环"""
        check_interval = 2.0
        status_interval = 30.0
        last_status = time.time()

        try:
            while self.running and self.process.poll() is None:
                line = self.process.stdout.readline()
                if line:
                    self._parse_output_line(line)
                    print(line.rstrip())

                if time.time() - last_status >= status_interval:
                    self._print_status()
                    last_status = time.time()

                if self._check_file_changes():
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 检测到文件修改，准备重启...")
                    self.restart_count += 1
                    self._restart()
                    break

                time.sleep(0.1)

        except Exception as e:
            print(f"监控循环错误: {e}")

    def _restart(self):
        """重启进程"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass

        time.sleep(1)

    def stop(self):
        """停止监控"""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass


def main():
    monitor = NajaLabMonitor()
    monitor.start()


if __name__ == "__main__":
    main()
