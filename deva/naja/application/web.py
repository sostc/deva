from __future__ import annotations

from deva import NW, Deva

from .container import AppContainer, set_app_container
from .runtime_config import AppRuntimeConfig


def run_web_application(config: AppRuntimeConfig):
    print("=" * 60)
    print("🚀 Naja 管理平台启动中...")
    print("=" * 60)

    from tornado.ioloop import IOLoop

    print("📂 启动系统引导流程...")
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

    server = NW("naja_webview", host=host, port=port, start=False)
    server.application.add_handlers(".*$", handlers)
    server.start()

    asyncio_loop = getattr(IOLoop.current(), "asyncio_loop", None)
    if asyncio_loop is None or not asyncio_loop.is_running():
        Deva.run()
        return

    import logging
    import signal
    import sys
    import threading

    logger = logging.getLogger("deva.naja")
    shutdown_event = threading.Event()

    def shutdown_handler(signum, frame):
        logger.info("收到退出信号，正在优雅关闭...")
        try:
            from deva.naja.supervisor import get_naja_supervisor

            supervisor = get_naja_supervisor()
            supervisor.shutdown()
            logger.info("所有组件已停止，数据已持久化")
        except Exception as e:
            logger.error(f"关闭时保存状态失败: {e}")
        shutdown_event.set()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        shutdown_handler(None, None)

    logger.info("程序退出")
    sys.exit(0)
