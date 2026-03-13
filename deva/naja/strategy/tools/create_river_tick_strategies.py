"""
Create river-based tick strategies bound to realtime_tick_5s (fallback to replay).
"""

import sys
sys.path.insert(0, "/Users/spark/pycharmproject/deva")

from deva.naja.strategy import get_strategy_manager
from deva.naja.datasource import get_datasource_manager


def _pick_datasource():
    ds_mgr = get_datasource_manager()
    realtime = None
    replay = None
    for ds in ds_mgr.list_all():
        name = (ds.name or "").lower()
        if "realtime_tick_5s" in name:
            realtime = ds
        if "回放" in name or "replay" in name:
            replay = ds
    return realtime or replay


def _apply_config(entry, *, name, class_path, init_args, params, param_help, ds_id):
    config = {
        "class_path": class_path,
        "init_args": init_args or {},
        "param_help": param_help or {},
    }
    description = getattr(entry._metadata, "description", "")
    return entry.update_config(
        name=name,
        description=description,
        bound_datasource_id=ds_id,
        compute_mode="record",
        category="Tick-River",
        strategy_type="plugin",
        strategy_config=config,
        strategy_params=params or {},
    )


def _upsert_strategy(mgr, *, name, class_path, init_args, params, param_help, ds_id):
    existing = mgr.get_by_name(name)
    if existing:
        result = _apply_config(existing, name=name, class_path=class_path, init_args=init_args, params=params, param_help=param_help, ds_id=ds_id)
        return existing, result

    result = mgr.create(
        name=name,
        func_code="",
        bound_datasource_id=ds_id,
        description="River tick strategy",
        compute_mode="record",
        category="Tick-River",
        tags=["river", "tick", "anomaly", "memory", "radar"],
        max_history_count=200,
        strategy_type="plugin",
        strategy_config={},
        strategy_params=params or {},
    )
    entry = mgr.get(result.get("id")) if result.get("success") else None
    if entry is None:
        return entry, result
    update_result = _apply_config(entry, name=name, class_path=class_path, init_args=init_args, params=params, param_help=param_help, ds_id=ds_id)
    if not update_result.get("success"):
        return entry, update_result
    if entry.is_running:
        entry.stop()
        entry.start()
    return entry, update_result


def main():
    mgr = get_strategy_manager()
    ds_mgr = get_datasource_manager()
    ds_mgr.load_from_db()
    mgr.load_from_db()

    ds = _pick_datasource()
    if not ds:
        print("[ERROR] 未找到 realtime_tick_5s 或 行情回放 数据源")
        return

    print(f"[INFO] 绑定数据源: {ds.name} (ID: {ds.id})")

    strategies = [
        {
            "name": "river_tick_异常分数_hst",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickAnomalyHST",
            "init_args": {"n_trees": 25, "height": 15, "window_size": 250},
            "params": {"n_trees": 25, "height": 15, "window_size": 250},
            "param_help": {
                "n_trees": "HalfSpaceTrees 树数量，越大越稳定但更慢",
                "height": "树高度，影响异常分辨率",
                "window_size": "滑动窗口大小",
            },
        },
        {
            "name": "river_tick_市场状态聚类",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickRegimeCluster",
            "init_args": {"n_clusters": 3, "halflife": 0.6},
            "params": {"n_clusters": 3, "halflife": 0.6},
            "param_help": {
                "n_clusters": "聚类数量（市场状态数量）",
                "halflife": "遗忘系数，越大越依赖近期",
            },
        },
        {
            "name": "river_tick_漂移检测_adwin",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickDriftADWIN",
            "init_args": {"min_n": 30},
            "params": {"min_n": 30},
            "param_help": {
                "min_n": "最小样本数后才触发漂移检测",
            },
        },
        {
            "name": "river_tick_量价尖峰",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickVolumePriceSpike",
            "init_args": {"vol_z_threshold": 2.0},
            "params": {"vol_z_threshold": 2.0},
            "param_help": {
                "vol_z_threshold": "成交量尖峰阈值（当前仅作保留参数）",
            },
        },
        {
            "name": "river_tick_动量趋势",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickMomentumTrend",
            "init_args": {"trend_scale": 100.0},
            "params": {"trend_scale": 100.0},
            "param_help": {
                "trend_scale": "动量放大系数，越大越敏感",
            },
        },
        {
            "name": "river_tick_趋势反转",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickTrendReversal",
            "init_args": {"min_delta": 0.001},
            "params": {"min_delta": 0.001},
            "param_help": {
                "min_delta": "反转判定阈值（均值涨跌幅）",
            },
        },
        {
            "name": "river_tick_波动率爆发",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickVolatilityBurst",
            "init_args": {"burst_threshold": 0.02},
            "params": {"burst_threshold": 0.02},
            "param_help": {
                "burst_threshold": "波动率爆发阈值（std_p_change）",
            },
        },
        {
            "name": "river_tick_强弱分布集中度",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickBreadthConcentration",
            "init_args": {"strong_threshold": 0.65},
            "params": {"strong_threshold": 0.65},
            "param_help": {
                "strong_threshold": "强弱集中阈值（涨/跌占比）",
            },
        },
        {
            "name": "river_tick_资金集中度",
            "class_path": "deva.naja.strategy.river_tick_strategies.RiverTickCapitalConcentration",
            "init_args": {"std_scale": 10.0},
            "params": {"std_scale": 10.0},
            "param_help": {
                "std_scale": "集中度放大系数",
            },
        },
    ]

    for spec in strategies:
        entry, result = _upsert_strategy(mgr, ds_id=ds.id, **spec)
        if result.get("success"):
            print(f"[SUCCESS] {spec['name']} 已创建/更新")
            if entry and not entry.is_running:
                start = entry.start()
                if start.get("success"):
                    print(f"  -> 已启动")
                else:
                    print(f"  -> 启动失败: {start.get('error')}")
        else:
            print(f"[ERROR] {spec['name']} 创建/更新失败: {result.get('error')}")


if __name__ == "__main__":
    main()
