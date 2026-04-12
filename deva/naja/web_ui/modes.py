"""启动模式初始化"""

from __future__ import annotations

from typing import Any

from deva import NB
from deva.naja.register import SR

_lab_mode_initialized = False
_news_radar_initialized = False





def _init_lab_mode(lab_config: dict):
    """初始化实验室模式

    1. 检查是否在交易时间（交易时间不允许启动实验）
    2. 创建回放数据源（如果指定了 table_name）
    3. 启动注意力系统实验模式

    Args:
        lab_config: 实验室配置，包含:
            - table_name: 回放数据表名
            - interval: 回放间隔（秒）
            - speed: 回放速度倍数
    """
    global _lab_mode_initialized
    if _lab_mode_initialized:
        print("🧪 实验室模式已初始化，跳过")
        return
    _lab_mode_initialized = True

    import uuid
    import time
    import os

    from ..radar.trading_clock import is_trading_time as is_trading_time_clock

    if is_trading_time_clock():
        print("⚠️ 当前处于交易时间，实验模式需要在非交易时间启动")
        print("⚠️ 请在收盘后或周末启动实验模式")
        _lab_mode_initialized = False
        return

    print("🧪 非交易时间检查通过，启动实验室模式...")
    # 设置调试模式环境变量
    if lab_config.get("debug"):
        os.environ["NAJA_LAB_DEBUG"] = "true"
        print("🧪 实验室调试模式已启用")
    else:
        os.environ["NAJA_LAB_DEBUG"] = "false"

    from ..datasource import get_datasource_manager, DataSourceEntry, UnitStatus
    from ..strategy import get_strategy_manager

    table_name = lab_config.get("table_name")
    interval = lab_config.get("interval", 1.0)
    speed = lab_config.get("speed", 1.0)

    ds_mgr = get_datasource_manager()
    strategy_mgr = get_strategy_manager()

    datasource_id = None

    if table_name:
        existing_replay_ds = None
        for ds in ds_mgr.list_all():
            if "历史行情回放" in ds.name and ds.name != "历史行情回放":
                continue
            if "历史行情回放" in ds.name:
                existing_replay_ds = ds
                break

        if existing_replay_ds:
            datasource_id = existing_replay_ds.id
            print(f"🧪 使用已有历史行情回放数据源: {datasource_id} ({existing_replay_ds.name})")

            if existing_replay_ds.status != UnitStatus.RUNNING:
                existing_replay_ds.start()
                print(f"🧪 数据源已启动")
        else:
            result = ds_mgr.create(
                name="历史行情回放",
                source_type="replay",
                config={
                    "table_name": table_name,
                    "interval": interval,
                    "speed": speed,
                }
            )

            if not result.get("success"):
                print(f"⚠️ 创建历史行情回放数据源失败: {result.get('error', '未知错误')}")
                return

            datasource_id = result.get("id")
            print(f"🧪 已创建历史行情回放数据源: {datasource_id}")

            time.sleep(0.5)

            lab_datasource = ds_mgr._items.get(datasource_id)
            if lab_datasource:
                lab_datasource.start()
                print(f"🧪 历史行情回放数据源已启动，回放间隔: {interval}s")
            else:
                print(f"⚠️ 找不到已创建的数据源: {datasource_id}")
                datasource_id = None

        if datasource_id:
            result = strategy_mgr.start_experiment(
                categories=[],  # 空列表表示所有类别
                datasource_id=datasource_id,
                include_attention=True  # 启用注意力策略
            )
            if result.get("success"):
                print(f"✅ 注意力策略实验模式已启动 (数据源: {datasource_id})")
            else:
                print(f"⚠️ 启动实验模式失败: {result.get('error', '未知错误')}")
        else:
            print("⚠️ 未指定回放数据表，仅启动注意力系统")


