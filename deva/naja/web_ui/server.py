"""Web 服务器启动"""

from __future__ import annotations

from deva import NW, Deva

from .modes import (
    _init_lab_mode,
    _init_news_radar_mode,
    _init_news_radar_speed_mode,
    _init_news_radar_sim_mode,
    _init_cognition_debug_mode,
    _init_tune_mode,
)
from .routes import create_handlers


def run_server(port: int = 8080, host: str = '0.0.0.0', lab_config: dict = None, news_radar_config: dict = None, cognition_debug_config: dict = None, tune_config: dict = None):
    """启动服务器

    Args:
        port: Web 服务器端口
        host: 绑定地址
        lab_config: 实验室模式配置，如 {'enabled': True, 'table_name': 'xxx', 'interval': 1.0}
        news_radar_config: 新闻雷达配置，如 {'enabled': True, 'mode': 'normal'|'speed'|'sim', 'speed': 1.0}
        tune_config: 调参模式配置，如 {'enabled': True, 'search_method': 'grid', 'max_samples': 100}
    """
    print("=" * 60)
    print("🚀 Naja 管理平台启动中...")
    print("=" * 60)

    from ..bootstrap import SystemBootstrap
    from ..market_hotspot.integration.market_hotspot_config import load_config
    from tornado.ioloop import IOLoop
    import threading

    print("📂 启动系统引导流程...")
    bootstrap = SystemBootstrap()
    boot_result = bootstrap.boot()

    if not boot_result.success:
        print(f"❌ 系统引导失败: {boot_result.error}")

    load_counts = boot_result.details.get("load_counts", {}) if boot_result.details else {}
    load_errors = boot_result.details.get("load_errors", {}) if boot_result.details else {}
    restore_results = boot_result.details.get("restore_results", {}) if boot_result.details else {}
    restore_errors = boot_result.details.get("restore_errors", {}) if boot_result.details else {}

    if load_counts:
        print(f"📂 加载完成: 数据源({load_counts.get('datasource', 0)}) 任务({load_counts.get('task', 0)}) 策略({load_counts.get('strategy', 0)}) 字典({load_counts.get('dictionary', 0)})")
    if load_errors:
        error_info = ", ".join([f"{k}: {v}" for k, v in load_errors.items()])
        print(f"⚠️ 部分数据加载失败: {error_info}")

    if restore_results:
        print("🔄 运行状态恢复完成")
    if restore_errors:
        error_info = ", ".join([f"{k}: {v}" for k, v in restore_errors.items()])
        print(f"⚠️ 部分状态恢复失败: {error_info}")

    print("🎯 恢复 Bandit 自适应循环...")
    try:
        from .bandit import restore_bandit_state
        restore_bandit_state()
        print("✓ Bandit 自适应循环状态已恢复")
    except Exception as e:
        print(f"⚠️ Bandit 自适应循环恢复失败: {e}")

    # 注意力系统配置摘要（启动可见性）
    try:
        attention_config = load_config()
        config_source = "env"
        import os
        if os.path.exists(os.path.expanduser("~/.naja/attention_config.yaml")):
            config_source = "file+env"
        print(
            "🧭 注意力配置摘要: enabled="
            f"{attention_config.enabled}, intervals="
            f"{attention_config.high_interval}/{attention_config.medium_interval}/{attention_config.low_interval}s, "
            f"monitoring={attention_config.enable_monitoring}, source={config_source}"
        )
    except Exception as e:
        print(f"⚠️ 注意力配置读取失败: {e}")

    # 实验室模式初始化
    if lab_config and lab_config.get("enabled"):
        print("🧪 实验室模式已启用，准备启动...")
        _init_lab_mode(lab_config)

    # 新闻雷达初始化
    if news_radar_config and news_radar_config.get("enabled"):
        mode = news_radar_config.get("mode", "normal")
        if mode == "sim":
            print("📡 新闻雷达模拟模式已启用，准备启动...")
            _init_news_radar_sim_mode(news_radar_config)
        elif mode == "speed":
            print("📡 新闻雷达加速模式已启用，准备启动...")
            _init_news_radar_speed_mode(news_radar_config)
        else:
            print("📡 新闻雷达已启用，准备启动...")
            _init_news_radar_mode()

    # 认知系统调试模式初始化
    if cognition_debug_config and cognition_debug_config.get("enabled"):
        print("🧠 认知系统调试模式已启用，准备启动...")
        _init_cognition_debug_mode()

    # 调参模式初始化
    if tune_config and tune_config.get("enabled"):
        print("🎯 调参模式已启用，准备启动...")
        _init_tune_mode(tune_config)

    handlers = create_handlers()

    print(f"🌐 启动 Web 服务器: http://localhost:{port}")
    print("=" * 60)

    server = NW('naja_webview', host=host, port=port, start=False)
    server.application.add_handlers('.*$', handlers)
    server.start()

    asyncio_loop = getattr(IOLoop.current(), 'asyncio_loop', None)
    if asyncio_loop is None or not asyncio_loop.is_running():
        Deva.run()
    else:
        import signal
        import threading

        shutdown_event = threading.Event()

        def shutdown_handler(signum, frame):
            import logging
            logger = logging.getLogger("deva.naja")
            logger.info("收到退出信号，正在优雅关闭...")



            try:
                from .supervisor import get_naja_supervisor
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
        import sys
        sys.exit(0)
