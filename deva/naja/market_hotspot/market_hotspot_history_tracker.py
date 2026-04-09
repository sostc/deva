"""
MarketHotspotHistoryTracker - 市场热点追踪/题材热度/题材变迁

别名/关键词: 热点、题材热度、题材、block、hot、题材热点

追踪市场热点随时间的变化，包括：
- 热门题材的变化趋势
- 热门个股的变化趋势
- 题材轮动检测
- 热点加强/减弱检测
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
class HotspotSnapshot:
    """市场热点快照"""
    timestamp: float
    global_hotspot: float
    block_weights: Dict[str, float]
    symbol_weights: Dict[str, float]
    symbol_market_data: Dict[str, Dict] = field(default_factory=dict)
    market_time_str: str = ""  # 行情时间字符串（如 "2024-01-15 10:30:00"）
    activity: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
            'market_time_str': self.market_time_str,
            'global_hotspot': self.global_hotspot,
            'block_weights': self.block_weights,
            'symbol_weights': self.symbol_weights,
            'symbol_market_data': self.symbol_market_data,
            'activity': self.activity,
        }


@dataclass
class HotspotChange:
    """市场热点变化记录"""
    timestamp: float
    change_type: str  # 'block_shift', 'symbol_shift', 'strengthen', 'weaken', 'new_hot', 'cooled'
    item_type: str  # 'block' | 'symbol'
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
    block: str = ""


@dataclass
class BlockHotspotEvent:
    """题材热点切换事件"""
    timestamp: float
    market_time: str
    market_date: str
    block_id: str
    block_name: str
    event_type: str  # 'rise', 'fall', 'new_hot', 'cooled'
    weight_change: float
    change_percent: float
    top_symbols: List[Dict]  # 题材内涨跌最多的个股
    description: str


class MarketHotspotHistoryTracker:
    """
    市场热点历史追踪器

    功能：
    1. 保存热点历史快照
    2. 检测热点变化
    3. 追踪热门题材/股票的变迁
    4. 生成变化报告
    5. 持久化历史数据（重启后可恢复）
    """

    def __init__(self, max_history: int = 100, max_persist_days: int = 7):
        self.max_history = max_history
        self.max_persist_days = max_persist_days
        self.snapshots: deque = deque(maxlen=max_history)
        self.changes: deque = deque(maxlen=max_history * 2)

        # 持久化路径
        self._persist_base_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
            'data', 'hotspot_history'
        )

        # 题材热点切换事件记录 - 多阈值支持
        self.block_hotspot_events_low: deque = deque(maxlen=50)
        self.block_hotspot_events_medium: deque = deque(maxlen=50)
        self.block_hotspot_events_high: deque = deque(maxlen=50)

        self.current_hot_blocks: Dict[str, float] = {}
        self.current_hot_symbols: Dict[str, float] = {}

        self.block_history: Dict[str, List[Dict]] = {}
        self.symbol_history: Dict[str, List[Dict]] = {}

        self.symbol_names: Dict[str, str] = {}
        self.block_names: Dict[str, str] = {}
        self._block_configs: Dict[str, Any] = {}

        self.symbol_to_block: Dict[str, str] = {}

        self.current_market_state: str = "unknown"
        self.current_market_state_description: str = "等待数据..."
        self.last_update_time: float = 0
        self.current_market_time_str: str = ""

        self._emit_last: Dict[str, float] = {}
        self._emit_cooldown_seconds: float = 30.0

        self._activity_shift_threshold: float = 0.2
        self._concentration_shift_threshold: float = 0.2

        self._persist_loaded = False
    
    def register_symbol_name(self, symbol: str, name: str):
        """注册股票名称"""
        self.symbol_names[symbol] = name
    
    def register_block_name(self, block_id: str, name: str):
        """注册题材名称"""
        self.block_names[block_id] = name

    def register_blocks(self, blocks: List):
        """批量注册题材配置（用于初始化）"""
        for block in blocks:
            if hasattr(block, 'block_id') and hasattr(block, 'name'):
                self.block_names[block.block_id] = block.name
                self._block_configs[block.block_id] = block

    def get_symbol_name(self, symbol: str) -> str:
        """获取股票名称"""
        return self.symbol_names.get(symbol, symbol)

    def get_symbol_block(self, symbol: str) -> str:
        """获取股票所属题材"""
        if self.snapshots:
            latest = self.snapshots[-1]
            market_data = latest.symbol_market_data.get(symbol, {})
            block = market_data.get('block', '') or market_data.get('block', '')
            if block:
                return block

        return self.symbol_to_block.get(symbol, '')

    def get_symbol_block_name(self, symbol: str) -> str:
        """获取股票所属题材名称（带题材名翻译）"""
        block_id = self.get_symbol_block(symbol)
        if not block_id:
            return ''
        return self.get_block_name(block_id)

    def register_symbol_block(self, symbol: str, block_id: str):
        """注册个股-题材映射"""
        if block_id:
            self.symbol_to_block[symbol] = block_id

    def get_symbol_change(self, symbol: str) -> float:
        """获取股票涨跌幅"""
        if self.snapshots:
            latest = self.snapshots[-1]
            market_data = latest.symbol_market_data.get(symbol, {})
            return market_data.get('change')
        return None

    def get_block_name(self, block_id: str) -> str:
        """获取题材名称"""
        if not block_id:
            return ""

        if block_id in self.block_names:
            return self.block_names[block_id]
        if block_id in self._block_configs:
            return self._block_configs[block_id].name

        if block_id.startswith("block_") and len(block_id) > 10:
            return ""

        return block_id

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

    def _emit_hotspot_event(
        self,
        *,
        event_type: str,
        title: str,
        content: str,
        score: float,
        payload: Optional[Dict[str, Any]] = None,
        symbol: str = "",
        block: str = "",
        market_time: str = "",
        old_value: Optional[float] = None,
        new_value: Optional[float] = None,
    ) -> None:
        now_ts = time.time()
        key = f"{event_type}:{symbol or block or 'global'}"
        if not self._should_emit(key, now_ts):
            return

        from .event_bus import get_event_bus
        event_bus = get_event_bus()
        from .events import HotspotShiftEvent
        event = HotspotShiftEvent(
            event_type=event_type,
            timestamp=now_ts,
            title=title,
            content=content,
            score=score,
            symbol=symbol,
            block=block,
            market_time=market_time,
            payload=payload or {},
            old_value=old_value,
            new_value=new_value,
        )
        event_bus.publish(event)

        self._emit_to_memory(
            timestamp=now_ts,
            title=title,
            content=content,
            payload=payload or {},
            symbol=symbol,
            block=block,
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
        block: str = "",
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
                "source": "hotspot:history_tracker",
                "title": title,
                "content": content,
                "symbol": symbol,
                "block": block,
                "market_time": market_time,
                "payload": payload,
                "importance": "high",
            }
            memory.process_record(record)
        except Exception:
            return

    def record_snapshot(self, global_hotspot: float,
                       block_weights: Dict[str, float],
                       symbol_weights: Dict[str, float],
                       timestamp: float = None,
                       timestamp_str: str = None,
                       symbol_market_data: Dict[str, Dict] = None,
                       activity: float = None):
        """
        记录热点快照

        Args:
            global_hotspot: 全局热点
            block_weights: 题材权重字典
            symbol_weights: 个股权重字典
            timestamp: 时间戳（优先使用行情数据时间）
            timestamp_str: 时间字符串（用于日志显示）
            symbol_market_data: 个股行情数据字典 {symbol: {'price': float, 'change': float, 'volume': float, 'block': str}}
            activity: 市场活跃度
        """
        from deva.naja.market_hotspot.integration.extended import get_mode_manager
        mode_manager = get_mode_manager()
        current_mode = mode_manager.get_mode() if mode_manager else 'unknown'

        import logging
        log = logging.getLogger(__name__)

        actual_timestamp = timestamp if timestamp is not None else time.time()
        market_data = symbol_market_data if symbol_market_data else {}
        actual_activity = activity if activity is not None else 0.5
        prev_state = self.current_market_state
        prev_hotspot = self.snapshots[-1].global_hotspot if self.snapshots else None

        snapshot = HotspotSnapshot(
            timestamp=actual_timestamp,
            global_hotspot=global_hotspot,
            block_weights=block_weights.copy(),
            symbol_weights=symbol_weights.copy(),
            symbol_market_data=market_data.copy(),
            market_time_str=timestamp_str or "",
            activity=actual_activity,
        )

        # 检测热点变化
        if self.snapshots:
            last_snapshot = self.snapshots[-1]

            # 调试日志
            if len(self.snapshots) <= 2:
                sample_items = list(block_weights.items())[:3]
                sample_named = {self.get_block_name(k): v for k, v in sample_items}
                _lab_debug_log(f"快照{len(self.snapshots)+1}: block_weights样本={sample_named}")

            self._detect_changes(last_snapshot, snapshot, timestamp_str)

        self.snapshots.append(snapshot)
        log.debug(f"[HistoryTracker] record_snapshot(mode={current_mode}): 快照 #{len(self.snapshots)}, global_hotspot={global_hotspot:.3f}")

        # 更新当前热门
        self.current_hot_blocks = dict(sorted(
            block_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10])

        self.current_hot_symbols = dict(sorted(
            symbol_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20])

        # 更新市场热点状态
        self._update_market_state(global_hotspot, actual_activity, block_weights, symbol_weights, actual_timestamp)

        # 更新行情时间
        self.current_market_time_str = timestamp_str or ""

        # 全局热点变化事件
        if prev_hotspot is not None:
            delta = global_hotspot - prev_hotspot
            if abs(delta) >= 0.2:
                direction = "提升" if delta > 0 else "回落"
                title = "热点强度变化"
                content = f"全局热点{direction}: {prev_hotspot:.2f} → {global_hotspot:.2f}"
                payload = {
                    "old_hotspot": prev_hotspot,
                    "new_hotspot": global_hotspot,
                    "delta": delta,
                    "activity": actual_activity,
                }
                score = min(1.0, abs(delta))
                self._emit_hotspot_event(
                    event_type="global_hotspot_shift",
                    title=title,
                    content=content,
                    score=score,
                    payload=payload,
                    market_time=self.current_market_time_str,
                    old_value=prev_hotspot,
                    new_value=global_hotspot,
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
                self._emit_hotspot_event(
                    event_type="market_activity_shift",
                    title=title,
                    content=content,
                    score=min(1.0, abs(delta_act)),
                    payload=payload,
                    market_time=self.current_market_time_str,
                    old_value=last_activity,
                    new_value=actual_activity,
                )

        # 题材集中度突变事件
        if self.snapshots and block_weights:
            last_snapshot = self.snapshots[-1]
            last_weights = last_snapshot.block_weights or {}
            if last_weights:
                last_top = max(last_weights.values()) if last_weights else 0
                last_total = sum(last_weights.values()) if last_weights else 1
                last_conc = last_top / last_total if last_total > 0 else 0
            else:
                last_conc = 0
            new_top = max(block_weights.values()) if block_weights else 0
            new_total = sum(block_weights.values()) if block_weights else 1
            new_conc = new_top / new_total if new_total > 0 else 0
            delta_conc = new_conc - last_conc
            if abs(delta_conc) >= self._concentration_shift_threshold:
                direction = "集中" if delta_conc > 0 else "分散"
                title = "题材集中度突变"
                content = f"资金{direction}: {last_conc:.2f} → {new_conc:.2f}"
                payload = {
                    "old_concentration": last_conc,
                    "new_concentration": new_conc,
                    "delta": delta_conc,
                }
                self._emit_hotspot_event(
                    event_type="block_concentration_shift",
                    title=title,
                    content=content,
                    score=min(1.0, abs(delta_conc)),
                    payload=payload,
                    market_time=self.current_market_time_str,
                    old_value=last_conc,
                    new_value=new_conc,
                )

        # 市场状态变化事件
        if prev_state != "unknown" and prev_state != self.current_market_state:
            title = "市场热点状态切换"
            content = f"市场状态由 {prev_state} 切换为 {self.current_market_state}"
            payload = {
                "old_state": prev_state,
                "new_state": self.current_market_state,
                "description": self.current_market_state_description,
                "global_hotspot": global_hotspot,
                "activity": actual_activity,
            }
            self._emit_hotspot_event(
                event_type="market_state_shift",
                title=title,
                content=content,
                score=min(1.0, max(global_hotspot, actual_activity)),
                payload=payload,
                market_time=self.current_market_time_str,
                old_value=0.0,
                new_value=1.0,
            )

    def _update_market_state(self, global_hotspot: float, activity: float,
                             block_weights: Dict[str, float],
                             symbol_weights: Dict[str, float], timestamp: float):
        """更新市场热点状态（基于热点集中程度和活跃度）"""
        # 热点（hotspot集中程度）
        if global_hotspot > 0.7:
            hotspot_state = "active"
            hotspot_desc = "hotspot高度集中 - 资金聚焦少数题材"
        elif global_hotspot > 0.4:
            hotspot_state = "moderate"
            hotspot_desc = "hotspot较集中 - 部分题材受到关注"
        elif global_hotspot > 0.2:
            hotspot_state = "quiet"
            hotspot_desc = "hotspot分散 - 没有明显主线"
        else:
            hotspot_state = "very_quiet"
            hotspot_desc = "hotspot涣散 - 资金观望"

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
        desc = f"{hotspot_desc}，{activity_desc}"

        # 如果题材权重非常集中，添加说明
        if block_weights:
            top_weight = max(block_weights.values()) if block_weights else 0
            total_weight = sum(block_weights.values()) if block_weights else 0
            if total_weight > 0:
                concentration = top_weight / total_weight
                if concentration > 0.8:
                    desc = f"资金高度集中 - 热点聚焦于少数题材，{activity_desc}"

        self.current_market_state = hotspot_state
        self.current_market_state_description = desc
        self.last_update_time = timestamp
    
    def _detect_changes(self, old: HotspotSnapshot, new: HotspotSnapshot, timestamp_str: str = None):
        """检测热点变化 - 增强版：记录题材热点切换和个股关联"""
        import logging
        log = logging.getLogger(__name__)

        current_time = time.time()

        # 时间显示
        time_display = timestamp_str if timestamp_str else datetime.fromtimestamp(current_time).strftime("%H:%M:%S")
        # 提取行情日期（格式如 "2024-01-15 10:30:00" -> "2024-01-15"）
        market_date = timestamp_str.split(" ")[0] if timestamp_str else datetime.fromtimestamp(current_time).strftime("%Y-%m-%d")
        
        # ========== 检测题材重大变化 ==========
        all_blocks = set(old.block_weights.keys()) | set(new.block_weights.keys())

        for block_id in all_blocks:
            old_weight = old.block_weights.get(block_id, 0)
            new_weight = new.block_weights.get(block_id, 0)
            block_name = self.get_block_name(block_id)

            # 计算变化
            if old_weight > 0:
                change_pct = (new_weight - old_weight) / old_weight * 100
            else:
                change_pct = float('inf') if new_weight > 0 else 0

            # 只记录重大变化（变化超过5%）
            # 获取该题材下的个股变化
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
                description = f"{block_name} 成为新热点"
            elif old_weight > 0 and new_weight == 0:
                event_type = 'cooled'
                event_emoji = '❄️'
                description = f"{block_name} 热点消退"
            elif change_pct > 10:
                event_type = 'rise'
                event_emoji = '📈'
                description = f"{block_name} 权重飙升 +{change_pct:.1f}%"
            else:
                event_type = 'fall'
                event_emoji = '📉'
                description = f"{block_name} 权重回调 {change_pct:.1f}%"

            # 创建事件对象
            event = BlockHotspotEvent(
                timestamp=current_time,
                market_time=time_display,
                market_date=market_date,
                block_id=block_id,
                block_name=block_name,
                event_type=event_type,
                weight_change=new_weight - old_weight,
                change_percent=change_pct if change_pct != float('inf') else 999,
                top_symbols=top_symbols,
                description=description
            )
            
            # 根据变化幅度记录到不同阈值的事件队列
            # 低阈值: 3%
            if abs(change_pct) >= 3 or (old_weight == 0 and new_weight > 0) or (old_weight > 0 and new_weight == 0):
                self.block_hotspot_events_low.append(event)

            # 中阈值: 5%
            if abs(change_pct) >= 5 or (old_weight == 0 and new_weight > 0) or (old_weight > 0 and new_weight == 0):
                self.block_hotspot_events_medium.append(event)
                score = min(1.0, abs(change_pct) / 100.0) if change_pct != float('inf') else 1.0
                payload = {
                    "block_id": block_id,
                    "block_name": block_name,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "change_percent": change_pct if change_pct != float('inf') else 999,
                    "event_type": event_type,
                    "top_symbols": top_symbols,
                }
                self._emit_hotspot_event(
                    event_type="block_hotspot",
                    title=f"题材热点变化: {block_name}",
                    content=description,
                    score=score,
                    payload=payload,
                    block=block_id,
                    market_time=time_display,
                    old_value=old_weight,
                    new_value=new_weight,
                )

            # 高阈值: 10%
            if abs(change_pct) >= 10 or (old_weight == 0 and new_weight > 0) or (old_weight > 0 and new_weight == 0):
                self.block_hotspot_events_high.append(event)

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
                block = market_info.get('block', '') or market_info.get('block', '')

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

                change = HotspotChange(
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
                    block=block
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
                    "block": block,
                    "change_type": change.change_type,
                }
                self._emit_hotspot_event(
                    event_type="symbol_hotspot_change",
                    title=f"个股热点变化: {symbol} {symbol_name}",
                    content=description,
                    score=score,
                    payload=payload,
                    symbol=symbol,
                    block=block,
                    market_time=time_display,
                    old_value=change.old_weight,
                    new_value=change.new_weight,
                )

                log.debug(f"[{time_display}] {emoji} {description}")
                if price > 0 and change_val != 0:
                    change_str = f"{change_val:+.2f}%" if isinstance(change_val, float) else f"{change_val}"
                    volume_str = self._format_volume(volume) if volume else ""
                    volume_str = f" | 量: {volume_str}" if volume_str else ""
                    block_str = f" [{block}]" if block else ""
                    log.debug(f"  权重: {old_weight:.2f} → {new_weight:.2f} ({change_pct:+.1f}%) | 价: ¥{price:.2f} ({change_str}){volume_str}{block_str}")
                else:
                    log.debug(f"  权重: {old_weight:.2f} → {new_weight:.2f} ({change_pct:+.1f}%)")
        
        # 注意：个股变化检测已合并到上面的逻辑中（第256-299行）
        # 避免重复检测导致记录过于频繁
        # 只保留权重大于1.0的个股的重大变化（更有参考意义）
    
    def get_recent_changes(self, n: int = 20) -> List[HotspotChange]:
        """获取最近的变化记录"""
        return list(self.changes)[-n:]
    
    def get_block_trend(self, block_id: str, n: int = 10) -> List[Dict]:
        """获取题材趋势"""
        trend = []
        for snapshot in list(self.snapshots)[-n:]:
            weight = snapshot.block_weights.get(block_id, 0)
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
    
    def get_hotspot_shift_report(self, emit_to_insight: bool = True) -> Dict[str, Any]:
        """
        获取热点转移报告

        Args:
            emit_to_insight: 是否推送洞察到认知系统，默认True

        Returns:
            包含热点转移信息的字典
        """
        if len(self.snapshots) < 2:
            return {
                'has_shift': False,
                'message': '数据不足，无法检测转移'
            }

        old_snapshot = self.snapshots[0]
        new_snapshot = self.snapshots[-1]

        old_top_blocks = sorted(old_snapshot.block_weights.keys(),
                                 key=lambda x: old_snapshot.block_weights[x],
                                 reverse=True)[:3]
        new_top_blocks = sorted(new_snapshot.block_weights.keys(),
                                 key=lambda x: new_snapshot.block_weights[x],
                                 reverse=True)[:3]

        old_top_symbols = sorted(old_snapshot.symbol_weights.keys(),
                                 key=lambda x: old_snapshot.symbol_weights[x],
                                 reverse=True)[:5]
        new_top_symbols = sorted(new_snapshot.symbol_weights.keys(),
                                 key=lambda x: new_snapshot.symbol_weights[x],
                                 reverse=True)[:5]

        old_block_set = set(old_top_blocks)
        new_block_set = set(new_top_blocks)
        block_shift = old_block_set != new_block_set

        old_symbol_set = set(old_top_symbols)
        new_symbol_set = set(new_top_symbols)
        symbol_shift = old_symbol_set != new_symbol_set

        removed_blocks_list = [s for s in old_top_blocks if s not in new_block_set]
        added_blocks_list = [s for s in new_top_blocks if s not in old_block_set]
        removed_symbols = [s for s in old_top_symbols if s not in new_symbol_set]
        added_symbols = [s for s in new_top_symbols if s not in old_symbol_set]

        report = {
            'has_shift': block_shift or symbol_shift,
            'block_shift': block_shift,
            'symbol_shift': symbol_shift,
            'old_top_blocks': [(s, self.get_block_name(s), old_snapshot.block_weights.get(s, 0))
                               for s in old_top_blocks],
            'new_top_blocks': [(s, self.get_block_name(s), new_snapshot.block_weights.get(s, 0))
                               for s in new_top_blocks],
            'old_top_symbols': [(s, self.get_symbol_name(s), old_snapshot.symbol_weights.get(s, 0))
                               for s in old_top_symbols],
            'new_top_symbols': [(s, self.get_symbol_name(s), new_snapshot.symbol_weights.get(s, 0))
                               for s in new_top_symbols],
            'time_span': new_snapshot.timestamp - old_snapshot.timestamp,
            'old_snapshot': old_snapshot.to_dict() if hasattr(old_snapshot, 'to_dict') else {'timestamp': old_snapshot.timestamp},
            'new_snapshot': new_snapshot.to_dict() if hasattr(new_snapshot, 'to_dict') else {'timestamp': new_snapshot.timestamp},
            'removed_blocks': [(s, self.get_block_name(s)) for s in removed_blocks_list],
            'added_blocks': [(s, self.get_block_name(s)) for s in added_blocks_list],
            'removed_symbols': [(s, self.get_symbol_name(s)) for s in removed_symbols],
            'added_symbols': [(s, self.get_symbol_name(s)) for s in added_symbols],
            'block_shift': block_shift,
            'removed_blocks': [(s, self.get_block_name(s)) for s in removed_blocks_list],
            'added_blocks': [(s, self.get_block_name(s)) for s in added_blocks_list],
        }

        if emit_to_insight and report['has_shift']:
            self._emit_hotspot_shift_insight(report, old_snapshot, new_snapshot)

        return report

    def _emit_hotspot_shift_insight(self, report: Dict[str, Any],
                                      old_snapshot: HotspotSnapshot,
                                      new_snapshot: HotspotSnapshot) -> None:
        """推送热点转移洞察到认知系统"""
        now_ts = time.time()
        shift_key = "hotspot_shift:global"
        if not self._should_emit(shift_key, now_ts):
            return

        parts = []
        if report.get('symbol_shift') and report.get('removed_symbols'):
            removed = [f"{s}({n})" for s, n in report['removed_symbols']]
            parts.append(f"退出: {', '.join(removed)}")
        if report.get('symbol_shift') and report.get('added_symbols'):
            added = [f"{s}({n})" for s, n in report['added_symbols']]
            parts.append(f"新进: {', '.join(added)}")

        if report.get('block_shift') and report.get('removed_blocks'):
            removed = [n for s, n in report['removed_blocks']]
            parts.append(f"题材退出: {', '.join(removed)}")
        if report.get('block_shift') and report.get('added_blocks'):
            added = [n for s, n in report['added_blocks']]
            parts.append(f"题材新进: {', '.join(added)}")

        content = "; ".join(parts) if parts else "热点集中度发生显著变化"

        time_span = report.get('time_span', 0)
        if time_span >= 3600:
            duration = f"{time_span/3600:.1f}小时"
        else:
            duration = f"{time_span/60:.1f}分钟"

        title = f"🔄 热点转移 detected ({duration})"

        shift_types = []
        if report.get('block_shift'):
            shift_types.append('题材')
        if report.get('symbol_shift'):
            shift_types.append('个股')
        shift_type_str = "+".join(shift_types) if shift_types else "综合"

        score = min(1.0, 0.5 + len(added_symbols) * 0.1)

        payload = {
            'shift_type': shift_type_str,
            'duration': duration,
            'time_span': time_span,
            'block_shift': report.get('block_shift', False),
            'removed_blocks': report.get('removed_blocks', []),
            'added_blocks': report.get('added_blocks', []),
            'removed_symbols': report.get('removed_symbols', []),
            'added_symbols': report.get('added_symbols', []),
            'old_top_blocks': report.get('old_top_blocks', []),
            'new_top_blocks': report.get('new_top_blocks', []),
            'old_top_symbols': report.get('old_top_symbols', []),
            'new_top_symbols': report.get('new_top_symbols', []),
            'block_shift': report.get('block_shift', False),
            'removed_blocks': report.get('removed_blocks', []),
            'added_blocks': report.get('added_blocks', []),
        }

        self._emit_hotspot_event(
            event_type="hotspot_shift",
            title=title,
            content=content,
            score=score,
            payload=payload,
            market_time=new_snapshot.market_time_str or "",
            old_value=old_snapshot.global_hotspot if old_snapshot else 0.0,
            new_value=new_snapshot.global_hotspot,
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """获取历史追踪摘要"""
        return {
            'snapshot_count': len(self.snapshots),
            'change_count': len(self.changes),
            'current_hot_blocks': [(k, self.get_block_name(k), v)
                                   for k, v in self.current_hot_blocks.items()],
            'current_hot_symbols': [(k, self.get_symbol_name(k), v)
                                   for k, v in self.current_hot_symbols.items()],
            'recent_changes': len(self.get_recent_changes(10)),
            'market_state': self.current_market_state,
            'market_state_description': self.current_market_state_description,
            'last_update_time': self.last_update_time
        }

    def get_market_state_info(self) -> Dict[str, Any]:
        """获取当前市场热点状态信息"""
        return {
            'state': self.current_market_state,
            'description': self.current_market_state_description,
            'last_update': self.last_update_time,
            'market_time': self.current_market_time_str,
            'hot_blocks': self.current_hot_blocks,
            'hot_symbols': self.current_hot_symbols,
            'global_hotspot': self.snapshots[-1].global_hotspot if self.snapshots else 0
        }

    def get_hot_blocks_with_names(self) -> list:
        """获取热门题材列表（带名称）"""
        result = []
        for block_id, weight in self.current_hot_blocks.items():
            block_name = self.get_block_name(block_id)
            result.append({
                'id': block_id,
                'name': block_name,
                'weight': weight
            })
        return result

    def get_hot_symbols_with_names(self, limit: int = 10) -> list:
        """获取热门股票列表（带名称）"""
        result = []
        for symbol, weight in list(self.current_hot_symbols.items())[:limit]:
            symbol_name = self.get_symbol_name(symbol)
            block_name = self.get_symbol_block_name(symbol)
            result.append({
                'code': symbol,
                'name': symbol_name,
                'block': block_name,
                'weight': weight
            })
        return result

    def is_block_valid(self, block_id: str) -> bool:
        """检查题材ID是否有效"""
        if not block_id:
            return False
        if block_id in self.block_names:
            return True
        if block_id in self._block_configs:
            return True
        if block_id.startswith("block_") and len(block_id) > 10:
            return False
        return True

    def _ensure_persist_dir(self):
        """确保持久化目录存在"""
        if not os.path.exists(self._persist_base_path):
            os.makedirs(self._persist_base_path, exist_ok=True)

    def _get_persist_file_path(self, market: str = None, date: str = None) -> str:
        """获取持久化文件路径"""
        self._ensure_persist_dir()
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        if market:
            return os.path.join(self._persist_base_path, f'{market}_snapshots_{date}.json')
        return os.path.join(self._persist_base_path, f'snapshots_{date}.json')

    def _cleanup_old_files(self):
        """清理过期的持久化文件"""
        import logging
        log = logging.getLogger(__name__)

        try:
            if not os.path.exists(self._persist_base_path):
                return

            cutoff_time = time.time() - (self.max_persist_days * 86400)
            removed_count = 0

            for filename in os.listdir(self._persist_base_path):
                if not filename.endswith('.json'):
                    continue
                file_path = os.path.join(self._persist_base_path, filename)
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_time:
                        os.remove(file_path)
                        removed_count += 1
                except Exception:
                    pass

            if removed_count > 0:
                log.info(f"[HistoryTracker] 清理过期历史文件: {removed_count} 个")
        except Exception as e:
            log.warning(f"[HistoryTracker] 清理过期文件失败: {e}")

    def save_state(self, market: str = None):
        """
        保存当前状态到持久化文件

        Args:
            market: 市场标识 ('CN' 或 'US')，None 表示保存到默认文件
        """
        import logging
        log = logging.getLogger(__name__)

        try:
            self._ensure_persist_dir()
            self._cleanup_old_files()

            file_path = self._get_persist_file_path(market)

            data = {
                'saved_at': time.time(),
                'saved_at_str': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'market': market or 'ALL',
                'snapshot_count': len(self.snapshots),
                'change_count': len(self.changes),
                'symbol_names': self.symbol_names,
                'block_names': self.block_names,
                'snapshots': [s.to_dict() for s in self.snapshots],
                'changes': [
                    {
                        'timestamp': c.timestamp,
                        'change_type': c.change_type,
                        'item_type': c.item_type,
                        'item_id': c.item_id,
                        'item_name': c.item_name,
                        'old_weight': c.old_weight,
                        'new_weight': c.new_weight,
                        'change_percent': c.change_percent,
                        'description': c.description,
                        'market_time': c.market_time,
                        'price': c.price,
                        'price_change': c.price_change,
                        'volume': c.volume,
                        'block': c.block,
                    }
                    for c in self.changes
                ],
                'block_hotspot_events': [
                    {
                        'timestamp': e.timestamp,
                        'market_time': e.market_time,
                        'market_date': e.market_date,
                        'block_id': e.block_id,
                        'block_name': e.block_name,
                        'event_type': e.event_type,
                        'weight_change': e.weight_change,
                        'change_percent': e.change_percent,
                        'description': e.description,
                    }
                    for e in self.block_hotspot_events_medium
                ],
            }

            import json
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            log.debug(f"[HistoryTracker] 状态已保存: {file_path}, snapshots={len(self.snapshots)}")
        except Exception as e:
            log.warning(f"[HistoryTracker] 保存状态失败: {e}")

    def load_state(self, market: str = None, date: str = None) -> bool:
        """
        从持久化文件加载状态

        Args:
            market: 市场标识 ('CN' 或 'US')，None 表示加载默认文件
            date: 日期字符串 (YYYY-MM-DD)，None 表示加载今天的文件

        Returns:
            是否加载成功
        """
        import logging
        log = logging.getLogger(__name__)

        try:
            file_path = self._get_persist_file_path(market, date)

            if not os.path.exists(file_path):
                log.debug(f"[HistoryTracker] 持久化文件不存在: {file_path}")
                return False

            import json
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.symbol_names.update(data.get('symbol_names', {}))
            self.block_names.update(data.get('block_names', {}))

            snapshots_data = data.get('snapshots', [])
            for s_data in snapshots_data[-self.max_history:]:
                snapshot = HotspotSnapshot(
                    timestamp=s_data['timestamp'],
                    global_hotspot=s_data['global_hotspot'],
                    block_weights=s_data['block_weights'],
                    symbol_weights=s_data['symbol_weights'],
                    symbol_market_data=s_data.get('symbol_market_data', {}),
                    market_time_str=s_data.get('market_time_str', ''),
                    activity=s_data.get('activity', 0.5),
                )
                self.snapshots.append(snapshot)

            changes_data = data.get('changes', [])
            for c_data in changes_data[-self.max_history * 2:]:
                change = HotspotChange(
                    timestamp=c_data['timestamp'],
                    change_type=c_data['change_type'],
                    item_type=c_data['item_type'],
                    item_id=c_data['item_id'],
                    item_name=c_data['item_name'],
                    old_weight=c_data['old_weight'],
                    new_weight=c_data['new_weight'],
                    change_percent=c_data['change_percent'],
                    description=c_data['description'],
                    market_time=c_data.get('market_time', ''),
                    price=c_data.get('price', 0),
                    price_change=c_data.get('price_change', 0),
                    volume=c_data.get('volume', 0),
                    block=c_data.get('block', ''),
                )
                self.changes.append(change)

            events_data = data.get('block_hotspot_events', [])
            for e_data in events_data[-50:]:
                event = BlockHotspotEvent(
                    timestamp=e_data['timestamp'],
                    market_time=e_data['market_time'],
                    market_date=e_data['market_date'],
                    block_id=e_data['block_id'],
                    block_name=e_data['block_name'],
                    event_type=e_data['event_type'],
                    weight_change=e_data['weight_change'],
                    change_percent=e_data['change_percent'],
                    top_symbols=[],
                    description=e_data['description'],
                )
                self.block_hotspot_events_medium.append(event)

            self._persist_loaded = True
            log.info(f"[HistoryTracker] 状态已加载: {file_path}, snapshots={len(self.snapshots)}, changes={len(self.changes)}")
            return True
        except Exception as e:
            log.warning(f"[HistoryTracker] 加载状态失败: {e}")
            return False

    def load_latest_state(self) -> bool:
        """
        加载最近的历史数据（跨多天查找）

        Returns:
            是否加载成功
        """
        import logging
        log = logging.getLogger(__name__)

        if not os.path.exists(self._persist_base_path):
            log.debug(f"[HistoryTracker] 持久化目录不存在: {self._persist_base_path}")
            return False

        try:
            import json
            today = datetime.now().strftime('%Y-%m-%d')

            files = []
            for filename in os.listdir(self._persist_base_path):
                if not filename.endswith('.json'):
                    continue
                if '_snapshots_' not in filename:
                    continue
                file_path = os.path.join(self._persist_base_path, filename)
                try:
                    mtime = os.path.getmtime(file_path)
                    files.append((mtime, file_path))
                except Exception:
                    pass

            files.sort(reverse=True)

            loaded = False
            for mtime, file_path in files[:self.max_persist_days]:
                date_str = os.path.basename(file_path).split('_')[-1].replace('.json', '')
                if self.load_state(date=date_str):
                    loaded = True
                    log.info(f"[HistoryTracker] 成功从 {date_str} 加载历史数据")
                    break

            if not loaded:
                log.debug(f"[HistoryTracker] 未找到可用的历史持久化文件")

            return loaded
        except Exception as e:
            log.warning(f"[HistoryTracker] 加载最近状态失败: {e}")
            return False

    def get_persist_info(self) -> Dict[str, Any]:
        """获取持久化状态信息"""
        info = {
            'persist_path': self._persist_base_path,
            'persist_days': self.max_persist_days,
            'loaded_from_persist': self._persist_loaded,
            'snapshot_count': len(self.snapshots),
            'change_count': len(self.changes),
            'files': [],
        }

        try:
            if os.path.exists(self._persist_base_path):
                for filename in sorted(os.listdir(self._persist_base_path)):
                    if filename.endswith('.json'):
                        file_path = os.path.join(self._persist_base_path, filename)
                        mtime = os.path.getmtime(file_path)
                        info['files'].append({
                            'name': filename,
                            'modified': datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            'size_kb': os.path.getsize(file_path) / 1024,
                        })
        except Exception:
            pass

        return info


# 全局追踪器实例
_history_tracker: Optional[MarketHotspotHistoryTracker] = None


def get_history_tracker() -> MarketHotspotHistoryTracker:
    """获取全局历史追踪器"""
    from deva.naja.register import SR
    return SR('history_tracker')
