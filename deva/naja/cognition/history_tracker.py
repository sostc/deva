"""
注意力历史追踪系统

追踪注意力随时间的变化，包括：
- 板块注意力的变化趋势
- 个股注意力的变化趋势
- 注意力转移检测
- 注意力加强/减弱检测
"""

import time
import os
from typing import Dict, List, Optional, Any
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime


def _lab_debug_log(msg: str):
    """实验室模式调试日志"""
    if os.environ.get("NAJA_LAB_DEBUG") == "true":
        import logging
        logging.getLogger(__name__).info(f"[Lab-Debug] {msg}")


@dataclass
class AttentionSnapshot:
    """注意力快照"""
    timestamp: float
    global_attention: float
    sector_weights: Dict[str, float]
    symbol_weights: Dict[str, float]
    symbol_market_data: Dict[str, Dict] = field(default_factory=dict)
    market_time_str: str = ""  # 行情时间字符串（如 "2024-01-15 10:30:00"）
    activity: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
            'market_time_str': self.market_time_str,
            'global_attention': self.global_attention,
            'sector_weights': self.sector_weights,
            'symbol_weights': self.symbol_weights,
            'symbol_market_data': self.symbol_market_data,
            'activity': self.activity,
        }


@dataclass
class AttentionChange:
    """注意力变化记录"""
    timestamp: float
    change_type: str  # 'sector_shift', 'symbol_shift', 'strengthen', 'weaken', 'new_hot', 'cooled'
    item_type: str  # 'sector' | 'symbol'
    item_id: str
    item_name: str
    old_weight: float
    new_weight: float
    change_percent: float
    description: str
    related_symbols: List[Dict] = field(default_factory=list)
    market_time: str = ""
    price: float = 0.0
    price_change: float = 0.0
    volume: float = 0.0
    sector: str = ""


@dataclass
class SectorHotspotEvent:
    """板块热点切换事件"""
    timestamp: float
    market_time: str
    market_date: str
    sector_id: str
    sector_name: str
    event_type: str  # 'rise', 'fall', 'new_hot', 'cooled'
    weight_change: float
    change_percent: float
    top_symbols: List[Dict]  # 板块内涨跌最多的个股
    description: str


