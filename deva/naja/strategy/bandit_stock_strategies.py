"""
题材牛股精选策略 - 给 Bandit 提供交易信号

特点：
1. 题材联动分析
2. 个股精选排序
3. 噪音股票过滤
4. 早期发现牛股
5. 支持 LLM 参数调节
6. 模型持久化
7. HTML 可视化
8. Bandit 信号输出

数据源: realtime_tick_5s
字典: 通达信概念题材
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import pandas as pd
except Exception:
    pd = None

log = logging.getLogger(__name__)

from river import anomaly, compose, drift, linear_model, stats

from deva.naja.dictionary.tongdaxin_blocks import (
    get_stock_blocks,
    get_block_stocks,
    get_all_blocks,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


@dataclass
class NoiseConfig:
    """噪音过滤配置"""
    min_price: float = 1.0
    min_volume: float = 100000
    max_change: float = 20.0
    min_history: int = 3


class BlockStockSelector:
    """题材牛股精选器

    从题材中精选最强牛股，给 Bandit 提供买入信号
    """

    def __init__(
        self,
        top_n: int = 5,
        min_score: float = 0.5,
        min_price: float = 1.0,
        min_volume: float = 100000,
        min_change: float = 20.0,
        enable_block_filter: bool = True,
        block_min_stocks: int = 3,
    ):
        self._top_n = top_n
        self._min_score = min_score
        self._min_price = min_price
        self._min_volume = min_volume
        self._min_change = min_change
        self._enable_block_filter = enable_block_filter
        self._block_min_stocks = block_min_stocks

        self._stock_scores: Dict[str, float] = {}
        self._stock_details: Dict[str, Dict] = {}
        self._last_signal: Optional[Dict] = None
        self._price_history: Dict[str, List[float]] = {}
        self._volume_history: Dict[str, List[float]] = {}
        self._score_history: List[Dict] = []

    def on_data(self, data: Any) -> None:
        """处理数据"""
        if pd is None:
            return

        df = None
        if isinstance(data, dict) and "data" in data:
            df = data["data"]
        elif isinstance(data, pd.DataFrame):
            df = data

        if df is None or df.empty:
            return

        df_filtered = self._filter_noise(df)

        if len(df_filtered) < 1:
            return

        df_filtered = df_filtered.copy()

        if self._enable_block_filter:
            df_filtered["blocks"] = df_filtered.index.map(lambda x: get_stock_blocks(x))
            df_filtered["block_count"] = df_filtered["blocks"].apply(len)
            df_filtered = df_filtered[df_filtered["block_count"] >= 1]

        df_filtered = self._calculate_scores(df_filtered)

        df_sorted = df_filtered.sort_values("composite_score", ascending=False)
        top_stocks = df_sorted.head(self._top_n * 3)

        selected = []
        for code, row in top_stocks.iterrows():
            score = _safe_float(row.get("composite_score", 0))
            if score >= self._min_score:
                blocks = row.get("blocks", []) if self._enable_block_filter else get_stock_blocks(code)
                selected.append({
                    "stock_code": code,
                    "stock_name": row.get("name", code) if hasattr(row, "get") else str(code),
                    "price": _safe_float(row.get("now", 0)),
                    "change": _safe_float(row.get("p_change", 0)) * 100,
                    "volume": _safe_float(row.get("volume", 0)),
                    "score": score,
                    "blocks": blocks[:3] if blocks else [],
                    "momentum": _safe_float(row.get("momentum_score", 0)),
                    "strength": _safe_float(row.get("strength_score", 0)),
                })

                self._stock_details[code] = {
                    "score": score,
                    "change": _safe_float(row.get("p_change", 0)) * 100,
                    "volume": _safe_float(row.get("volume", 0)),
                    "blocks": blocks,
                }

            if len(selected) >= self._top_n:
                break

        self._stock_scores = dict(zip(df_sorted.index, df_sorted["composite_score"]))

        self._update_history(selected)

        best = selected[0] if selected else None
        if best:
            if best["change"] > 3:
                signal_type = "bull_strong_buy"
            elif best["change"] > 0:
                signal_type = "bull_buy"
            elif best["change"] > -3:
                signal_type = "bull_hold"
            else:
                signal_type = "bull_weak"

            self._last_signal = {
                "signal_type": signal_type,
                "score": best["score"],
                "direction": 1 if best["change"] > 0 else -1,
                "selected_stocks": selected,
                "best_stock": best,
                "html": "",
            }
        else:
            self._last_signal = {
                "signal_type": "bull_no_signal",
                "score": 0,
                "direction": 0,
                "selected_stocks": [],
                "best_stock": None,
                "html": "",
            }

    def _filter_noise(self, df: pd.DataFrame) -> pd.DataFrame:
        """过滤噪音股票"""
        result = df.copy()

        if "now" in result.columns:
            result = result[result["now"] >= self._min_price]

        if "volume" in result.columns:
            result = result[result["volume"] >= self._min_volume]

        if "p_change" in result.columns:
            result = result[result["p_change"].abs() <= self._min_change / 100]

        return result

    def _calculate_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算综合评分"""
        if df.empty:
            return df

        df["momentum_score"] = 0.0
        df["strength_score"] = 0.0
        df["block_score"] = 0.0
        df["composite_score"] = 0.0

        if "p_change" in df.columns:
            changes = pd.to_numeric(df["p_change"], errors="coerce").fillna(0) * 100
            momentum = (changes - changes.min()) / (changes.max() - changes.min() + 0.001)
            df["momentum_score"] = momentum

        if "volume" in df.columns:
            volumes = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
            strength = (volumes - volumes.min()) / (volumes.max() - volumes.min() + 0.001)
            df["strength_score"] = strength

        if self._enable_block_filter and "block_count" in df.columns:
            df["block_score"] = df["block_count"] / df["block_count"].max() if df["block_count"].max() > 0 else 0

        df["composite_score"] = (
            df["momentum_score"] * 0.5 +
            df["strength_score"] * 0.3 +
            df["block_score"] * 0.2
        )

        return df

    def _update_history(self, selected: List[Dict]) -> None:
        """更新历史"""
        self._score_history.append({
            "timestamp": time.time(),
            "selected": selected,
            "top_score": selected[0]["score"] if selected else 0,
        })

        if len(self._score_history) > 50:
            self._score_history.pop(0)

    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        if not self._last_signal:
            return None

        signal = dict(self._last_signal)
        signal["html"] = self._generate_html(signal)
        return signal

    def _generate_html(self, signal: Dict) -> str:
        """生成 HTML"""
        selected = signal.get("selected_stocks", [])
        best = signal.get("best_stock", {})

        if not selected:
            return '''
<div style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);border-radius:16px;padding:16px;color:#fff;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;margin-bottom:8px;">🐂 题材牛股精选</div>
    <div style="padding:20px;text-align:center;color:rgba(255,255,255,0.7);">暂无符合条件的股票</div>
</div>
'''

        rows = []
        for s in selected[:5]:
            change = s.get("change", 0)
            change_color = "#22c55e" if change > 0 else "#ef4444"
            block_str = ",".join(s.get("blocks", [])[:2]) if s.get("blocks") else "题材未知"

            rows.append(f'''
<tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
    <td style="padding:8px;font-weight:600;">{s.get("stock_code","")}</td>
    <td style="padding:8px;">{str(s.get("stock_name",""))[:6]}</td>
    <td style="padding:8px;color:{change_color};">{change:+.2f}%</td>
    <td style="padding:8px;">{s.get("score",0):.2f}</td>
</tr>
''')

        best_change = best.get("change", 0)
        best_color = "#22c55e" if best_change > 0 else "#ef4444"

        html = f'''
<div style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);border-radius:16px;padding:16px;color:#fff;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;margin-bottom:8px;">🐂 题材牛股精选 TOP{len(selected)}</div>

    <div style="background:rgba(255,255,255,0.1);border-radius:12px;padding:12px;margin-bottom:12px;">
        <div style="font-size:12px;opacity:0.7;margin-bottom:4px;">最佳标的</div>
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="font-size:18px;font-weight:700;">{best.get("stock_code","")}</div>
                <div style="font-size:12px;opacity:0.7;">{str(best.get("stock_name",""))[:10]}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:20px;font-weight:700;color:{best_color};">{best_change:+.2f}%</div>
                <div style="font-size:12px;opacity:0.7;">评分 {best.get("score",0):.2f}</div>
            </div>
        </div>
    </div>

    <table style="width:100%;font-size:12px;">
        <tr style="color:rgba(255,255,255,0.7);border-bottom:1px solid rgba(255,255,255,0.2);">
            <th style="padding:8px;text-align:left;">代码</th>
            <th style="padding:8px;text-align:left;">名称</th>
            <th style="padding:8px;text-align:right;">涨跌</th>
            <th style="padding:8px;text-align:right;">评分</th>
        </tr>
        {''.join(rows)}
    </table>
</div>
'''
        return html

    def update_params(self, params: Dict) -> None:
        """更新参数"""
        self._top_n = params.get("top_n", self._top_n)
        self._min_score = params.get("min_score", self._min_score)
        self._min_price = params.get("min_price", self._min_price)
        self._min_volume = params.get("min_volume", self._min_volume)
        self._enable_block_filter = params.get("enable_block_filter", self._enable_block_filter)
        self._block_min_stocks = params.get("block_min_stocks", self._block_min_stocks)

    def get_state(self) -> Dict:
        """获取状态"""
        return {
            "stock_scores": self._stock_scores,
            "top_n": self._top_n,
        }

    def set_state(self, state: Dict) -> None:
        """设置状态"""
        if "top_n" in state:
            self._top_n = state["top_n"]


