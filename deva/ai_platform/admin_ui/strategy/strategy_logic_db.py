"""策略逻辑数据库模块(Strategy Logic Database)

将股票策略的分析计算逻辑代码整合并保存到数据库，支持：
- 策略逻辑代码的持久化存储
- 程序启动时从数据库加载策略逻辑
- 程序关闭时保存策略状态
- 策略逻辑的版本管理

================================================================================
架构设计
================================================================================

【策略逻辑存储结构】
┌─────────────────────────────────────────────────────────────────────────────┐
│  strategy_logic (数据库表)                                                   │
│  ├── id: 策略逻辑ID                                                          │
│  ├── name: 策略名称                                                          │
│  ├── strategy_type: 策略类型 (block_change/block_ranking/limit_up_down/...)  │
│  ├── code: 策略计算逻辑代码                                                   │
│  ├── params_schema: 参数模式定义 (JSON)                                       │
│  ├── default_params: 默认参数 (JSON)                                          │
│  ├── description: 策略描述                                                   │
│  ├── version: 版本号                                                         │
│  ├── created_at: 创建时间                                                    │
│  └── updated_at: 更新时间                                                    │
└─────────────────────────────────────────────────────────────────────────────┘

【策略实例存储结构】
┌─────────────────────────────────────────────────────────────────────────────┐
│  strategy_instances (数据库表)                                               │
│  ├── id: 实例ID                                                              │
│  ├── logic_id: 关联的策略逻辑ID                                               │
│  ├── name: 实例名称                                                          │
│  ├── params: 实例参数 (JSON)                                                  │
│  ├── state: 运行状态 (running/paused/draft/archived)                          │
│  ├── upstream: 上游数据源配置 (JSON)                                           │
│  ├── downstream: 下游输出配置 (JSON)                                           │
│  ├── processed_count: 处理计数                                                │
│  ├── error_count: 错误计数                                                   │
│  ├── last_error: 最近错误                                                    │
│  ├── created_at: 创建时间                                                    │
│  └── updated_at: 更新时间                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
import hashlib

from deva import NB, log


@dataclass
class StrategyLogicMeta:
    """策略逻辑元数据"""
    id: str
    name: str
    strategy_type: str
    code: str = ""
    params_schema: dict = field(default_factory=dict)
    default_params: dict = field(default_factory=dict)
    description: str = ""
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyLogicMeta":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class StrategyInstanceState:
    """策略实例状态"""
    id: str
    logic_id: str
    name: str
    params: dict = field(default_factory=dict)
    state: str = "draft"
    upstream: dict = field(default_factory=dict)
    downstream: dict = field(default_factory=dict)
    processed_count: int = 0
    error_count: int = 0
    last_error: str = ""
    last_error_ts: float = 0
    last_process_ts: float = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyInstanceState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


BLOCK_CHANGE_CODE = '''
def _format_pct(val):
    """格式化百分比显示"""
    if not isinstance(val, (int, float)):
        return str(val)
    pct = val * 100
    if val > 0:
        return f"<span class='up'>+{pct:.2f}%</span>"
    elif val < 0:
        return f"<span class='down'>{pct:.2f}%</span>"
    return f"{pct:.2f}%"


def _prepare_df(df, cols=None):
    """准备DataFrame，添加元数据并展开板块"""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    if cols:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        df = df[cols].copy()
    else:
        df = df.copy()
    
    if "blockname" not in df.columns:
        df["blockname"] = "unknown"
    if "name" not in df.columns:
        df["name"] = df["code"].astype(str) if "code" in df.columns else "unknown"
    
    df["blockname"] = df["blockname"].fillna("unknown").astype(str)
    df["blockname_item"] = df["blockname"].map(
        lambda x: [item.strip() for item in x.split("|") if item and item.strip()] or ["unknown"]
    )
    df = df.explode("blockname_item", ignore_index=True)
    return df


def _calc_block_ranking(df, col, n=20, top=True):
    """计算板块排名"""
    df = df.copy()
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    grouped = (
        df.sort_values([col], ascending=not top)
        .groupby("blockname_item").head(n)
        .groupby("blockname_item")[col].mean()
        .to_frame(col)
        .sort_values(col, ascending=not top).head(10)
    )
    return grouped


def _get_top_stocks_in_block(df, blockname, col, n=3, top=True):
    """获取板块内TOP股票"""
    block_df = df[df["blockname_item"] == blockname].copy()
    block_df = block_df.sort_values(col, ascending=not top).head(n)
    return block_df


def process(df, window_data, params):
    """板块异动策略处理函数
    
    参数:
        df: 当前行情DataFrame
        window_data: 时间窗口数据列表
        params: 策略参数
            - window_size: 窗口大小
            - top_n: 返回的板块数量
            - sample_n: 每个板块取样的股票数量
    
    返回:
        HTML格式的板块异动报告
    """
    import pandas as pd
    
    window_size = params.get("window_size", 6)
    top_n = params.get("top_n", 5)
    sample_n = params.get("sample_n", 3)
    
    if len(window_data) < 2:
        return None, window_data
    
    start_df = window_data[0]
    end_df = window_data[-1]
    
    end_df = end_df.copy()
    valid_mask = start_df["close"] > 0
    if not valid_mask.any():
        return "<p>暂无有效数据</p>", window_data
    
    end_df = end_df[valid_mask].copy()
    start_df = start_df[valid_mask].copy()
    end_df["change"] = (end_df["now"] - start_df["now"]) / start_df["close"]
    
    df = _prepare_df(end_df, ["code", "change", "p_change", "name"])
    if df.empty:
        return "<p>暂无有效数据</p>", window_data
    
    max_group = _calc_block_ranking(df, "change", n=sample_n, top=True)
    min_group = _calc_block_ranking(df, "change", n=sample_n, top=False)
    
    def build_detail(group, df, top):
        parts = []
        for blockname in group.index[:top_n]:
            stocks = _get_top_stocks_in_block(df, blockname, "change", n=sample_n, top=top)
            if len(stocks) > 0:
                stock_info = ", ".join([
                    f"{row['name']}({_format_pct(row['change'])})"
                    for _, row in stocks.iterrows()
                ])
                avg = group.loc[blockname, "change"]
                parts.append(f"<b>{blockname}</b>({_format_pct(avg)}): {stock_info}")
        return "<br>".join(parts) if parts else "暂无数据"
    
    up_detail = build_detail(max_group, df, top=True)
    down_detail = build_detail(min_group, df, top=False)
    
    html = f"""
    <h4>板块异动-涨幅TOP{top_n}</h4>
    <div style='padding:8px;background:#fff5f5;border-radius:6px;margin:4px 0;'>{up_detail}</div>
    <h4>板块异动-跌幅TOP{top_n}</h4>
    <div style='padding:8px;background:#f0fff4;border-radius:6px;margin:4px 0;'>{down_detail}</div>
    """
    return html, window_data
'''


BLOCK_RANKING_CODE = '''
def _format_pct(val):
    """格式化百分比显示"""
    if not isinstance(val, (int, float)):
        return str(val)
    pct = val * 100
    if val > 0:
        return f"<span class='up'>+{pct:.2f}%</span>"
    elif val < 0:
        return f"<span class='down'>{pct:.2f}%</span>"
    return f"{pct:.2f}%"


def _prepare_df(df, cols=None):
    """准备DataFrame，添加元数据并展开板块"""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    if cols:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        df = df[cols].copy()
    else:
        df = df.copy()
    
    if "blockname" not in df.columns:
        df["blockname"] = "unknown"
    if "name" not in df.columns:
        df["name"] = df["code"].astype(str) if "code" in df.columns else "unknown"
    
    df["blockname"] = df["blockname"].fillna("unknown").astype(str)
    df["blockname_item"] = df["blockname"].map(
        lambda x: [item.strip() for item in x.split("|") if item and item.strip()] or ["unknown"]
    )
    df = df.explode("blockname_item", ignore_index=True)
    return df


def _calc_block_ranking(df, col, n=20, top=True):
    """计算板块排名"""
    df = df.copy()
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    grouped = (
        df.sort_values([col], ascending=not top)
        .groupby("blockname_item").head(n)
        .groupby("blockname_item")[col].mean()
        .to_frame(col)
        .sort_values(col, ascending=not top).head(10)
    )
    return grouped


def _get_top_stocks_in_block(df, blockname, col, n=3, top=True):
    """获取板块内TOP股票"""
    block_df = df[df["blockname_item"] == blockname].copy()
    block_df = block_df.sort_values(col, ascending=not top).head(n)
    return block_df


def process(df, params):
    """领涨领跌板块策略处理函数
    
    参数:
        df: 当前行情DataFrame
        params: 策略参数
            - sample_sizes: 样本数量列表
            - top_n: 返回的板块数量
            - sample_n: 每个板块取样的股票数量
    
    返回:
        HTML格式的领涨领跌板块报告
    """
    import pandas as pd
    
    sample_sizes = params.get("sample_sizes", [20, 50])
    top_n = params.get("top_n", 5)
    sample_n = params.get("sample_n", 3)
    
    df = _prepare_df(df, ["code", "p_change", "name"])
    if df.empty:
        return "<p>暂无有效数据</p>"
    
    parts = []
    for n in sample_sizes:
        max_g = _calc_block_ranking(df, "p_change", n=n, top=True)
        min_g = _calc_block_ranking(df, "p_change", n=n, top=False)
        
        def build_block_detail(group, top):
            details = []
            for blockname in group.index[:top_n]:
                stocks = _get_top_stocks_in_block(df, blockname, "p_change", n=sample_n, top=top)
                if len(stocks) > 0:
                    stock_info = ", ".join([
                        f"{row['name']}({_format_pct(row['p_change'])})"
                        for _, row in stocks.iterrows()
                    ])
                    avg = group.loc[blockname, "p_change"]
                    details.append(f"<b>{blockname}</b>({_format_pct(avg)}): {stock_info}")
            return "<br>".join(details) if details else "暂无数据"
        
        up_html = f"<h4>领涨板块TOP{top_n} (样本{n}只)</h4><div style='padding:8px;background:#fff5f5;border-radius:6px;margin:4px 0;'>{build_block_detail(max_g, top=True)}</div>"
        down_html = f"<h4>领跌板块TOP{top_n} (样本{n}只)</h4><div style='padding:8px;background:#f0fff4;border-radius:6px;margin:4px 0;'>{build_block_detail(min_g, top=False)}</div>"
        parts.extend([up_html, down_html])
    
    return "".join(parts)
'''


LIMIT_UP_DOWN_CODE = '''
def _format_pct(val):
    """格式化百分比显示"""
    if not isinstance(val, (int, float)):
        return str(val)
    pct = val * 100
    if val > 0:
        return f"<span class='up'>+{pct:.2f}%</span>"
    elif val < 0:
        return f"<span class='down'>{pct:.2f}%</span>"
    return f"{pct:.2f}%"


def _prepare_df(df, cols=None):
    """准备DataFrame，添加元数据并展开板块"""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    if cols:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        df = df[cols].copy()
    else:
        df = df.copy()
    
    if "blockname" not in df.columns:
        df["blockname"] = "unknown"
    if "name" not in df.columns:
        df["name"] = df["code"].astype(str) if "code" in df.columns else "unknown"
    
    df["blockname"] = df["blockname"].fillna("unknown").astype(str)
    df["blockname_item"] = df["blockname"].map(
        lambda x: [item.strip() for item in x.split("|") if item and item.strip()] or ["unknown"]
    )
    df = df.explode("blockname_item", ignore_index=True)
    return df


def process(df, params):
    """涨跌停统计策略处理函数
    
    参数:
        df: 当前行情DataFrame
        params: 策略参数
            - limit_threshold: 涨跌停阈值
            - top_n: 每个板块显示的股票数量
    
    返回:
        HTML格式的涨跌停统计报告
    """
    import pandas as pd
    
    threshold = params.get("limit_threshold", 0.098)
    top_n = params.get("top_n", 5)
    
    zt_raw = df.query(f"p_change>{threshold}")[["code", "p_change"]]
    dt_raw = df.query(f"p_change<-{threshold}")[["code", "p_change"]]
    
    zt_df = _prepare_df(zt_raw, ["code", "p_change"])
    dt_df = _prepare_df(dt_raw, ["code", "p_change"])
    
    zt_count = int(df.query(f"p_change>{threshold}")["code"].nunique())
    dt_count = int(df.query(f"p_change<-{threshold}")["code"].nunique())
    
    def build_stock_list(stock_df, top=True):
        if len(stock_df) == 0:
            return "暂无数据"
        grouped = stock_df.groupby("blockname_item").apply(
            lambda g: ", ".join([
                f"{row['name']}({_format_pct(row['p_change'])})"
                for _, row in g.sort_values("p_change", ascending=not top).head(top_n).iterrows()
            ])
        )
        parts = [f"<b>{block}</b>: {stocks}" for block, stocks in grouped.head(10).items()]
        return "<br>".join(parts)
    
    zt_html = f"<h4>涨停 {zt_count} 只</h4><div style='padding:8px;background:#fff5f5;border-radius:6px;margin:4px 0;'>{build_stock_list(zt_df, top=True)}</div>"
    dt_html = f"<h4>跌停 {dt_count} 只</h4><div style='padding:8px;background:#f0fff4;border-radius:6px;margin:4px 0;'>{build_stock_list(dt_df, top=False)}</div>"
    
    return zt_html + dt_html
'''


CUSTOM_FILTER_CODE = '''
def process(df, params):
    """自定义股票筛选策略处理函数
    
    参数:
        df: 当前行情DataFrame
        params: 策略参数
            - filter_expr: 筛选表达式 (pandas query 语法)
            - output_columns: 输出的列名列表
            - sort_column: 排序列名
            - sort_ascending: 是否升序
            - limit: 输出数量限制
    
    返回:
        筛选后的DataFrame
    """
    import pandas as pd
    
    filter_expr = params.get("filter_expr", "p_change > 0.05")
    output_columns = params.get("output_columns", ["code", "name", "p_change", "blockname"])
    sort_column = params.get("sort_column", "p_change")
    sort_ascending = params.get("sort_ascending", False)
    limit = params.get("limit", 50)
    
    try:
        filtered = df.query(filter_expr).copy()
    except Exception as e:
        raise ValueError(f"Filter expression error: {e}")
    
    if len(filtered) == 0:
        return pd.DataFrame(columns=output_columns)
    
    available_cols = [c for c in output_columns if c in filtered.columns]
    result = filtered[available_cols]
    
    if sort_column in result.columns:
        result = result.sort_values(sort_column, ascending=sort_ascending)
    
    return result.head(limit)
'''


DEFAULT_STRATEGY_LOGICS = [
    {
        "id": "block_change_v1",
        "name": "板块异动策略",
        "strategy_type": "block_change",
        "code": BLOCK_CHANGE_CODE,
        "params_schema": {
            "window_size": {"type": "int", "default": 6, "description": "滑动窗口大小"},
            "top_n": {"type": "int", "default": 5, "description": "返回的板块数量"},
            "sample_n": {"type": "int", "default": 3, "description": "每个板块取样的股票数量"},
        },
        "default_params": {"window_size": 6, "top_n": 5, "sample_n": 3},
        "description": "计算板块在时间窗口内的涨跌幅变化，支持多时间窗口",
        "tags": ["板块", "异动", "实时"],
    },
    {
        "id": "block_ranking_v1",
        "name": "领涨领跌板块策略",
        "strategy_type": "block_ranking",
        "code": BLOCK_RANKING_CODE,
        "params_schema": {
            "sample_sizes": {"type": "list", "default": [20, 50], "description": "样本数量列表"},
            "top_n": {"type": "int", "default": 5, "description": "返回的板块数量"},
            "sample_n": {"type": "int", "default": 3, "description": "每个板块取样的股票数量"},
        },
        "default_params": {"sample_sizes": [20, 50], "top_n": 5, "sample_n": 3},
        "description": "计算当日各板块的涨跌幅排名，支持多样本量统计",
        "tags": ["板块", "排名", "领涨领跌"],
    },
    {
        "id": "limit_up_down_v1",
        "name": "涨跌停统计策略",
        "strategy_type": "limit_up_down",
        "code": LIMIT_UP_DOWN_CODE,
        "params_schema": {
            "limit_threshold": {"type": "float", "default": 0.098, "description": "涨跌停阈值"},
            "top_n": {"type": "int", "default": 5, "description": "每个板块显示的股票数量"},
        },
        "default_params": {"limit_threshold": 0.098, "top_n": 5},
        "description": "统计涨停和跌停的股票数量及板块分布",
        "tags": ["涨跌停", "统计", "实时"],
    },
    {
        "id": "custom_filter_v1",
        "name": "自定义股票筛选策略",
        "strategy_type": "custom_filter",
        "code": CUSTOM_FILTER_CODE,
        "params_schema": {
            "filter_expr": {"type": "str", "default": "p_change > 0.05", "description": "筛选表达式"},
            "output_columns": {"type": "list", "default": ["code", "name", "p_change", "blockname"], "description": "输出列"},
            "sort_column": {"type": "str", "default": "p_change", "description": "排序列"},
            "sort_ascending": {"type": "bool", "default": False, "description": "是否升序"},
            "limit": {"type": "int", "default": 50, "description": "输出数量限制"},
        },
        "default_params": {"filter_expr": "p_change > 0.05", "output_columns": ["code", "name", "p_change", "blockname"], "sort_column": "p_change", "sort_ascending": False, "limit": 50},
        "description": "根据用户自定义条件筛选股票",
        "tags": ["筛选", "自定义", "条件"],
    },
]


class StrategyLogicDB:
    """策略逻辑数据库管理器
    
    提供策略逻辑代码的存储、加载和管理功能。
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._db = NB("strategy_logic")
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> "StrategyLogicDB":
        return cls()
    
    def initialize(self) -> int:
        """初始化默认策略逻辑到数据库
        
        Returns:
            初始化的策略数量
        """
        count = 0
        for logic_data in DEFAULT_STRATEGY_LOGICS:
            logic_id = logic_data["id"]
            if logic_id not in self._db:
                logic = StrategyLogicMeta(
                    id=logic_id,
                    name=logic_data["name"],
                    strategy_type=logic_data["strategy_type"],
                    code=logic_data["code"],
                    params_schema=logic_data.get("params_schema", {}),
                    default_params=logic_data.get("default_params", {}),
                    description=logic_data.get("description", ""),
                    tags=logic_data.get("tags", []),
                )
                self._db[logic_id] = logic.to_dict()
                count += 1
        return count
    
    def get_logic(self, logic_id: str) -> Optional[StrategyLogicMeta]:
        """获取策略逻辑
        
        Args:
            logic_id: 策略逻辑ID
        
        Returns:
            StrategyLogicMeta 或 None
        """
        data = self._db.get(logic_id)
        if data:
            return StrategyLogicMeta.from_dict(data)
        return None
    
    def get_logic_by_type(self, strategy_type: str) -> Optional[StrategyLogicMeta]:
        """根据策略类型获取策略逻辑
        
        Args:
            strategy_type: 策略类型
        
        Returns:
            StrategyLogicMeta 或 None
        """
        for logic_id, data in self._db.items():
            if isinstance(data, dict) and data.get("strategy_type") == strategy_type:
                return StrategyLogicMeta.from_dict(data)
        return None
    
    def list_all(self) -> List[StrategyLogicMeta]:
        """列出所有策略逻辑
        
        Returns:
            策略逻辑列表
        """
        logics = []
        for logic_id, data in self._db.items():
            if isinstance(data, dict):
                logics.append(StrategyLogicMeta.from_dict(data))
        return logics
    
    def save_logic(self, logic: StrategyLogicMeta) -> dict:
        """保存策略逻辑
        
        Args:
            logic: 策略逻辑对象
        
        Returns:
            保存结果
        """
        logic.updated_at = time.time()
        self._db[logic.id] = logic.to_dict()
        return {"success": True, "id": logic.id}
    
    def delete_logic(self, logic_id: str) -> dict:
        """删除策略逻辑
        
        Args:
            logic_id: 策略逻辑ID
        
        Returns:
            删除结果
        """
        if logic_id in self._db:
            del self._db[logic_id]
            return {"success": True}
        return {"success": False, "error": "Logic not found"}
    
    def compile_logic(self, logic_id: str) -> Optional[Callable]:
        """编译策略逻辑代码
        
        Args:
            logic_id: 策略逻辑ID
        
        Returns:
            编译后的处理函数或None
        """
        import pandas as pd
        
        logic = self.get_logic(logic_id)
        if not logic or not logic.code:
            return None
        
        try:
            local_ns = {"__builtins__": __builtins__, "pd": pd}
            exec(logic.code, local_ns, local_ns)
            
            if "process" in local_ns and callable(local_ns["process"]):
                return local_ns["process"]
            return None
        except Exception as e:
            print(f"[StrategyLogicDB] Compile error for {logic_id}: {e}")
            return None