class AttentionHistoryTracker:
    """
    注意力历史追踪器
    
    功能：
    1. 保存注意力历史快照
    2. 检测注意力变化
    3. 追踪热门板块/股票的变迁
    4. 生成变化报告
    """
    
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.snapshots: deque = deque(maxlen=max_history)
        self.changes: deque = deque(maxlen=max_history * 2)
        
        # 板块热点切换事件记录 - 多阈值支持
        # 不同敏感度的事件分别存储
        self.sector_hotspot_events_low: deque = deque(maxlen=50)      # 低阈值 (3%)
        self.sector_hotspot_events_medium: deque = deque(maxlen=50)   # 中阈值 (5%)
        self.sector_hotspot_events_high: deque = deque(maxlen=50)     # 高阈值 (10%)
        # 保留旧接口兼容
        self.sector_hotspot_events = self.sector_hotspot_events_medium
        
        # 当前热门记录
        self.current_hot_sectors: Dict[str, float] = {}
        self.current_hot_symbols: Dict[str, float] = {}

        # 历史热门记录（用于检测变迁）
        self.sector_history: Dict[str, List[Dict]] = {}
        self.symbol_history: Dict[str, List[Dict]] = {}

        # 股票代码到名称的映射
        self.symbol_names: Dict[str, str] = {}
        # 板块ID到名称的映射
        self.sector_names: Dict[str, str] = {}
        # 板块配置引用（用于查找名称）
        self._sector_configs: Dict[str, Any] = {}

        # 个股到板块的映射（简化版）
        self.symbol_to_sector: Dict[str, str] = {}

        # 当前市场注意力状态（用于UI展示）
        self.current_market_state: str = "unknown"  # 'active', 'moderate', 'quiet', 'very_quiet'
        self.current_market_state_description: str = "等待数据..."
        self.last_update_time: float = 0
        self.current_market_time_str: str = ""  # 行情时间字符串（如 "2024-01-15 10:30:00"）

        # 事件桥接与节流
        self._emit_last: Dict[str, float] = {}
        self._emit_cooldown_seconds: float = 30.0

        # 宏观变化阈值
        self._activity_shift_threshold: float = 0.2
        self._concentration_shift_threshold: float = 0.2
    
    def register_symbol_name(self, symbol: str, name: str):
        """注册股票名称"""
        self.symbol_names[symbol] = name
    
    def register_sector_name(self, sector_id: str, name: str):
        """注册板块名称"""
        self.sector_names[sector_id] = name

    def register_sectors(self, sectors: List):
        """批量注册板块配置（用于初始化）"""
        for sector in sectors:
            if hasattr(sector, 'sector_id') and hasattr(sector, 'name'):
                self.sector_names[sector.sector_id] = sector.name
                self._sector_configs[sector.sector_id] = sector
    
    def get_symbol_name(self, symbol: str) -> str:
        """获取股票名称"""
        return self.symbol_names.get(symbol, symbol)

    def get_symbol_sector(self, symbol: str) -> str:
        """获取股票所属板块"""
        if self.snapshots:
            latest = self.snapshots[-1]
            market_data = latest.symbol_market_data.get(symbol, {})
            sector = market_data.get('sector', '')
            if sector:
                return sector

        return self.symbol_to_sector.get(symbol, '')

    def get_symbol_sector_name(self, symbol: str) -> str:
        """获取股票所属板块名称（带板块名翻译）"""
        sector_id = self.get_symbol_sector(symbol)
        if not sector_id:
            return ''
        return self.get_sector_name(sector_id)

    def register_symbol_sector(self, symbol: str, sector_id: str):
        """注册个股-板块映射"""
        if sector_id:
            self.symbol_to_sector[symbol] = sector_id

    def get_symbol_change(self, symbol: str) -> float:
        """获取股票涨跌幅"""
        if self.snapshots:
            latest = self.snapshots[-1]
            market_data = latest.symbol_market_data.get(symbol, {})
            return market_data.get('change')
        return None

    def get_sector_name(self, sector_id: str) -> str:
        """获取板块名称"""
        if not sector_id:
            return ""

        if sector_id in self.sector_names:
            return self.sector_names[sector_id]
        if sector_id in self._sector_configs:
            return self._sector_configs[sector_id].name

        if sector_id.startswith("block_") and len(sector_id) > 10:
            return ""

        return sector_id

    def _format_volume(self, volume: float) -> str:
        """格式化成交量显示"""
        if volume >= 1e8:
            return f"{volume / 1e8:.1f}亿"
        elif volume >= 1e4:
            return f"{volume / 1e4:.1f}万"
        else:
            return f"{volume:.0f}"

    def _should_emit(self, key: str, now_ts: float) -> bool:
        last_ts = self._emit_last.get(key, 0.0)
        if now_ts - last_ts < self._emit_cooldown_seconds:
            return False
        self._emit_last[key] = now_ts
        return True

    def _emit_attention_event(
        self,
        *,
        event_type: str,
        title: str,
        content: str,
        score: float,
        payload: Optional[Dict[str, Any]] = None,
        symbol: str = "",
        sector: str = "",
        market_time: str = "",
    ) -> None:
        now_ts = time.time()
        key = f"{event_type}:{symbol or sector or 'global'}"
        if not self._should_emit(key, now_ts):
            return
        self._emit_to_insight_pool(
            event_type=event_type,
            title=title,
            content=content,
            score=score,
            payload=payload or {},
            symbol=symbol,
            sector=sector,
            market_time=market_time,
            timestamp=now_ts,
        )
        self._emit_to_memory(
            timestamp=now_ts,
            title=title,
            content=content,
            payload=payload or {},
            symbol=symbol,
            sector=sector,
            market_time=market_time,
        )

    def _emit_to_memory(
        self,
        *,
        timestamp: float,
        title: str,
        content: str,
        payload: Dict[str, Any],
        symbol: str = "",
        sector: str = "",
        market_time: str = "",
    ) -> None:
        try:
            from deva.naja.memory import get_memory_engine
        except Exception:
            return
        try:
            memory = get_memory_engine()
            record = {
                "timestamp": timestamp,
                "source": "attention:history_tracker",
                "title": title,
                "content": content,
                "symbol": symbol,
                "sector": sector,
                "market_time": market_time,
                "payload": payload,
                "importance": "high",
            }
            memory.process_record(record)
        except Exception:
            return

    def _emit_to_insight_pool(
        self,
        *,
        event_type: str,
        title: str,
        content: str,
        score: float,
        payload: Dict[str, Any],
        symbol: str = "",
        sector: str = "",
        market_time: str = "",
        timestamp: float = None,
    ) -> None:
        try:
            from deva.naja.insight import get_insight_pool
        except Exception:
            return
        try:
            pool = get_insight_pool()
            ts = timestamp if timestamp is not None else time.time()
            pool.ingest_attention_event(
                {
                    "theme": title,
                    "summary": content,
                    "symbols": [symbol] if symbol else [],
                    "sectors": [sector] if sector else [],
                    "confidence": 0.7,
                    "actionability": 0.5,
                    "system_attention": score,
                    "source": "attention",
                    "signal_type": event_type,
                    "ts": ts,
                    "payload": {**payload, "market_time": market_time} if market_time else payload,
                }
            )
        except Exception:
            return

    def record_snapshot(self, global_attention: float,
                       sector_weights: Dict[str, float],
                       symbol_weights: Dict[str, float],
                       timestamp: float = None,
                       timestamp_str: str = None,
                       symbol_market_data: Dict[str, Dict] = None,
                       activity: float = None):
        """
        记录注意力快照

        Args:
            global_attention: 全局注意力
            sector_weights: 板块权重字典
            symbol_weights: 个股权重字典
            timestamp: 时间戳（优先使用行情数据时间）
            timestamp_str: 时间字符串（用于日志显示）
            symbol_market_data: 个股行情数据字典 {symbol: {'price': float, 'change': float, 'volume': float, 'sector': str}}
            activity: 市场活跃度
        """
        import logging
        log = logging.getLogger(__name__)

        actual_timestamp = timestamp if timestamp is not None else time.time()
        market_data = symbol_market_data if symbol_market_data else {}
        actual_activity = activity if activity is not None else 0.5
        prev_state = self.current_market_state
        prev_attention = self.snapshots[-1].global_attention if self.snapshots else None

        snapshot = AttentionSnapshot(
            timestamp=actual_timestamp,
            global_attention=global_attention,
            sector_weights=sector_weights.copy(),
            symbol_weights=symbol_weights.copy(),
            symbol_market_data=market_data.copy(),
            market_time_str=timestamp_str or "",
            activity=actual_activity,
        )

        # 检测注意力变化
        if self.snapshots:
            last_snapshot = self.snapshots[-1]

            # 调试日志
            if len(self.snapshots) <= 2:
                sample_items = list(sector_weights.items())[:3]
                sample_named = {self.get_sector_name(k): v for k, v in sample_items}
                _lab_debug_log(f"快照{len(self.snapshots)+1}: sector_weights样本={sample_named}")

            self._detect_changes(last_snapshot, snapshot, timestamp_str)
        
        self.snapshots.append(snapshot)
        
        # 更新当前热门
        self.current_hot_sectors = dict(sorted(
            sector_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10])

        self.current_hot_symbols = dict(sorted(
            symbol_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20])

        # 更新市场注意力状态
        self._update_market_state(global_attention, actual_activity, sector_weights, symbol_weights, actual_timestamp)

        # 更新行情时间
        self.current_market_time_str = timestamp_str or ""

        # 全局注意力变化事件
        if prev_attention is not None:
            delta = global_attention - prev_attention
            if abs(delta) >= 0.2:
                direction = "提升" if delta > 0 else "回落"
                title = "注意力强度变化"
                content = f"全局注意力{direction}: {prev_attention:.2f} → {global_attention:.2f}"
                payload = {
                    "old_attention": prev_attention,
                    "new_attention": global_attention,
                    "delta": delta,
                    "activity": actual_activity,
                }
                score = min(1.0, abs(delta))
                self._emit_attention_event(
                    event_type="global_attention_shift",
                    title=title,
                    content=content,
                    score=score,
                    payload=payload,
                    market_time=self.current_market_time_str,
                )

        # 活跃度突变事件
        if self.snapshots:
            last_activity = self.snapshots[-1].activity
            delta_act = actual_activity - last_activity
            if abs(delta_act) >= self._activity_shift_threshold:
                direction = "升温" if delta_act > 0 else "降温"
                title = "市场活跃度突变"
                content = f"市场活跃度{direction}: {last_activity:.2f} → {actual_activity:.2f}"
                payload = {
                    "old_activity": last_activity,
                    "new_activity": actual_activity,
                    "delta": delta_act,
                }
                self._emit_attention_event(
                    event_type="market_activity_shift",
                    title=title,
                    content=content,
                    score=min(1.0, abs(delta_act)),
                    payload=payload,
                    market_time=self.current_market_time_str,
                )

        # 板块集中度突变事件
        if self.snapshots and sector_weights:
            last_snapshot = self.snapshots[-1]
            last_weights = last_snapshot.sector_weights or {}
            if last_weights:
                last_top = max(last_weights.values()) if last_weights else 0
                last_total = sum(last_weights.values()) if last_weights else 1
                last_conc = last_top / last_total if last_total > 0 else 0
            else:
                last_conc = 0
            new_top = max(sector_weights.values()) if sector_weights else 0
            new_total = sum(sector_weights.values()) if sector_weights else 1
            new_conc = new_top / new_total if new_total > 0 else 0
            delta_conc = new_conc - last_conc
            if abs(delta_conc) >= self._concentration_shift_threshold:
                direction = "集中" if delta_conc > 0 else "分散"
                title = "板块集中度突变"
                content = f"资金{direction}: {last_conc:.2f} → {new_conc:.2f}"
                payload = {
                    "old_concentration": last_conc,
                    "new_concentration": new_conc,
                    "delta": delta_conc,
                }
                self._emit_attention_event(
                    event_type="sector_concentration_shift",
                    title=title,
                    content=content,
                    score=min(1.0, abs(delta_conc)),
                    payload=payload,
                    market_time=self.current_market_time_str,
                )

        # 市场状态变化事件
        if prev_state != "unknown" and prev_state != self.current_market_state:
            title = "市场注意力状态切换"
            content = f"市场状态由 {prev_state} 切换为 {self.current_market_state}"
            payload = {
                "old_state": prev_state,
                "new_state": self.current_market_state,
                "description": self.current_market_state_description,
                "global_attention": global_attention,
                "activity": actual_activity,
            }
            self._emit_attention_event(
                event_type="market_state_shift",
                title=title,
                content=content,
                score=min(1.0, max(global_attention, actual_activity)),
                payload=payload,
                market_time=self.current_market_time_str,
            )

    def _update_market_state(self, global_attention: float, activity: float,
                             sector_weights: Dict[str, float],
                             symbol_weights: Dict[str, float], timestamp: float):
        """更新市场注意力状态（基于注意力和活跃度）"""
        # 注意力（焦点集中程度）
        if global_attention > 0.7:
            attention_state = "active"
            attention_desc = "焦点高度集中 - 资金聚焦少数板块"
        elif global_attention > 0.4:
            attention_state = "moderate"
            attention_desc = "焦点较集中 - 部分板块受到关注"
        elif global_attention > 0.2:
            attention_state = "quiet"
            attention_desc = "焦点分散 - 没有明显主线"
        else:
            attention_state = "very_quiet"
            attention_desc = "焦点涣散 - 资金观望"

        # 活跃度（市场热闘程度）
        if activity > 0.7:
            activity_desc = "市场非常活跃"
        elif activity > 0.4:
            activity_desc = "市场温和"
        elif activity > 0.15:
            activity_desc = "市场清淡"
        else:
            activity_desc = "市场冷清"

        # 合并描述
        desc = f"{attention_desc}，{activity_desc}"

        # 如果板块权重非常集中，添加说明
        if sector_weights:
            top_weight = max(sector_weights.values()) if sector_weights else 0
            total_weight = sum(sector_weights.values()) if sector_weights else 0
            if total_weight > 0:
                concentration = top_weight / total_weight
                if concentration > 0.8:
                    desc = f"资金高度集中 - 注意力聚焦于少数板块，{activity_desc}"

        self.current_market_state = attention_state
        self.current_market_state_description = desc
        self.last_update_time = timestamp
    
    def _detect_changes(self, old: AttentionSnapshot, new: AttentionSnapshot, timestamp_str: str = None):
        """检测注意力变化 - 增强版：记录板块热点切换和个股关联"""
        import logging
        log = logging.getLogger(__name__)

        current_time = time.time()

        # 时间显示
        time_display = timestamp_str if timestamp_str else datetime.fromtimestamp(current_time).strftime("%H:%M:%S")
        # 提取行情日期（格式如 "2024-01-15 10:30:00" -> "2024-01-15"）
        market_date = timestamp_str.split(" ")[0] if timestamp_str else datetime.fromtimestamp(current_time).strftime("%Y-%m-%d")
        
        # ========== 检测板块重大变化 ==========
        all_sectors = set(old.sector_weights.keys()) | set(new.sector_weights.keys())
        
        for sector_id in all_sectors:
            old_weight = old.sector_weights.get(sector_id, 0)
            new_weight = new.sector_weights.get(sector_id, 0)
            sector_name = self.get_sector_name(sector_id)
            
            # 计算变化
            if old_weight > 0:
                change_pct = (new_weight - old_weight) / old_weight * 100
            else:
                change_pct = float('inf') if new_weight > 0 else 0
            
            # 只记录重大变化（变化超过5%）
            # 获取该板块下的个股变化
            all_symbol_changes = []
            for symbol in set(old.symbol_weights.keys()) | set(new.symbol_weights.keys()):
                s_old = old.symbol_weights.get(symbol, 0)
                s_new = new.symbol_weights.get(symbol, 0)
                if s_old > 0:
                    s_change_pct = (s_new - s_old) / s_old * 100
                    if abs(s_change_pct) > 5:  # 只记录变化超过5%的个股
                        all_symbol_changes.append({
                            'symbol': symbol,
                            'name': self.get_symbol_name(symbol),
                            'old': s_old,
                            'new': s_new,
                            'change_pct': s_change_pct
                        })
            
            # 按变化幅度排序，取前3个
            all_symbol_changes.sort(key=lambda x: abs(x['change_pct']), reverse=True)
            top_symbols = all_symbol_changes[:3]
            
            # 定义事件类型
            if old_weight == 0 and new_weight > 0:
                event_type = 'new_hot'
                event_emoji = '🔥'
                description = f"{sector_name} 成为新热点"
            elif old_weight > 0 and new_weight == 0:
                event_type = 'cooled'
                event_emoji = '❄️'
                description = f"{sector_name} 热点消退"
            elif change_pct > 10:
                event_type = 'rise'
                event_emoji = '📈'
                description = f"{sector_name} 权重飙升 +{change_pct:.1f}%"
            else:
                event_type = 'fall'
                event_emoji = '📉'
                description = f"{sector_name} 权重回调 {change_pct:.1f}%"
            
            # 创建事件对象
            event = SectorHotspotEvent(
                timestamp=current_time,
                market_time=time_display,
                market_date=market_date,
                sector_id=sector_id,
                sector_name=sector_name,
                event_type=event_type,
                weight_change=new_weight - old_weight,
                change_percent=change_pct if change_pct != float('inf') else 999,
                top_symbols=top_symbols,
                description=description
            )
            
            # 根据变化幅度记录到不同阈值的事件队列
            # 低阈值: 3%
            if abs(change_pct) >= 3 or (old_weight == 0 and new_weight > 0) or (old_weight > 0 and new_weight == 0):
                self.sector_hotspot_events_low.append(event)

            # 中阈值: 5%
            if abs(change_pct) >= 5 or (old_weight == 0 and new_weight > 0) or (old_weight > 0 and new_weight == 0):
                self.sector_hotspot_events_medium.append(event)
                score = min(1.0, abs(change_pct) / 100.0) if change_pct != float('inf') else 1.0
                payload = {
                    "sector_id": sector_id,
                    "sector_name": sector_name,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "change_percent": change_pct if change_pct != float('inf') else 999,
                    "event_type": event_type,
                    "top_symbols": top_symbols,
                }
                self._emit_attention_event(
                    event_type="sector_hotspot",
                    title=f"板块热点变化: {sector_name}",
                    content=description,
                    score=score,
                    payload=payload,
                    sector=sector_id,
                    market_time=time_display,
                )

            # 高阈值: 10%
            if abs(change_pct) >= 10 or (old_weight == 0 and new_weight > 0) or (old_weight > 0 and new_weight == 0):
                self.sector_hotspot_events_high.append(event)

            # 打印详细日志（只打印中阈值及以上的，使用DEBUG级别）
            if abs(change_pct) >= 5:
                log.debug(f"[{time_display}] {event_emoji} {description}")
                log.debug(f"  权重: {old_weight:.3f} → {new_weight:.3f} ({change_pct:+.1f}%)")
                if top_symbols:
                    log.debug(f"  关联个股权重变化:")
                    for s in top_symbols:
                        emoji = '📈' if s['change_pct'] > 0 else '📉'
                        log.debug(f"    {emoji} {s['symbol']} {s['name']}: {s['old']:.2f} → {s['new']:.2f} ({s['change_pct']:+.1f}%)")
        
        # ========== 检测个股重大变化（优化版） ==========
        # 只关注高权重个股的重大变化，减少噪音
        all_symbols = set(old.symbol_weights.keys()) | set(new.symbol_weights.keys())
        
        # 筛选出高权重个股（权重大于2.0或变化前权重大于2.0）
        significant_symbols = [
            symbol for symbol in all_symbols
            if old.symbol_weights.get(symbol, 0) > 2.0 or new.symbol_weights.get(symbol, 0) > 2.0
        ]
        
        for symbol in significant_symbols:
            old_weight = old.symbol_weights.get(symbol, 0)
            new_weight = new.symbol_weights.get(symbol, 0)
            symbol_name = self.get_symbol_name(symbol)
            
            if old_weight > 0:
                change_pct = (new_weight - old_weight) / old_weight * 100
            else:
                change_pct = float('inf') if new_weight > 0 else 0
            
            # 只记录重大变化（变化超过30%或进入/退出高权重区间）
            is_new_hot = old_weight <= 2.0 and new_weight > 3.0
            is_cooled = old_weight > 3.0 and new_weight <= 2.0
            is_major_change = abs(change_pct) >= 30
            
            if is_new_hot or is_cooled or is_major_change:
                market_info = new.symbol_market_data.get(symbol, {})
                price = market_info.get('price', 0)
                change_val = market_info.get('change', 0)
                volume = market_info.get('volume', 0)
                sector = market_info.get('sector', '')

                if is_new_hot:
                    description = f"{symbol} {symbol_name} 成为新热门"
                    emoji = '🔥'
                elif is_cooled:
                    description = f"{symbol} {symbol_name} 热门消退"
                    emoji = '❄️'
                elif change_pct > 30:
                    description = f"{symbol} {symbol_name} 权重飙升 +{change_pct:.1f}%"
                    emoji = '🚀'
                else:
                    description = f"{symbol} {symbol_name} 权重回调 {change_pct:.1f}%"
                    emoji = '🔻'

                change = AttentionChange(
                    timestamp=current_time,
                    change_type='new_hot' if is_new_hot else 'cooled' if is_cooled else ('strengthen' if change_pct > 0 else 'weaken'),
                    item_type='symbol',
                    item_id=symbol,
                    item_name=symbol_name,
                    old_weight=old_weight,
                    new_weight=new_weight,
                    change_percent=change_pct if change_pct != float('inf') else 999,
                    description=description,
                    market_time=time_display,
                    price=price,
                    price_change=change_val,
                    volume=volume,
                    sector=sector
                )
                self.changes.append(change)
                score = min(1.0, abs(change.change_percent) / 100.0)
                payload = {
                    "symbol": symbol,
                    "symbol_name": symbol_name,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "change_percent": change.change_percent,
                    "price": price,
                    "price_change": change_val,
                    "volume": volume,
                    "sector": sector,
                    "change_type": change.change_type,
                }
                self._emit_attention_event(
                    event_type="symbol_attention_change",
                    title=f"个股注意力变化: {symbol} {symbol_name}",
                    content=description,
                    score=score,
                    payload=payload,
                    symbol=symbol,
                    sector=sector,
                    market_time=time_display,
                )

                log.debug(f"[{time_display}] {emoji} {description}")
                if price > 0 and change_val != 0:
                    change_str = f"{change_val:+.2f}%" if isinstance(change_val, float) else f"{change_val}"
                    volume_str = self._format_volume(volume) if volume else ""
                    volume_str = f" | 量: {volume_str}" if volume_str else ""
                    sector_str = f" [{sector}]" if sector else ""
                    log.debug(f"  权重: {old_weight:.2f} → {new_weight:.2f} ({change_pct:+.1f}%) | 价: ¥{price:.2f} ({change_str}){volume_str}{sector_str}")
                else:
                    log.debug(f"  权重: {old_weight:.2f} → {new_weight:.2f} ({change_pct:+.1f}%)")
        
        # 注意：个股变化检测已合并到上面的逻辑中（第256-299行）
        # 避免重复检测导致记录过于频繁
        # 只保留权重大于1.0的个股的重大变化（更有参考意义）
    
    def get_recent_changes(self, n: int = 20) -> List[AttentionChange]:
        """获取最近的变化记录"""
        return list(self.changes)[-n:]
    
    def get_sector_trend(self, sector_id: str, n: int = 10) -> List[Dict]:
        """获取板块趋势"""
        trend = []
        for snapshot in list(self.snapshots)[-n:]:
            weight = snapshot.sector_weights.get(sector_id, 0)
            trend.append({
                'timestamp': snapshot.timestamp,
                'datetime': datetime.fromtimestamp(snapshot.timestamp).strftime('%H:%M:%S'),
                'weight': weight
            })
        return trend
    
    def get_symbol_trend(self, symbol: str, n: int = 10) -> List[Dict]:
        """获取个股趋势"""
        trend = []
        for snapshot in list(self.snapshots)[-n:]:
            weight = snapshot.symbol_weights.get(symbol, 0)
            trend.append({
                'timestamp': snapshot.timestamp,
                'datetime': datetime.fromtimestamp(snapshot.timestamp).strftime('%H:%M:%S'),
                'weight': weight
            })
        return trend
    
    def get_attention_shift_report(self, emit_to_insight: bool = True) -> Dict[str, Any]:
        """
        获取注意力转移报告

        Args:
            emit_to_insight: 是否推送洞察到认知系统，默认True

        Returns:
            包含注意力转移信息的字典
        """
        if len(self.snapshots) < 2:
            return {
                'has_shift': False,
                'message': '数据不足，无法检测转移'
            }

        old_snapshot = self.snapshots[0]
        new_snapshot = self.snapshots[-1]

        old_top_sectors = sorted(old_snapshot.sector_weights.keys(),
                                 key=lambda x: old_snapshot.sector_weights[x],
                                 reverse=True)[:3]
        new_top_sectors = sorted(new_snapshot.sector_weights.keys(),
                                 key=lambda x: new_snapshot.sector_weights[x],
                                 reverse=True)[:3]

        old_top_symbols = sorted(old_snapshot.symbol_weights.keys(),
                                 key=lambda x: old_snapshot.symbol_weights[x],
                                 reverse=True)[:5]
        new_top_symbols = sorted(new_snapshot.symbol_weights.keys(),
                                 key=lambda x: new_snapshot.symbol_weights[x],
                                 reverse=True)[:5]

        old_sector_set = set(old_top_sectors)
        new_sector_set = set(new_top_sectors)
        sector_shift = old_sector_set != new_sector_set

        old_symbol_set = set(old_top_symbols)
        new_symbol_set = set(new_top_symbols)
        symbol_shift = old_symbol_set != new_symbol_set

        removed_sectors = [s for s in old_top_sectors if s not in new_sector_set]
        added_sectors = [s for s in new_top_sectors if s not in old_sector_set]
        removed_symbols = [s for s in old_top_symbols if s not in new_symbol_set]
        added_symbols = [s for s in new_top_symbols if s not in old_symbol_set]

        report = {
            'has_shift': sector_shift or symbol_shift,
            'sector_shift': sector_shift,
            'symbol_shift': symbol_shift,
            'old_top_sectors': [(s, self.get_sector_name(s), old_snapshot.sector_weights.get(s, 0))
                               for s in old_top_sectors],
            'new_top_sectors': [(s, self.get_sector_name(s), new_snapshot.sector_weights.get(s, 0))
                               for s in new_top_sectors],
            'old_top_symbols': [(s, self.get_symbol_name(s), old_snapshot.symbol_weights.get(s, 0))
                               for s in old_top_symbols],
            'new_top_symbols': [(s, self.get_symbol_name(s), new_snapshot.symbol_weights.get(s, 0))
                               for s in new_top_symbols],
            'time_span': new_snapshot.timestamp - old_snapshot.timestamp,
            'old_snapshot': old_snapshot.to_dict() if hasattr(old_snapshot, 'to_dict') else {'timestamp': old_snapshot.timestamp},
            'new_snapshot': new_snapshot.to_dict() if hasattr(new_snapshot, 'to_dict') else {'timestamp': new_snapshot.timestamp},
            'removed_sectors': [(s, self.get_sector_name(s)) for s in removed_sectors],
            'added_sectors': [(s, self.get_sector_name(s)) for s in added_sectors],
            'removed_symbols': [(s, self.get_symbol_name(s)) for s in removed_symbols],
            'added_symbols': [(s, self.get_symbol_name(s)) for s in added_symbols],
        }

        if emit_to_insight and report['has_shift']:
            self._emit_attention_shift_insight(report, old_snapshot, new_snapshot)

        return report

    def _emit_attention_shift_insight(self, report: Dict[str, Any],
                                      old_snapshot: AttentionSnapshot,
                                      new_snapshot: AttentionSnapshot) -> None:
        """推送注意力转移洞察到认知系统"""
        now_ts = time.time()
        shift_key = "attention_shift:global"
        if not self._should_emit(shift_key, now_ts):
            return

        parts = []
        if report.get('symbol_shift') and report.get('removed_symbols'):
            removed = [f"{s}({n})" for s, n in report['removed_symbols']]
            parts.append(f"退出: {', '.join(removed)}")
        if report.get('symbol_shift') and report.get('added_symbols'):
            added = [f"{s}({n})" for s, n in report['added_symbols']]
            parts.append(f"新进: {', '.join(added)}")

        if report.get('sector_shift') and report.get('removed_sectors'):
            removed = [n for s, n in report['removed_sectors']]
            parts.append(f"板块退出: {', '.join(removed)}")
        if report.get('sector_shift') and report.get('added_sectors'):
            added = [n for s, n in report['added_sectors']]
            parts.append(f"板块新进: {', '.join(added)}")

        content = "; ".join(parts) if parts else "注意力集中度发生显著变化"

        time_span = report.get('time_span', 0)
        if time_span >= 3600:
            duration = f"{time_span/3600:.1f}小时"
        else:
            duration = f"{time_span/60:.1f}分钟"

        title = f"🔄 注意力转移 detected ({duration})"

        shift_types = []
        if report.get('sector_shift'):
            shift_types.append('板块')
        if report.get('symbol_shift'):
            shift_types.append('个股')
        shift_type_str = "+".join(shift_types) if shift_types else "综合"

        score = min(1.0, 0.5 + len(added_symbols) * 0.1)

        payload = {
            'shift_type': shift_type_str,
            'duration': duration,
            'time_span': time_span,
            'removed_sectors': report.get('removed_sectors', []),
            'added_sectors': report.get('added_sectors', []),
            'removed_symbols': report.get('removed_symbols', []),
            'added_symbols': report.get('added_symbols', []),
            'old_top_sectors': report.get('old_top_sectors', []),
            'new_top_sectors': report.get('new_top_sectors', []),
            'old_top_symbols': report.get('old_top_symbols', []),
            'new_top_symbols': report.get('new_top_symbols', []),
        }

        self._emit_attention_event(
            event_type="attention_shift",
            title=title,
            content=content,
            score=score,
            payload=payload,
            market_time=new_snapshot.market_time_str or "",
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """获取历史追踪摘要"""
        return {
            'snapshot_count': len(self.snapshots),
            'change_count': len(self.changes),
            'current_hot_sectors': [(k, self.get_sector_name(k), v)
                                   for k, v in self.current_hot_sectors.items()],
            'current_hot_symbols': [(k, self.get_symbol_name(k), v)
                                   for k, v in self.current_hot_symbols.items()],
            'recent_changes': len(self.get_recent_changes(10)),
            'market_state': self.current_market_state,
            'market_state_description': self.current_market_state_description,
            'last_update_time': self.last_update_time
        }

    def get_market_state_info(self) -> Dict[str, Any]:
        """获取当前市场注意力状态信息"""
        return {
            'state': self.current_market_state,
            'description': self.current_market_state_description,
            'last_update': self.last_update_time,
            'market_time': self.current_market_time_str,
            'hot_sectors': self.current_hot_sectors,
            'hot_symbols': self.current_hot_symbols,
            'global_attention': self.snapshots[-1].global_attention if self.snapshots else 0
        }

    def get_hot_sectors_with_names(self) -> list:
        """获取热门板块列表（带名称）"""
        result = []
        for sector_id, weight in self.current_hot_sectors.items():
            sector_name = self.get_sector_name(sector_id)
            result.append({
                'id': sector_id,
                'name': sector_name,
                'weight': weight
            })
        return result

    def get_hot_symbols_with_names(self, limit: int = 10) -> list:
        """获取热门股票列表（带名称）"""
        result = []
        for symbol, weight in list(self.current_hot_symbols.items())[:limit]:
            symbol_name = self.get_symbol_name(symbol)
            sector = self.get_symbol_sector_name(symbol)
            result.append({
                'code': symbol,
                'name': symbol_name,
                'sector': sector,
                'weight': weight
            })
        return result


# 全局追踪器实例
_history_tracker: Optional[AttentionHistoryTracker] = None


def get_history_tracker() -> AttentionHistoryTracker:
    """获取全局历史追踪器"""
    global _history_tracker
    if _history_tracker is None:
        _history_tracker = AttentionHistoryTracker()
    return _history_tracker
