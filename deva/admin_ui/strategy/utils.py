"""通用工具模块(Utils Module)

提供策略、数据源、股票等模块的公共工具函数。

================================================================================
功能列表
================================================================================

【数据格式化】
- format_pct: 格式化百分比显示
- format_duration: 格式化时长显示
- df_to_html: DataFrame 转 HTML 表格

【数据处理】
- prepare_df: 数据预处理（选择列、添加元数据、展开板块）
- calc_block_ranking: 计算板块排名
- get_top_stocks_in_block: 获取板块内股票

【样式定义】
- TABLE_STYLE: 表格 CSS 样式
"""

from __future__ import annotations

import threading
from typing import List, Optional
import pandas as pd


TABLE_STYLE = """
<style>
.df-table{width:100%;border-collapse:collapse;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:13px;margin:8px 0;}
.df-table th,.df-table td{padding:6px 10px;text-align:left;border-bottom:1px solid #e5e7eb;}
.df-table th{background:#f1f5f9;font-weight:600;color:#475569;}
.df-table tr:hover{background:#f8fafc;}
.df-table td{color:#334155;}
.up{color:#e53935;font-weight:500;}
.down{color:#43a047;font-weight:500;}
</style>
"""

_TABLE_STYLE_ADDED = False
_table_style_lock = threading.Lock()


def format_pct(val) -> str:
    """格式化百分比显示
    
    Args:
        val: 数值（小数形式，如 0.05 表示 5%）
    
    Returns:
        格式化后的 HTML 字符串，涨跌用不同颜色标识
    """
    if not isinstance(val, (int, float)):
        return str(val)
    pct = val * 100
    if val > 0:
        return f"<span class='up'>+{pct:.2f}%</span>"
    elif val < 0:
        return f"<span class='down'>{pct:.2f}%</span>"
    return f"{pct:.2f}%"


def format_duration(seconds: float) -> str:
    """格式化时长显示
    
    Args:
        seconds: 秒数
    
    Returns:
        人类可读的时长字符串
    """
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds / 60)}分钟"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}小时"
    else:
        return f"{int(seconds / 86400)}天"


def df_to_html(df: pd.DataFrame, index: bool = False, title: str = None) -> str:
    """DataFrame 转 HTML 表格
    
    Args:
        df: DataFrame
        index: 是否包含索引
        title: 可选标题
    
    Returns:
        HTML 字符串
    """
    global _TABLE_STYLE_ADDED
    if df is None or len(df) == 0:
        return "<p>暂无数据</p>"
    html = df.to_html(index=index, classes="df-table", border=0)
    html = " ".join(html.split())
    if title:
        html = f"<h4>{title}</h4>" + html
    with _table_style_lock:
        if not _TABLE_STYLE_ADDED:
            html = TABLE_STYLE + html
            _TABLE_STYLE_ADDED = True
    return html


def ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    """确保 DataFrame 包含必需列
    
    Args:
        df: 原始 DataFrame
    
    Returns:
        添加必需列后的 DataFrame
    """
    out = df.copy()
    if "blockname" not in out.columns:
        out["blockname"] = "unknown"
    if "name" not in out.columns:
        out["name"] = out["code"].astype(str) if "code" in out.columns else "unknown"
    return out


def enrich_with_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """添加元数据（股票名称、板块等）
    
    Args:
        df: 原始 DataFrame
    
    Returns:
        添加元数据后的 DataFrame
    """
    try:
        from .data import Stock
        return Stock.render(df)
    except Exception:
        return df


def expand_blockname_rows(
    df: pd.DataFrame, 
    block_col: str = "blockname", 
    target_col: str = "blockname_item"
) -> pd.DataFrame:
    """展开板块名称行
    
    将 "军工|国家安防" 这样的多板块字符串展开为多行。
    
    Args:
        df: 原始 DataFrame
        block_col: 板块列名
        target_col: 目标列名
    
    Returns:
        展开后的 DataFrame
    """
    if df is None:
        return pd.DataFrame(columns=[block_col, target_col])
    if len(df) == 0:
        out = df.copy()
        if target_col not in out.columns:
            out[target_col] = []
        return out

    out = df.copy()
    if block_col not in out.columns:
        out[block_col] = "unknown"

    out[block_col] = out[block_col].fillna("unknown").astype(str)
    out[target_col] = out[block_col].map(
        lambda x: [item.strip() for item in x.split("|") if item and item.strip()] or ["unknown"]
    )
    out = out.explode(target_col, ignore_index=True)
    return out


