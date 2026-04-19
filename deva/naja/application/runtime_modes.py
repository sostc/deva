from __future__ import annotations

from .runtime_config import AppRuntimeConfig
from ..web_ui import modes as legacy_modes


class RuntimeModeInitializer:
    """Application-layer coordinator for optional runtime modes."""

    def __init__(self, config: AppRuntimeConfig):
        self.config = config

    def initialize(self) -> None:
        self._init_lab_mode()
        self._init_news_radar_mode()
        self._init_cognition_debug_mode()
        self._init_tune_mode()

    def _init_lab_mode(self) -> None:
        if self.config.lab.enabled:
            print("🧪 实验室模式已启用，准备启动...")
            legacy_modes._init_lab_mode(self.config.lab.to_legacy_dict())

    def _init_news_radar_mode(self) -> None:
        cfg = self.config.news_radar
        if not cfg.enabled:
            return

        if cfg.mode == "sim":
            print("📡 新闻雷达模拟模式已启用，准备启动...")
            legacy_modes._init_news_radar_sim_mode(cfg.to_legacy_dict())
        elif cfg.mode == "speed":
            print("📡 新闻雷达加速模式已启用，准备启动...")
            legacy_modes._init_news_radar_speed_mode(cfg.to_legacy_dict())
        else:
            print("📡 新闻雷达已启用，准备启动...")
            legacy_modes._init_news_radar_mode()

    def _init_cognition_debug_mode(self) -> None:
        if self.config.cognition_debug.enabled:
            print("🧠 认知系统调试模式已启用，准备启动...")
            legacy_modes._init_cognition_debug_mode()

    def _init_tune_mode(self) -> None:
        if self.config.tune.enabled:
            print("🎯 调参模式已启用，准备启动...")
            legacy_modes._init_tune_mode(self.config.tune.to_legacy_dict())