def _init_realtime_simulation_mode(interval: float = 0.5):
    """初始化实盘模拟模式

    在非交易时间模拟实盘 tick 数据，用于测试注意力系统的数据驱动能力。

    模拟数据格式与 realtime_tick_5s 一致，包含：
    - code: 股票代码
    - now: 当前价格
    - change_pct: 涨跌幅
    - volume: 成交量

    Args:
        interval: 数据生成间隔（秒），默认 0.5
    """
    import uuid
    import time
    import os

    os.environ["NAJA_LAB_DEBUG"] = "true"
    os.environ["NAJA_ATTENTION_ENABLED"] = "true"

    from ..datasource import get_datasource_manager

    ds_mgr = get_datasource_manager()

    sim_ds_name = f"实盘模拟-行情Tick-{uuid.uuid4().hex[:8]}"

    tick_func_code = '''
import time
import random
import pandas as pd
from typing import Any, Optional, Callable
from datetime import datetime

SYMBOLS = [
    "000001", "000002", "000063", "000333", "000338", "000651", "000858", "000876",
    "002415", "002594", "002714", "002230", "002236", "002371", "002460", "002475",
    "600000", "600009", "600016", "600019", "600028", "600030", "600036", "600050",
    "600100", "600104", "600109", "600111", "600150", "600170", "600183", "600196",
    "600276", "600309", "600406", "600436", "600438", "600519", "600570", "600585",
    "600690", "600703", "600745", "600760", "600809", "600837", "600887", "600893",
    "600905", "600918", "600941", "601006", "601012", "601066", "601088", "601118",
    "601138", "601166", "601169", "601186", "601211", "601288", "601318", "601328",
    "601336", "601390", "601398", "601601", "601628", "601658", "601688", "601698",
    "601728", "601766", "601800", "601816", "601857", "601888", "601899", "601919",
    "601939", "601988", "601989", "601995", "603259", "603288", "603501", "603799",
]

PRICE_BASE = {s: 10 + random.random() * 90 for s in SYMBOLS}

class TickSimulator:
    def __init__(self):
        self.prices = PRICE_BASE.copy()
        self.count = 0

    def generate_tick(self):
        self.count += 1
        data = []
        for symbol in SYMBOLS:
            prev_price = self.prices[symbol]
            change_pct = random.uniform(-5, 5)
            now_price = prev_price * (1 + change_pct / 100)
            self.prices[symbol] = now_price

            volume = int(random.uniform(10000, 1000000))

            data.append({
                "code": symbol,
                "now": round(now_price, 2),
                "change_pct": round(change_pct, 2),
                "p_change": round(change_pct, 2),
                "volume": volume,
                "amount": round(volume * now_price, 2),
                "timestamp": time.time(),
                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        df = pd.DataFrame(data)

        try:
            from deva import NB
            nb = NB("naja_realtime_quotes")
            for _, row in df.iterrows():
                nb.set(row['code'], {
                    'now': row['now'],
                    'change_pct': row['change_pct'],
                    'p_change': row['p_change'],
                    'volume': row['volume'],
                    'amount': row['amount'],
                })
        except Exception:
            pass

        return df

_simulator = TickSimulator()

def fetch_data():
    return _simulator.generate_tick()

def get_stream():
    return None
'''

    result = ds_mgr.create(
        name=sim_ds_name,
        func_code=tick_func_code,
        source_type="timer",
        config={"interval": interval},
        execution_mode="timer",
    )

    if not result.get("success"):
        print(f"⚠️ 创建实盘模拟数据源失败: {result.get('error', '未知错误')}")
        return None

    sim_ds_id = result.get("id")
    print(f"📈 已创建实盘模拟数据源: {sim_ds_name}, 间隔: {interval}s")

    time.sleep(0.3)

    sim_ds = ds_mgr._items.get(sim_ds_id)
    if sim_ds:
        sim_ds.start()
        print(f"📈 实盘模拟数据源已启动")
    else:
        print(f"⚠️ 找不到已创建的实盘模拟数据源")
        return None

    return {
        "datasource_id": sim_ds_id,
        "datasource_name": sim_ds_name,
    }


def _init_news_radar_mode():
    """初始化新闻雷达（默认模式）

    雷达引擎(RadarEngine)已内置新闻获取器，无需数据源。
    此函数仅确保 RadarEngine 的新闻获取器正常运行。
    """
    from ..radar import get_radar_engine

    radar = get_radar_engine()
    if radar._news_fetcher is not None and radar._news_fetcher._running:
        stats = radar.get_news_fetcher_stats()
        interval = stats.get('fetch_interval', 60) if stats else 60
        print(f"📡 新闻雷达已启用（RadarEngine 内置新闻获取器，运行中）")
    else:
        print(f"📡 新闻雷达已启用（RadarEngine 新闻获取器未运行）")