def prepare_df(df: pd.DataFrame, cols: List[str] = None) -> pd.DataFrame:
    """数据预处理
    
    完整的数据预处理流程：选择列 → 添加元数据 → 确保必需列 → 展开板块
    
    Args:
        df: 原始 DataFrame
        cols: 需要选择的列，None 表示选择全部
    
    Returns:
        预处理后的 DataFrame
    """
    if df is None or len(df) == 0:
        return pd.DataFrame()
    
    if cols:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        df = df[cols].copy()
    else:
        df = df.copy()
    
    df = ensure_required_columns(enrich_with_metadata(df))
    df = expand_blockname_rows(df)
    return df


def calc_block_ranking(
    df: pd.DataFrame, 
    col: str, 
    n: int = 20, 
    top: bool = True
) -> pd.DataFrame:
    """计算板块排名
    
    按指定列排序，每个板块取前 n 只股票，计算平均涨跌幅，返回 TOP 10。
    
    Args:
        df: 预处理后的 DataFrame（需包含 blockname_item 列）
        col: 排序依据的列名
        n: 每个板块取样的股票数量
        top: True 取涨幅最大，False 取跌幅最大
    
    Returns:
        排名结果 DataFrame
    """
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


def get_top_stocks_in_block(
    df: pd.DataFrame, 
    blockname: str, 
    col: str, 
    n: int = 3, 
    top: bool = True
) -> pd.DataFrame:
    """获取板块内股票
    
    获取指定板块内按指定列排序的前 n 只股票。
    
    Args:
        df: 预处理后的 DataFrame（需包含 blockname_item 列）
        blockname: 板块名称
        col: 排序依据的列名
        n: 返回的股票数量
        top: True 取涨幅最大，False 取跌幅最大
    
    Returns:
        股票 DataFrame
    """
    block_df = df[df["blockname_item"] == blockname].copy()
    block_df = block_df.sort_values(col, ascending=not top).head(n)
    return block_df


def build_block_detail_html(
    group: pd.DataFrame,
    df: pd.DataFrame,
    top: bool = True,
    col: str = "change",
    top_n: int = 5,
    sample_n: int = 3
) -> str:
    """构建板块详情 HTML
    
    Args:
        group: 板块排名结果
        df: 预处理后的 DataFrame
        top: True 为涨幅，False 为跌幅
        col: 数据列名
        top_n: 返回的板块数量
        sample_n: 每个板块取样的股票数量
    
    Returns:
        HTML 字符串
    """
    parts = []
    for blockname in group.index[:top_n]:
        stocks = get_top_stocks_in_block(df, blockname, col, n=sample_n, top=top)
        if len(stocks) > 0:
            stock_info = ", ".join([
                f"{row['name']}({format_pct(row[col])})"
                for _, row in stocks.iterrows()
            ])
            avg = group.loc[blockname, col]
            parts.append(f"<b>{blockname}</b>({format_pct(avg)}): {stock_info}")
    return "<br>".join(parts) if parts else "暂无数据"


