"""Naja 启动模式配置

本模块统一管理 Naja 系统的所有启动模式和配置选项

启动模式分类
============

1. 正常交易模式 (Normal Trading Mode)
   - 默认模式
   - 启用新闻雷达（真实数据源）
   - 启动实时数据获取 (RealtimeDataFetcher)

2. 实验室模式 (Lab Mode)
   - 用于回放历史数据测试
   - 与正常交易模式互斥
   - 交易时间禁止启动

3. 新闻雷达模式 (News Radar Mode)
   - 默认启用
   - 三种子模式: normal / speed / sim

4. 认知调试模式 (Cognition Debug Mode)
   - 自动组合: 实验室模式 + 新闻雷达模拟模式

启动参数速查
============

| 命令 | 说明 |
|------|------|
| python -m deva.naja | 默认启动（正常交易+新闻雷达） |
| python -m deva.naja --lab --lab-table xxx | 实验室模式回放 |
| python -m deva.naja --news-radar-speed 10 | 新闻雷达10倍速 |
| python -m deva.naja --news-radar-sim | 新闻雷达模拟模式 |
| python -m deva.naja --cognition-debug | 完整认知调试模式 |

环境变量
========

| 变量 | 说明 |
|------|------|
| NAJA_LAB_MODE | 实验室模式标志 (值为'1') |
| NAJA_LAB_DEBUG | 实验室调试日志 |
| NAJA_NEWS_RADAR_DEBUG | 新闻雷达调试日志 |
| NAJA_COGNITION_DEBUG | 认知系统调试日志 |
"""

from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class StartupMode(Enum):
    """Naja 启动模式枚举"""
    NORMAL = "normal"           # 正常交易模式
    LAB = "lab"                # 实验室模式
    COGNITION_DEBUG = "cognition_debug"  # 认知调试模式
    TUNE = "tune"             # 调参模式：用历史数据搜索最优参数


class NewsRadarMode(Enum):
    """新闻雷达子模式"""
    NORMAL = "normal"          # 默认：真实数据源，正常频率
    SPEED = "speed"           # 加速：真实数据源，加快频率
    SIM = "sim"               # 模拟：使用模拟数据源


@dataclass
class StartupConfig:
    """Naja 启动配置"""
    mode: StartupMode = StartupMode.NORMAL
    news_radar_mode: NewsRadarMode = NewsRadarMode.NORMAL
    news_radar_speed: float = 1.0
    lab_table: Optional[str] = None
    lab_interval: float = 1.0
    lab_speed: float = 1.0
    lab_debug: bool = False
    tune_enabled: bool = False
    tune_search_method: str = "grid"
    tune_max_samples: int = 100
    tune_export_path: Optional[str] = None

    @property
    def is_lab_mode(self) -> bool:
        return self.mode in (StartupMode.LAB, StartupMode.COGNITION_DEBUG, StartupMode.TUNE)

    @property
    def is_trading_allowed(self) -> bool:
        """是否允许在交易时间启动"""
        return not self.is_lab_mode

    def __str__(self) -> str:
        mode_str = f"mode={self.mode.value}"
        if self.is_lab_mode:
            mode_str += f", lab_table={self.lab_table}"
        mode_str += f", news_radar={self.news_radar_mode.value}"
        if self.news_radar_mode == NewsRadarMode.SPEED:
            mode_str += f"({self.news_radar_speed}x)"
        return f"StartupConfig({mode_str})"


# 模式组合关系映射表
MODE_COMBINATIONS = {
    # 正常交易模式
    "default": StartupConfig(
        mode=StartupMode.NORMAL,
        news_radar_mode=NewsRadarMode.NORMAL,
    ),

    # 实验室模式
    "lab": StartupConfig(
        mode=StartupMode.LAB,
        news_radar_mode=NewsRadarMode.NORMAL,
    ),

    # 实验室模式 + 新闻雷达加速
    "lab_speed": StartupConfig(
        mode=StartupMode.LAB,
        news_radar_mode=NewsRadarMode.SPEED,
        news_radar_speed=10.0,
    ),

    # 实验室模式 + 新闻雷达模拟
    "lab_sim": StartupConfig(
        mode=StartupMode.LAB,
        news_radar_mode=NewsRadarMode.SIM,
    ),

    # 认知调试模式（自动组合）
    "cognition_debug": StartupConfig(
        mode=StartupMode.COGNITION_DEBUG,
        news_radar_mode=NewsRadarMode.SIM,
        lab_table="quant_snapshot_5min_window",
        lab_interval=0.5,
        lab_debug=True,
    ),

    # 调参模式
    "tune": StartupConfig(
        mode=StartupMode.TUNE,
        news_radar_mode=NewsRadarMode.NORMAL,
        tune_enabled=True,
        tune_search_method="grid",
    ),
}


def get_mode_description(mode: StartupMode) -> str:
    """获取模式描述"""
    descriptions = {
        StartupMode.NORMAL: "正常交易模式 - 启用实时数据获取和新闻雷达",
        StartupMode.LAB: "实验室模式 - 回放历史数据，与正常交易模式互斥",
        StartupMode.COGNITION_DEBUG: "认知调试模式 - 自动启用实验室+新闻雷达模拟",
        StartupMode.TUNE: "调参模式 - 用历史数据搜索最优参数",
    }
    return descriptions.get(mode, "未知模式")


def get_news_radar_description(mode: NewsRadarMode) -> str:
    """获取新闻雷达子模式描述"""
    descriptions = {
        NewsRadarMode.NORMAL: "真实数据源，正常频率",
        NewsRadarMode.SPEED: "真实数据源，加速频率",
        NewsRadarMode.SIM: "模拟数据源",
    }
    return descriptions.get(mode, "未知模式")


# 便捷函数：创建常用配置
def create_normal_config() -> StartupConfig:
    """创建正常交易模式配置"""
    return MODE_COMBINATIONS["default"]


def create_lab_config(table_name: str, interval: float = 1.0, speed: float = 1.0) -> StartupConfig:
    """创建实验室模式配置"""
    return StartupConfig(
        mode=StartupMode.LAB,
        news_radar_mode=NewsRadarMode.NORMAL,
        lab_table=table_name,
        lab_interval=interval,
        lab_speed=speed,
    )


def create_cognition_debug_config() -> StartupConfig:
    """创建认知调试模式配置"""
    return MODE_COMBINATIONS["cognition_debug"]