class EarlyBullFinder:
    """早期牛股发现器

    专门发现刚开始启动的牛股，在早期介入
    """

    def __init__(
        self,
        rise_threshold: float = 2.0,
        volume_boost: float = 1.5,
        momentum_window: int = 5,
    ):
        self._rise_threshold = rise_threshold
        self._volume_boost = volume_boost
        self._momentum_window = momentum_window

        self._stock_history: Dict[str, List[Dict]] = {}
        self._last_signal: Optional[Dict] = None

    def on_data(self, data: Any) -> None:
        """处理数据"""
        if pd is None:
            return

        df = None
        if isinstance(data, dict) and "data" in data:
            df = data["data"]
        elif isinstance(data, pd.DataFrame):
            df = data

        if df is None or df.empty:
            log.debug(f"[EarlyBullFinder] 数据为空，跳过")
            return

        log.debug(f"[EarlyBullFinder] on_data: 收到 {len(df)} 行数据, columns={list(df.columns)[:10]}")
        
        candidates = []
        total_processed = 0
        total_filtered = 0
        total_accumulated = 0

        for code in df.index:
            row = df.loc[code]

            price = _safe_float(row.get("now", 0))
            change = _safe_float(row.get("p_change", 0)) * 100
            volume = _safe_float(row.get("volume", 0))
            total_processed += 1

            if price < 1 or volume < 50000:
                total_filtered += 1
                if total_filtered <= 3:  # 只记录前3个
                    log.debug(f"[EarlyBullFinder] {code} 过滤: price={price:.2f}, volume={volume:.0f}")
                continue

            history = self._stock_history.setdefault(code, [])
            old_len = len(history)
            history.append({
                "timestamp": time.time(),
                "price": price,
                "change": change,
                "volume": volume,
            })

            if len(history) > self._momentum_window:
                history.pop(0)

            if old_len < 3 and len(history) >= 3:
                log.info(f"[EarlyBullFinder] 🎉 {code} 历史数据积累完成! now={len(history)}, price={price:.2f}, change={change:.2f}%")
            
            if len(history) <= 3:
                total_accumulated += 1
                if total_accumulated <= 5:  # 只记录前5个
                    log.debug(f"[EarlyBullFinder] {code} 积累中: history_count={len(history)}, price={price:.2f}, change={change:.2f}%")

            if len(history) < 3:
                continue

            recent_changes = [h["change"] for h in history[-3:]]
            avg_change = sum(recent_changes) / len(recent_changes)

            if recent_changes[-1] > self._rise_threshold:
                volume_ratio = volume / (sum(h["volume"] for h in history[-3:]) / 3)

                if volume_ratio > self._volume_boost or avg_change > 5:
                    blocks = get_stock_blocks(code)
                    candidates.append({
                        "stock_code": code,
                        "stock_name": row.get("name", code) if hasattr(row, "get") else str(code),
                        "price": price,
                        "change": change,
                        "volume": volume,
                        "volume_ratio": volume_ratio,
                        "momentum_score": avg_change * volume_ratio,
                        "blocks": blocks,
                    })

        log.debug(f"[EarlyBullFinder] 处理完成: total={total_processed}, filtered={total_filtered}, accumulated={total_accumulated}, candidates={len(candidates)}")
        if candidates:
            log.info(f"[EarlyBullFinder] 🔥 产生 {len(candidates)} 个候选股: {[(c['stock_code'], c['change'], c['volume_ratio']) for c in candidates[:3]]}")

        candidates.sort(key=lambda x: x["momentum_score"], reverse=True)

        if candidates:
            best = candidates[0]
            if best["change"] > 5:
                signal_type = "early_bull_strong"
            elif best["change"] > 3:
                signal_type = "early_bull_confirm"
            else:
                signal_type = "early_bull_start"

            self._last_signal = {
                "signal_type": signal_type,
                "score": min(1.0, best["momentum_score"] / 10),
                "direction": 1,
                "candidates": candidates[:3],
                "best_stock": best,
                "html": "",
            }
        else:
            self._last_signal = {
                "signal_type": "early_bull_none",
                "score": 0,
                "direction": 0,
                "candidates": [],
                "best_stock": None,
                "html": "",
            }

    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        if not self._last_signal:
            return None

        signal = dict(self._last_signal)
        signal["html"] = self._generate_html(signal)
        return signal

    def _generate_html(self, signal: Dict) -> str:
        """生成 HTML"""
        candidates = signal.get("candidates", [])
        best = signal.get("best_stock", {})

        if not candidates:
            return '''
<div style="background:linear-gradient(135deg,#7c3aed,#a855f7);border-radius:16px;padding:16px;color:#fff;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;margin-bottom:8px;">🚀 早期牛股发现</div>
    <div style="padding:20px;text-align:center;color:rgba(255,255,255,0.7);">暂无早期信号</div>
</div>
'''

        rows = []
        for c in candidates:
            change = c.get("change", 0)
            color = "#22c55e" if change > 0 else "#ef4444"
            rows.append(f'''
<tr>
    <td style="padding:6px;font-weight:600;">{c.get("stock_code","")}</td>
    <td style="padding:6px;color:{color};">{change:+.2f}%</td>
    <td style="padding:6px;">{c.get("volume_ratio",0):.1f}x</td>
</tr>
''')

        html = f'''
<div style="background:linear-gradient(135deg,#7c3aed,#a855f7);border-radius:16px;padding:16px;color:#fff;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;margin-bottom:8px;">🚀 早期牛股发现</div>

    <div style="background:rgba(255,255,255,0.1);border-radius:12px;padding:12px;margin-bottom:12px;">
        <div style="font-size:12px;opacity:0.7;">最佳早期信号</div>
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="font-size:20px;font-weight:700;">{best.get("stock_code","")}</div>
                <div style="font-size:12px;opacity:0.7;">{str(best.get("stock_name",""))[:10]}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:24px;font-weight:700;color:#22c55e;">{best.get("change",0):+.2f}%</div>
                <div style="font-size:12px;opacity:0.7;">量比 {best.get("volume_ratio",0):.1f}x</div>
            </div>
        </div>
    </div>

    <table style="width:100%;font-size:12px;">
        <tr style="color:rgba(255,255,255,0.7);">
            <th style="padding:6px;text-align:left;">股票</th>
            <th style="padding:6px;text-align:right;">涨幅</th>
            <th style="padding:6px;text-align:right;">量比</th>
        </tr>
        {''.join(rows)}
    </table>
</div>
'''
        return html

    def update_params(self, params: Dict) -> None:
        """更新参数"""
        self._rise_threshold = params.get("rise_threshold", self._rise_threshold)
        self._volume_boost = params.get("volume_boost", self._volume_boost)
        self._momentum_window = params.get("momentum_window", self._momentum_window)


SELECTOR_REGISTRY = {
    "block_stock_selector": BlockStockSelector,
    "early_bull": EarlyBullFinder,
}


def get_selector(name: str, **kwargs) -> Optional[Any]:
    """获取选择器实例"""
    cls = SELECTOR_REGISTRY.get(name)
    if cls:
        return cls(**kwargs)
    return None