class StrategyInstanceDB:
    """策略实例数据库管理器
    
    提供策略实例状态的存储、加载和管理功能。
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._db = NB("strategy_instances")
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> "StrategyInstanceDB":
        return cls()
    
    def get_instance_state(self, instance_id: str) -> Optional[StrategyInstanceState]:
        """获取策略实例状态
        
        Args:
            instance_id: 实例ID
        
        Returns:
            StrategyInstanceState 或 None
        """
        data = self._db.get(instance_id)
        if data:
            return StrategyInstanceState.from_dict(data)
        return None
    
    def list_all(self) -> List[StrategyInstanceState]:
        """列出所有策略实例状态
        
        Returns:
            策略实例状态列表
        """
        instances = []
        for instance_id, data in self._db.items():
            if isinstance(data, dict):
                instances.append(StrategyInstanceState.from_dict(data))
        return instances
    
    def list_by_state(self, state: str) -> List[StrategyInstanceState]:
        """按状态列出策略实例
        
        Args:
            state: 状态 (running/paused/draft/archived)
        
        Returns:
            策略实例状态列表
        """
        instances = []
        for instance_id, data in self._db.items():
            if isinstance(data, dict) and data.get("state") == state:
                instances.append(StrategyInstanceState.from_dict(data))
        return instances
    
    def save_instance_state(self, state: StrategyInstanceState) -> dict:
        """保存策略实例状态
        
        Args:
            state: 策略实例状态对象
        
        Returns:
            保存结果
        """
        state.updated_at = time.time()
        self._db[state.id] = state.to_dict()
        return {"success": True, "id": state.id}
    
    def delete_instance(self, instance_id: str) -> dict:
        """删除策略实例
        
        Args:
            instance_id: 实例ID
        
        Returns:
            删除结果
        """
        if instance_id in self._db:
            del self._db[instance_id]
            return {"success": True}
        return {"success": False, "error": "Instance not found"}
    
    def save_all_from_manager(self, manager) -> int:
        """从策略管理器保存所有策略实例状态
        
        Args:
            manager: StrategyManager 实例
        
        Returns:
            保存的数量
        """
        count = 0
        for unit in manager.list_units():
            try:
                state = StrategyInstanceState(
                    id=unit.id,
                    logic_id=getattr(unit, 'STRATEGY_TYPE', 'custom'),
                    name=unit.name,
                    params=getattr(unit, 'params', {}),
                    state=unit.status.value,
                    upstream=unit.lineage.upstream[0].to_dict() if unit.lineage.upstream else {},
                    downstream=unit.lineage.downstream[0].to_dict() if unit.lineage.downstream else {},
                    processed_count=unit.state.processed_count,
                    error_count=unit.state.error_count,
                    last_error=unit.state.last_error,
                    last_error_ts=unit.state.last_error_ts,
                    last_process_ts=unit.state.last_process_ts,
                    created_at=unit.metadata.created_at,
                    updated_at=time.time(),
                )
                self.save_instance_state(state)
                count += 1
            except Exception as e:
                print(f"[StrategyInstanceDB] Save error for {unit.name}: {e}")
        return count


def initialize_strategy_logic_db() -> dict:
    """初始化策略逻辑数据库
    
    Returns:
        初始化结果
    """
    logic_db = StrategyLogicDB.get_instance()
    count = logic_db.initialize()
    
    return {
        "success": True,
        "initialized_count": count,
        "total_logics": len(logic_db.list_all()),
    }


def get_logic_db() -> StrategyLogicDB:
    """获取策略逻辑数据库实例"""
    return StrategyLogicDB.get_instance()


def get_instance_db() -> StrategyInstanceDB:
    """获取策略实例数据库实例"""
    return StrategyInstanceDB.get_instance()
