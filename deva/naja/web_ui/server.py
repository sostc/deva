"""Web 服务器启动"""

from __future__ import annotations


def run_server(port: int = 8080, host: str = '0.0.0.0', lab_config: dict = None, news_radar_config: dict = None, cognition_debug_config: dict = None, tune_config: dict = None):
    """兼容旧入口，内部已切到 application 层组合根。"""
    # 使用惰性导入避免循环依赖
    from ..application import AppRuntimeConfig, run_web_application
    
    config = AppRuntimeConfig.from_legacy(
        host=host,
        port=port,
        lab_config=lab_config,
        news_radar_config=news_radar_config,
        cognition_debug_config=cognition_debug_config,
        tune_config=tune_config,
    )
    run_web_application(config)