def _init_news_radar_speed_mode(news_radar_config: dict):
    """初始化新闻雷达加速模式

    通过 RadarEngine 加快新闻获取频率

    Args:
        news_radar_config: 配置，包含:
            - speed: 加速倍数
    """
    global _news_radar_initialized
    if _news_radar_initialized:
        print("📡 新闻雷达加速模式已初始化，跳过")
        return
    _news_radar_initialized = True
    import os
    os.environ["NAJA_NEWS_RADAR_DEBUG"] = "true"

    from ..radar import get_radar_engine

    speed = news_radar_config.get("speed", 1.0)
    radar = get_radar_engine()

    if radar._news_fetcher is None:
        print("⚠️ RadarEngine 新闻获取器未启动，加速模式无法启用")
        return

    base_interval = radar._news_fetcher._base_interval
    accelerated_interval = base_interval / speed

    radar.set_news_fetcher_interval(accelerated_interval)

    print(f"📡 新闻雷达加速模式已启用")
    print(f"📡 原始间隔: {base_interval:.1f}s -> 加速间隔: {accelerated_interval:.1f}s (×{speed})")


def _init_news_radar_sim_mode(news_radar_config: dict):
    """初始化新闻雷达模拟模式

    通过 RadarEngine 加快新闻获取频率（模拟模式）
    雷达内置会在真实获取失败时 fallback 到模拟数据

    Args:
        news_radar_config: 配置，包含:
            - interval: 模拟数据间隔（秒）
            - speed: 模拟速度倍数
    """
    global _news_radar_initialized
    if _news_radar_initialized:
        print("📡 新闻雷达模拟模式已初始化，跳过")
        return
    _news_radar_initialized = True
    import os
    os.environ["NAJA_NEWS_RADAR_DEBUG"] = "true"

    from ..radar import get_radar_engine

    sim_interval = news_radar_config.get("interval", 0.5)
    sim_speed = news_radar_config.get("speed", 1.0)

    radar = get_radar_engine()

    if radar._news_fetcher is None:
        print("⚠️ RadarEngine 新闻获取器未启动，模拟模式无法启用")
        return

    radar.set_news_fetcher_interval(sim_interval)

    print(f"📡 新闻雷达模拟模式已启用")
    print(f"📡 模拟间隔: {sim_interval}s (×{sim_speed})")


def _init_tune_mode(tune_config: dict):
    import os
    os.environ['NAJA_LAB_MODE'] = '1'

    """初始化调参模式"""
    print(f"🎯 调参模式已启用（持续循环优化版）")

    from .bandit.tuner import get_bandit_tuner
    tuner = get_bandit_tuner()
    tuner.start()
    tuner.register_callback(_on_tuner_event)

    scheduler = SR('replay_scheduler')
    if scheduler:
        scheduler.register_finished_callback(_on_replay_finished)

    print(f"🎯 调参器已启动，等待信号...")


def _on_tuner_event(event: str, data: Any):
    """处理调参器事件"""
    if event == 'new_best':
        log.info(f"🏆 新最优参数: {data.params}")
    elif event == 'params_relaxed':
        log.info(f"📊 参数放宽: {data}")
    elif event == 'signal_collected':
        count = data.get('count', 0)
        if count % 10 == 0:
            log.info(f"📥 已收集 {count} 个信号")


def _on_replay_finished():
    """数据回放结束时调用"""
    from .bandit.tuner import get_bandit_tuner
    tuner = get_bandit_tuner()
    tuner.on_data_replay_finished()


def _init_cognition_debug_mode():
    """初始化认知系统调试模式

    自动启用：
    1. 实验室模式（历史行情回放）
    2. 新闻雷达模拟模式（模拟新闻高速流入）
    """
    import os
    os.environ["NAJA_COGNITION_DEBUG"] = "true"

    from .datasource import get_datasource_manager
    from .strategy import get_strategy_manager

    print("🧠 认知系统调试模式已初始化")

    lab_config = {
        "enabled": True,
        "table_name": "quant_snapshot_5min_window",
        "interval": 0.5,
        "speed": 1.0,
        "debug": True,
    }
    _init_lab_mode(lab_config)

    news_radar_config = {
        "enabled": True,
        "mode": "sim",
        "interval": 0.3,
        "speed": 2.0,
    }
    _init_news_radar_sim_mode(news_radar_config)

    print("🧠 认知系统调试模式已完成初始化（实验室模式+新闻雷达模拟模式）")
