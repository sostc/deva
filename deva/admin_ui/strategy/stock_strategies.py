"""股票策略模块(Stock Strategies)

提供股票相关的策略实现，包括板块异动、涨跌停统计、板块排名等。

================================================================================
策略类型
================================================================================

【板块异动策略】
- BlockChangeStrategy: 计算板块在时间窗口内的涨跌幅

【涨跌停策略】
- LimitUpDownStrategy: 统计涨跌停股票数量

【板块排名策略】
- BlockRankingStrategy: 按涨跌幅对板块排序

【自定义筛选策略】
- CustomStockFilterStrategy: 应用自定义筛选条件
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import pandas as pd

from deva import NS, log

from .strategy_unit import (
    StrategyUnit,
    StrategyStatus,
    SchemaDefinition,
    DataSchema,
    OutputType,
)
from .utils import (
    format_pct,
    prepare_df,
    calc_block_ranking,
    get_top_stocks_in_block,
    build_block_change_html,
    build_limit_up_down_html,
    build_block_ranking_html,
)


STOCK_INPUT_SCHEMA = SchemaDefinition(fields=[
    DataSchema(name="code", type="str", description="股票代码"),
    DataSchema(name="name", type="str", description="股票名称"),
    DataSchema(name="price", type="float", description="当前价格"),
    DataSchema(name="volume", type="int", description="成交量"),
    DataSchema(name="amount", type="float", description="成交额"),
    DataSchema(name="time", type="datetime", description="时间戳"),
])


class StockStrategyUnit(StrategyUnit):
    """股票策略基类
    
    提供股票策略的通用功能，包括数据预处理、结果输出等。
    """
    
    def __init__(
        self,
        name: str,
        processor_func: Callable = None,
        description: str = "",
        tags: List[str] = None,
        window_seconds: int = 30,
        output_stream_name: str = None,
        auto_start: bool = False,
    ):
        super().__init__(
            name=name,
            processor_func=processor_func,
            description=description,
            tags=tags or ["stock"],
            input_schema=STOCK_INPUT_SCHEMA,
            auto_start=False,
        )
        
        self.window_seconds = window_seconds
        self._data_buffer: List[pd.DataFrame] = []
        self._buffer_lock = None
        
        if output_stream_name:
            self.connect_downstream(output_stream_name)
        
        if auto_start:
            self.start()
    
    def _ensure_buffer_lock(self):
        if self._buffer_lock is None:
            import threading
            self._buffer_lock = threading.Lock()
    
    def add_to_buffer(self, df: pd.DataFrame):
        self._ensure_buffer_lock()
        with self._buffer_lock:
            self._data_buffer.append(df)
            cutoff = datetime.now().timestamp() - self.window_seconds
            self._data_buffer = [
                d for d in self._data_buffer
                if hasattr(d, '_ts') and d._ts > cutoff
            ]
    
    def get_buffer_data(self) -> pd.DataFrame:
        self._ensure_buffer_lock()
        with self._buffer_lock:
            if not self._data_buffer:
                return pd.DataFrame()
            return pd.concat(self._data_buffer, ignore_index=True)
    
    def clear_buffer(self):
        self._ensure_buffer_lock()
        with self._buffer_lock:
            self._data_buffer.clear()


class BlockChangeStrategy(StockStrategyUnit):
    """板块异动策略
    
    计算板块在时间窗口内的涨跌幅，输出板块异动报告。
    """
    
    def __init__(
        self,
        name: str = "板块异动",
        window_seconds: int = 30,
        sample_n: int = 20,
        top_n: int = 5,
        output_stream_name: str = "block_change_output",
        **kwargs,
    ):
        self.sample_n = sample_n
        self.top_n = top_n
        
        super().__init__(
            name=name,
            description="计算板块在时间窗口内的涨跌幅",
            window_seconds=window_seconds,
            output_stream_name=output_stream_name,
            **kwargs,
        )
        
        self.set_processor(self._process)
    
    def _process(self, df: pd.DataFrame) -> Dict:
        if df is None or len(df) == 0:
            return {"success": False, "error": "No data"}
        
        try:
            prepared = prepare_df(df, ["code", "change", "name"])
            if prepared.empty:
                return {"success": False, "error": "No valid data after preparation"}
            
            html = build_block_change_html(
                prepared,
                top_n=self.top_n,
                sample_n=self.sample_n,
                col="change"
            )
            
            return {
                "success": True,
                "html": html,
                "data_count": len(prepared),
                "window_seconds": self.window_seconds,
                "ts": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "ts": datetime.now().isoformat(),
            }


class LimitUpDownStrategy(StockStrategyUnit):
    """涨跌停策略
    
    统计涨跌停股票数量，按板块分组展示。
    """
    
    def __init__(
        self,
        name: str = "涨跌停统计",
        threshold: float = 0.098,
        top_n: int = 5,
        output_stream_name: str = "limit_up_down_output",
        **kwargs,
    ):
        self.threshold = threshold
        self.top_n = top_n
        
        super().__init__(
            name=name,
            description="统计涨跌停股票数量",
            window_seconds=0,
            output_stream_name=output_stream_name,
            **kwargs,
        )
        
        self.set_processor(self._process)
    
    def _process(self, df: pd.DataFrame) -> Dict:
        if df is None or len(df) == 0:
            return {"success": False, "error": "No data"}
        
        try:
            html = build_limit_up_down_html(
                df,
                threshold=self.threshold,
                top_n=self.top_n
            )
            
            zt_count = int(df.query(f"p_change>{self.threshold}")["code"].nunique())
            dt_count = int(df.query(f"p_change<-{self.threshold}")["code"].nunique())
            
            return {
                "success": True,
                "html": html,
                "limit_up_count": zt_count,
                "limit_down_count": dt_count,
                "ts": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "ts": datetime.now().isoformat(),
            }


class BlockRankingStrategy(StockStrategyUnit):
    """板块排名策略
    
    按涨跌幅对板块排序，支持多种样本数量。
    """
    
    def __init__(
        self,
        name: str = "板块排名",
        sample_sizes: List[int] = None,
        top_n: int = 5,
        sample_n: int = 3,
        output_stream_name: str = "block_ranking_output",
        **kwargs,
    ):
        self.sample_sizes = sample_sizes or [20, 50]
        self.top_n = top_n
        self.sample_n = sample_n
        
        super().__init__(
            name=name,
            description="按涨跌幅对板块排序",
            window_seconds=0,
            output_stream_name=output_stream_name,
            **kwargs,
        )
        
        self.set_processor(self._process)
    
    def _process(self, df: pd.DataFrame) -> Dict:
        if df is None or len(df) == 0:
            return {"success": False, "error": "No data"}
        
        try:
            html = build_block_ranking_html(
                df,
                sample_sizes=self.sample_sizes,
                top_n=self.top_n,
                sample_n=self.sample_n,
                col="p_change"
            )
            
            return {
                "success": True,
                "html": html,
                "data_count": len(df),
                "sample_sizes": self.sample_sizes,
                "ts": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "ts": datetime.now().isoformat(),
            }


class CustomStockFilterStrategy(StockStrategyUnit):
    """自定义股票筛选策略
    
    应用自定义筛选条件，返回筛选结果。
    """
    
    def __init__(
        self,
        name: str = "自定义筛选",
        filter_func: Callable[[pd.DataFrame], pd.DataFrame] = None,
        filter_code: str = None,
        output_stream_name: str = "custom_filter_output",
        **kwargs,
    ):
        super().__init__(
            name=name,
            description="应用自定义筛选条件",
            window_seconds=0,
            output_stream_name=output_stream_name,
            **kwargs,
        )
        
        self._filter_func = filter_func
        
        if filter_code:
            self.set_filter_from_code(filter_code)
        
        if self._filter_func:
            self.set_processor(self._process)
    
    def set_filter_from_code(self, code: str):
        local_ns = {"pd": pd, "__builtins__": __builtins__}
        try:
            exec(code, local_ns, local_ns)
        except Exception as e:
            raise ValueError(f"Filter code execution error: {e}")
        
        func = local_ns.get("filter_stocks")
        if not callable(func):
            raise ValueError("No 'filter_stocks' function found in code")
        
        self._filter_func = func
        self.set_processor(self._process)
    
    def _process(self, df: pd.DataFrame) -> Dict:
        if df is None or len(df) == 0:
            return {"success": False, "error": "No data"}
        
        if not self._filter_func:
            return {"success": False, "error": "No filter function set"}
        
        try:
            result = self._filter_func(df)
            
            if not isinstance(result, pd.DataFrame):
                return {"success": False, "error": "Filter must return DataFrame"}
            
            return {
                "success": True,
                "data": result.to_dict(orient="records"),
                "count": len(result),
                "ts": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "ts": datetime.now().isoformat(),
            }


STRATEGY_REGISTRY = {
    "block_change": BlockChangeStrategy,
    "limit_up_down": LimitUpDownStrategy,
    "block_ranking": BlockRankingStrategy,
    "custom_filter": CustomStockFilterStrategy,
}


def create_stock_strategy(
    strategy_type: str,
    name: str = None,
    **kwargs,
) -> Optional[StockStrategyUnit]:
    """创建股票策略实例
    
    Args:
        strategy_type: 策略类型 (block_change/limit_up_down/block_ranking/custom_filter)
        name: 策略名称
        **kwargs: 策略参数
    
    Returns:
        策略实例
    """
    cls = STRATEGY_REGISTRY.get(strategy_type)
    if not cls:
        return None
    
    if name:
        kwargs["name"] = name
    
    return cls(**kwargs)


def list_available_strategies() -> List[Dict]:
    """列出所有可用的股票策略类型"""
    return [
        {
            "type": "block_change",
            "name": "板块异动策略",
            "description": "计算板块在时间窗口内的涨跌幅",
            "class": BlockChangeStrategy,
        },
        {
            "type": "limit_up_down",
            "name": "涨跌停策略",
            "description": "统计涨跌停股票数量",
            "class": LimitUpDownStrategy,
        },
        {
            "type": "block_ranking",
            "name": "板块排名策略",
            "description": "按涨跌幅对板块排序",
            "class": BlockRankingStrategy,
        },
        {
            "type": "custom_filter",
            "name": "自定义筛选策略",
            "description": "应用自定义筛选条件",
            "class": CustomStockFilterStrategy,
        },
    ]


def initialize_default_stock_strategies(
    auto_start: bool = False,
    register_to_manager: bool = True,
    datasource_name: str = "quant_source",
) -> Dict[str, StockStrategyUnit]:
    """初始化默认的股票策略
    
    Args:
        auto_start: 是否自动启动
        register_to_manager: 是否注册到管理器
        datasource_name: 关联的数据源名称，默认为 quant_source
    
    Returns:
        策略实例字典
    """
    from .strategy_manager import get_manager
    from .datasource import get_ds_manager
    
    strategies = {}
    
    strategies["block_change_30s"] = BlockChangeStrategy(
        name="板块异动_30秒",
        window_seconds=30,
        sample_n=20,
        top_n=5,
        output_stream_name="block_change_30s_output",
        auto_start=False,
    )
    
    strategies["block_change_1m"] = BlockChangeStrategy(
        name="板块异动_1分钟",
        window_seconds=60,
        sample_n=20,
        top_n=5,
        output_stream_name="block_change_1m_output",
        auto_start=False,
    )
    
    strategies["limit_up_down"] = LimitUpDownStrategy(
        name="涨跌停统计",
        threshold=0.098,
        top_n=5,
        output_stream_name="limit_up_down_output",
        auto_start=False,
    )
    
    strategies["block_ranking"] = BlockRankingStrategy(
        name="板块排名",
        sample_sizes=[20, 50],
        top_n=5,
        sample_n=3,
        output_stream_name="block_ranking_output",
        auto_start=False,
    )
    
    if register_to_manager:
        manager = get_manager()
        ds_mgr = get_ds_manager()
        source = ds_mgr.get_source_by_name(datasource_name)
        
        for name, strategy in strategies.items():
            manager.register(strategy)
            
            if source:
                ds_mgr.link_strategy(source.id, strategy.id)
                stream = source.get_stream()
                if stream:
                    strategy.set_input_stream(stream.filter(lambda x: x is not None))
                strategy.save()
    
    if auto_start:
        for strategy in strategies.values():
            strategy.start()
    
    return strategies