def build_block_change_html(
    df: pd.DataFrame,
    top_n: int = 5,
    sample_n: int = 3,
    col: str = "change"
) -> str:
    """构建板块异动 HTML
    
    Args:
        df: 预处理后的 DataFrame
        top_n: 返回的板块数量
        sample_n: 每个板块取样的股票数量
        col: 数据列名
    
    Returns:
        HTML 字符串
    """
    max_group = calc_block_ranking(df, col, n=sample_n, top=True)
    min_group = calc_block_ranking(df, col, n=sample_n, top=False)
    
    up_detail = build_block_detail_html(max_group, df, top=True, col=col, top_n=top_n, sample_n=sample_n)
    down_detail = build_block_detail_html(min_group, df, top=False, col=col, top_n=top_n, sample_n=sample_n)
    
    html = f"""
    <h4>板块异动-涨幅TOP{top_n}</h4>
    <div style='padding:8px;background:#fff5f5;border-radius:6px;margin:4px 0;'>{up_detail}</div>
    <h4>板块异动-跌幅TOP{top_n}</h4>
    <div style='padding:8px;background:#f0fff4;border-radius:6px;margin:4px 0;'>{down_detail}</div>
    """
    return html


def build_limit_up_down_html(
    df: pd.DataFrame,
    threshold: float = 0.098,
    top_n: int = 5
) -> str:
    """构建涨跌停 HTML
    
    Args:
        df: 原始 DataFrame
        threshold: 涨跌停阈值
        top_n: 每个板块显示的股票数量
    
    Returns:
        HTML 字符串
    """
    zt_raw = df.query(f"p_change>{threshold}")[["code", "p_change"]]
    dt_raw = df.query(f"p_change<-{threshold}")[["code", "p_change"]]
    
    zt_df = prepare_df(zt_raw, ["code", "p_change"])
    dt_df = prepare_df(dt_raw, ["code", "p_change"])
    
    zt_count = int(df.query(f"p_change>{threshold}")["code"].nunique())
    dt_count = int(df.query(f"p_change<-{threshold}")["code"].nunique())
    
    def build_stock_list(stock_df: pd.DataFrame, top: bool = True) -> str:
        if len(stock_df) == 0:
            return "暂无数据"
        grouped = stock_df.groupby("blockname_item").apply(
            lambda g: ", ".join([
                f"{row['name']}({format_pct(row['p_change'])})"
                for _, row in g.sort_values("p_change", ascending=not top).head(top_n).iterrows()
            ])
        )
        parts = [f"<b>{block}</b>: {stocks}" for block, stocks in grouped.head(10).items()]
        return "<br>".join(parts)
    
    zt_html = f"<h4>涨停 {zt_count} 只</h4><div style='padding:8px;background:#fff5f5;border-radius:6px;margin:4px 0;'>{build_stock_list(zt_df, top=True)}</div>"
    dt_html = f"<h4>跌停 {dt_count} 只</h4><div style='padding:8px;background:#f0fff4;border-radius:6px;margin:4px 0;'>{build_stock_list(dt_df, top=False)}</div>"
    
    return zt_html + dt_html


def build_block_ranking_html(
    df: pd.DataFrame,
    sample_sizes: List[int] = None,
    top_n: int = 5,
    sample_n: int = 3,
    col: str = "p_change"
) -> str:
    """构建板块排名 HTML
    
    Args:
        df: 预处理后的 DataFrame
        sample_sizes: 样本数量列表
        top_n: 返回的板块数量
        sample_n: 每个板块取样的股票数量
        col: 数据列名
    
    Returns:
        HTML 字符串
    """
    if sample_sizes is None:
        sample_sizes = [20, 50]
    
    df = prepare_df(df, ["code", col, "name"])
    if df.empty:
        return "<p>暂无有效数据</p>"
    
    parts = []
    for n in sample_sizes:
        max_g = calc_block_ranking(df, col, n=n, top=True)
        min_g = calc_block_ranking(df, col, n=n, top=False)
        
        up_html = f"<h4>领涨板块TOP{top_n} (样本{n}只)</h4><div style='padding:8px;background:#fff5f5;border-radius:6px;margin:4px 0;'>{build_block_detail_html(max_g, df, top=True, col=col, top_n=top_n, sample_n=sample_n)}</div>"
        down_html = f"<h4>领跌板块TOP{top_n} (样本{n}只)</h4><div style='padding:8px;background:#f0fff4;border-radius:6px;margin:4px 0;'>{build_block_detail_html(min_g, df, top=False, col=col, top_n=top_n, sample_n=sample_n)}</div>"
        parts.extend([up_html, down_html])
    
    return "".join(parts)
