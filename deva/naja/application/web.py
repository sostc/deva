from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import threading

from deva import NW, Deva

from .container import AppContainer
from .runtime_config import AppRuntimeConfig
from deva.naja.infra.runtime.daemon import (
    PID_FILE, PORT_FILE, NAJA_DIR, save_pid, clear_pid, setup_reload_handler,
)


class _CleanEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """消灭 Python 3.13 下的"假 running"event loop 状态。

    当 loop.is_running() 返回 True 但 asyncio.get_running_loop() 抛
    RuntimeError 时，立即丢弃该 loop 并创建全新的干净 loop，从而
    保证 Tornado/NW 拿到的 loop 一定可以正常 start()。
    """

    def get_event_loop(self):
        try:
            loop = super().get_event_loop()
        except (RuntimeError, AssertionError):
            loop = self.new_event_loop()
            self.set_event_loop(loop)
            return loop
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if loop.is_running():
                loop = self.new_event_loop()
                self.set_event_loop(loop)
        return loop


def _ensure_clean_event_loop() -> None:
    """在任何 Tornado / NW 操作前调用：安装干净 policy + 重建 IOLoop。"""
    asyncio.set_event_loop_policy(_CleanEventLoopPolicy())
    import tornado.platform.asyncio
    # 先拿到一个干净 loop（经 policy 过滤）
    clean_loop = asyncio.get_event_loop_policy().get_event_loop()
    asyncio.set_event_loop(clean_loop)
    # 确保 Tornado IOLoop 绑定在干净 loop 上；install() 会覆盖掉之前的 IOLoop
    tornado.platform.asyncio.AsyncIOMainLoop().install()


def run_web_application(config: AppRuntimeConfig):
    # 第一步：强制清洗 event loop（在 import/boot 之前，否则 container.boot()
    # 里可能有后台组件提前污染 loop 状态）
    _ensure_clean_event_loop()

    # 确保只有一个 Naja 进程在运行
    if not save_pid():
        print("❌ Naja 进程已经在运行，无法启动新实例")
        sys.exit(1)

    container = AppContainer(config)
    container.boot()

    report = container.startup_report()
    load_counts = report["load_counts"]
    load_errors = report["load_errors"]
    restore_results = report["restore_results"]
    restore_errors = report["restore_errors"]

    if load_counts:
        print(
            f"📂 加载完成: 数据源({load_counts.get('datasource', 0)}) "
            f"任务({load_counts.get('task', 0)}) 策略({load_counts.get('strategy', 0)}) "
            f"字典({load_counts.get('dictionary', 0)})"
        )
    if load_errors:
        error_info = ", ".join([f"{k}: {v}" for k, v in load_errors.items()])
        print(f"⚠️ 部分数据加载失败: {error_info}")
    if restore_results:
        print("🔄 运行状态恢复完成")
    if restore_errors:
        error_info = ", ".join([f"{k}: {v}" for k, v in restore_errors.items()])
        print(f"⚠️ 部分状态恢复失败: {error_info}")

    try:
        print(container.attention_config_summary())
    except Exception as e:
        print(f"⚠️ 注意力配置读取失败: {e}")

    container.initialize_runtime_modes()

    handlers = container.create_handlers()
    host = config.server.host
    port = config.server.port

    print(f"🌐 启动 Web 服务器: http://localhost:{port}")
    print("=" * 60)

    try:
        from deva.naja.infra.ui.menu_bar_tray import MenuBarTray
        if MenuBarTray.is_available():
            print("📋 正在启动菜单栏托盘...")
    except Exception as e:
        logging.warning(f"检查菜单栏托盘失败: {e}")

    server = NW("naja_webview", host=host, port=port, start=False)
    server.application.add_handlers(".*$", handlers)

    try:
        PORT_FILE.write_text(str(port))
    except Exception:
        pass

    # 注册全局退出 / 热重启信号 handler（进程级，不依赖 loop 状态）
    logger = logging.getLogger("deva.naja")

    def shutdown_handler(signum, frame):
        logger.info("收到退出信号，正在优雅关闭...")
        try:
            from deva.naja.supervisor import get_naja_supervisor
            supervisor = get_naja_supervisor()
            supervisor.shutdown()
            logger.info("所有组件已停止，数据已持久化")
        except Exception as e:
            logger.error(f"关闭时保存状态失败: {e}")
        clear_pid()
        # 让 Tornado IOLoop 从 Deva.run() 中干净退出
        try:
            from tornado.ioloop import IOLoop
            IOLoop.current().stop()
        except Exception:
            pass

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    def reload_handler():
        import subprocess
        import time
        logger.info("=== 热重启开始 ===")
        try:
            from deva.naja.supervisor import get_naja_supervisor
            supervisor = get_naja_supervisor()
            supervisor.shutdown()
            logger.info("所有组件已停止")
        except Exception as e:
            logger.error(f"关闭时保存状态失败: {e}")
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        logger.info("=== 正在重启 Naja ===")
        time.sleep(1)
        rport = 8080
        try:
            if PORT_FILE.exists():
                rport = int(PORT_FILE.read_text().strip())
        except Exception:
            pass
        env = os.environ.copy()
        if sys.platform == "darwin":
            env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
        log_file = NAJA_DIR / "logs" / "naja.log"
        cmd = [sys.executable, "-m", "deva.naja", f"--port={rport}"]
        subprocess.Popen(
            cmd,
            env=env,
            stdout=open(log_file, "a"),
            stderr=subprocess.STDOUT,
            cwd=os.getcwd(),
            start_new_session=True,
        )
        logger.info("=== 热重启完成 ===")
        sys.exit(0)

    setup_reload_handler(reload_handler)

    server.start()

    # loop 已由 _ensure_clean_event_loop 清洗，直接启动事件循环即可
    Deva.run()
