"""
AwakenedAlaya - 觉醒阿赖耶识

增强光明藏和顿悟引擎，实现：
1. 完整顿悟机制
2. 跨市场迁移增强
3. 全量模式召回
"""

import time
import math
import logging
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

try:
    from deva import NB
    NB_AVAILABLE = True
except ImportError:
    NB_AVAILABLE = False

log = logging.getLogger(__name__)

_loop_audit_log_stage = None

def _get_audit():
    global _loop_audit_log_stage
    if _loop_audit_log_stage is None:
        try:
            from ..common.loop_audit import LoopAudit
            _loop_audit_log_stage = lambda **kw: LoopAudit(**kw)
        except ImportError:
            _loop_audit_log_stage = lambda **kw: _DummyAudit()
    return _loop_audit_log_stage

class _DummyAudit:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def record_data_out(self, *args, **kwargs): pass


class AwakeningLevel(Enum):
    """觉醒层次"""
    DORMANT = "dormant"          # 沉睡
    AWAKENING = "awakening"     # 觉醒中
    ILLUMINATED = "illuminated" # 已照亮
    ENLIGHTENED = "enlightened" # 顿悟


class CrossMarketSectorMapper:
    """
    美股板块 → A股板块 映射器

    用于将美股热门板块的变化传导到A股市场预测
    """
    US_SECTOR_TO_A_STOCK: Dict[str, List[str]] = {
        "ai_chip": ["AI", "半导体", "芯片", "光刻机", "GPU", "CPU"],
        "ai_infra": ["AI", "云计算", "云服务", "数据中心", "服务器"],
        "cloud_ai": ["AI", "云计算", "云服务", "SaaS", "大数据"],
        "ai_software": ["AI", "软件", "大数据", "人工智能"],
        "social_media": ["社交媒体", "互联网", "广告"],
        "e_commerce": ["电商", "零售", "物流", "跨境电商"],
        "ev": ["新能源汽车", "锂电池", "汽车零部件", "充电桩"],
        "robotaxi": ["自动驾驶", "新能源汽车", "AI"],
        "robotics": ["机器人", "人工智能", "自动化", "工业机器人"],
        "crypto": ["数字货币", "区块链", "金融科技", "比特币"],
        "streaming": ["流媒体", "娱乐", "影视", "在线视频"],
        "gaming": ["游戏", "电竞", "元宇宙", "VR/AR"],
        "fintech": ["金融科技", "数字货币", "支付", "区块链"],
        "finance": ["金融", "证券", "银行", "保险"],
        "consumer": ["消费", "零售", "食品饮料", "家电"],
        "healthcare": ["医疗", "医药", "医疗器械", "生物制药"],
    }

    @classmethod
    def get_a_stock_sectors(cls, us_sector: str) -> List[str]:
        """获取美股板块对应的A股板块列表"""
        return cls.US_SECTOR_TO_A_STOCK.get(us_sector, [])

    @classmethod
    def get_all_a_stock_sectors(cls) -> Set[str]:
        """获取所有映射的A股板块（去重）"""
        result = set()
        for a_sectors in cls.US_SECTOR_TO_A_STOCK.values():
            result.update(a_sectors)
        return result


@dataclass
class PatternArchive:
    """模式归档"""
    pattern_id: str
    pattern_type: str
    market_context: Dict[str, Any]
    outcome: Dict[str, Any]
    success: bool
    archived_at: float


@dataclass
class AwakeningSignal:
    """觉醒信号"""
    signal_type: str            # "pattern_match", "contradiction", "timing"
    trigger_conditions: List[str]
    confidence: float
    illumination_content: str
    timestamp: float = field(default_factory=time.time)


class CrossMarketMemory:
    """
    跨市场记忆

    存储和迁移跨市场的经验

    衰减机制设计：
    1. 新鲜度衰减：模式按时间指数衰减
    2. 成功率追踪：每次迁移结果更新成功率
    3. 条件匹配度：根据条件偏差计算匹配分数
    """

    def __init__(
        self,
        pattern_half_life: float = 604800.0,
        pattern_max_age_factor: float = 3.0,
        min_match_score: float = 0.1
    ):
        """
        初始化跨市场记忆

        Args:
            pattern_half_life: 模式半衰期（秒），默认 7 天
            pattern_max_age_factor: 最大年龄系数，超过 half_life * factor 后降权
            min_match_score: 最低匹配分数，低于此分数的模式被排除
        """
        self._source_memories: Dict[str, List[Dict[str, Any]]] = {
            "futures": [],
            "us_stock": [],
            "hk_stock": [],
            "crypto": []
        }
        self._transfer_success_rate: Dict[str, float] = {}
        self._pattern_half_life = pattern_half_life
        self._pattern_max_age_factor = pattern_max_age_factor
        self._min_match_score = min_match_score

    def _compute_freshness_weight(self, stored_at: float) -> float:
        """
        计算模式的新鲜度权重

        使用指数衰减：weight = exp(-dt / half_life)
        超过 max_age_factor * half_life 后权重接近 0
        """
        dt = time.time() - stored_at
        max_age = self._pattern_half_life * self._pattern_max_age_factor
        if dt >= max_age:
            return 0.01
        return math.exp(-dt / self._pattern_half_life)

    def _compute_match_score(
        self,
        memory: Dict[str, Any],
        current_conditions: Dict[str, Any]
    ) -> float:
        """
        计算条件匹配分数

        返回 0-1 之间的分数，越高越匹配
        """
        memory_conditions = memory.get("conditions", {})
        if not memory_conditions:
            return 0.5

        match_sum = 0.0
        match_count = 0

        for key, value in current_conditions.items():
            if key not in memory_conditions:
                continue

            mem_val = memory_conditions[key]
            if isinstance(value, (int, float)) and isinstance(mem_val, (int, float)) and mem_val != 0:
                deviation = abs(value - mem_val) / abs(mem_val)
                match_sum += max(0, 1 - deviation)
                match_count += 1

        if match_count == 0:
            return 0.5

        return match_sum / match_count

    def _compute_pattern_score(
        self,
        memory: Dict[str, Any],
        current_conditions: Dict[str, Any]
    ) -> float:
        """
        计算模式综合评分

        评分 = 成功率 × 条件匹配度 × 新鲜度权重
        """
        pattern_id = memory.get("pattern_id", id(memory))
        success_rate = self._transfer_success_rate.get(pattern_id, 0.5)

        match_score = self._compute_match_score(memory, current_conditions)
        freshness = self._compute_freshness_weight(memory.get("stored_at", time.time()))

        score = success_rate * match_score * freshness
        return score

    def push_sector_change(
        self,
        us_sector_changes: Dict[str, float],
        significance_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        推送美股板块变化到跨市场记忆

        Args:
            us_sector_changes: 美股板块注意力变化 dict，{板块ID: 注意力权重}
            significance_threshold: 显著变化阈值，默认0.3

        Returns:
            被推送的A股预测板块列表
        """
        if not us_sector_changes:
            return []

        significant_changes = {
            sector: weight
            for sector, weight in us_sector_changes.items()
            if weight >= significance_threshold
        }

        if not significant_changes:
            return []

        pushed_a_sectors = []

        for us_sector, weight in significant_changes.items():
            a_sectors = CrossMarketSectorMapper.get_a_stock_sectors(us_sector)

            for a_sector in a_sectors:
                pattern = {
                    "pattern_id": f"us_{us_sector}_to_a_{a_sector}_{int(time.time())}",
                    "conditions": {
                        "us_sector": us_sector,
                        "us_weight": weight,
                        "a_sector": a_sector,
                        "significance": weight,
                    },
                    "source_market": "us_stock",
                    "target_market": "a_stock",
                    "prediction": "明日A股相关板块可能受益",
                }

                self.store_success_pattern("us_stock", pattern)
                pushed_a_sectors.append({
                    "us_sector": us_sector,
                    "us_weight": weight,
                    "a_sector": a_sector,
                })

        log.info(f"[CrossMarket] 推送美股板块变化: {len(pushed_a_sectors)} 个A股预测")
        return pushed_a_sectors

    def store_success_pattern(
        self,
        source_market: str,
        pattern: Dict[str, Any]
    ):
        """存储成功模式"""
        if source_market not in self._source_memories:
            self._source_memories[source_market] = []

        memory_entry = {
            **pattern,
            "stored_at": time.time(),
            "usage_count": 0,
            "source_market": source_market
        }

        pattern_id = pattern.get("pattern_id")
        if pattern_id and pattern_id not in self._transfer_success_rate:
            self._transfer_success_rate[pattern_id] = 0.5

        self._source_memories[source_market].append(memory_entry)

        if len(self._source_memories[source_market]) > 500:
            self._source_memories[source_market] = self._source_memories[source_market][-500:]

    def recall_applicable_patterns(
        self,
        target_market: str,
        current_conditions: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        召回适用模式

        返回按综合评分排序的 top-k 模式
        """
        scored_patterns = []

        market_transfer_map = {
            "a_stock": ["futures", "hk_stock", "us_stock"],
            "hk_stock": ["us_stock", "a_stock"],
        }

        source_markets = market_transfer_map.get(target_market, list(self._source_memories.keys()))

        for source_market in source_markets:
            if source_market not in self._source_memories:
                continue

            for memory in self._source_memories[source_market]:
                match_score = self._compute_match_score(memory, current_conditions)

                if match_score < self._min_match_score:
                    continue

                pattern_score = self._compute_pattern_score(memory, current_conditions)

                memory["usage_count"] += 1
                memory["match_score"] = match_score
                memory["pattern_score"] = pattern_score
                scored_patterns.append(memory)

        scored_patterns.sort(key=lambda x: x.get("pattern_score", 0), reverse=True)
        return scored_patterns[:5]

    def _check_applicability(
        self,
        memory: Dict[str, Any],
        conditions: Dict[str, Any]
    ) -> bool:
        """检查是否适用（保持向后兼容）"""
        memory_conditions = memory.get("conditions", {})

        for key, value in conditions.items():
            if key in memory_conditions:
                mem_val = memory_conditions[key]
                if isinstance(value, (int, float)) and isinstance(mem_val, (int, float)):
                    if abs(value - mem_val) > mem_val * 0.5:
                        return False

        return True

    def record_transfer_outcome(
        self,
        pattern_id: str,
        success: bool
    ):
        """记录迁移结果"""
        if pattern_id not in self._transfer_success_rate:
            self._transfer_success_rate[pattern_id] = 0.5

        current = self._transfer_success_rate[pattern_id]
        if success:
            self._transfer_success_rate[pattern_id] = min(0.95, current + 0.1)
        else:
            self._transfer_success_rate[pattern_id] = max(0.1, current - 0.1)

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        total_patterns = sum(len(memories) for memories in self._source_memories.values())

        market_stats = {}
        for market, memories in self._source_memories.items():
            if memories:
                freshness_sum = sum(
                    self._compute_freshness_weight(m.get("stored_at", 0))
                    for m in memories
                )
                market_stats[market] = {
                    "count": len(memories),
                    "avg_freshness": freshness_sum / len(memories) if memories else 0
                }

        return {
            "total_patterns": total_patterns,
            "market_stats": market_stats,
            "pattern_half_life_days": self._pattern_half_life / 86400,
            "tracked_success_rates": len(self._transfer_success_rate),
        }

    PERSISTENCE_TABLE = "naja_cross_market_memory"
    PERSISTENCE_KEY = "cross_market_memory"

    def save_state(self) -> Dict[str, Any]:
        """保存跨市场记忆状态"""
        if not NB_AVAILABLE:
            return {"success": False, "error": "NB not available"}

        try:
            state_data = {
                "source_memories": self._source_memories,
                "transfer_success_rate": self._transfer_success_rate,
                "pattern_half_life": self._pattern_half_life,
                "pattern_max_age_factor": self._pattern_max_age_factor,
                "min_match_score": self._min_match_score,
                "saved_at": time.time(),
            }
            db = NB(self.PERSISTENCE_TABLE)
            db[self.PERSISTENCE_KEY] = state_data
            return {
                "success": True,
                "total_patterns": sum(len(m) for m in self._source_memories.values()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_state(self) -> Dict[str, Any]:
        """加载跨市场记忆状态"""
        if not NB_AVAILABLE:
            return {"success": False, "error": "NB not available"}

        try:
            db = NB(self.PERSISTENCE_TABLE)
            if self.PERSISTENCE_KEY not in db:
                return {"success": True, "loaded": False, "message": "No saved state"}

            state_data = db.get(self.PERSISTENCE_KEY)

            self._source_memories = state_data.get("source_memories", {
                "futures": [], "us_stock": [], "hk_stock": [], "crypto": []
            })
            self._transfer_success_rate = state_data.get("transfer_success_rate", {})
            self._pattern_half_life = state_data.get("pattern_half_life", 604800.0)
            self._pattern_max_age_factor = state_data.get("pattern_max_age_factor", 3.0)
            self._min_match_score = state_data.get("min_match_score", 0.1)

            return {
                "success": True,
                "loaded": True,
                "total_patterns": sum(len(m) for m in self._source_memories.values()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class PatternArchiveManager:
    """
    模式归档管理器

    管理所有历史模式的全量召回

    衰减机制设计：
    1. 成功率截断：失败次数过多的模式被降权
    2. 新鲜度衰减：按时间指数衰减归档模式的影响力
    3. 智能召回：按成功率 × 新鲜度综合排序
    """

    def __init__(
        self,
        pattern_half_life: float = 604800.0,
        max_archive_size: int = 1000,
        retain_ratio: float = 0.5
    ):
        """
        初始化模式归档管理器

        Args:
            pattern_half_life: 模式半衰期（秒），默认 7 天
            max_archive_size: 每个类型最大归档数量
            retain_ratio: 超过容量时保留的成功率比例
        """
        self._archives: Dict[str, List[PatternArchive]] = {
            "momentum": [],
            "reversal": [],
            "breakout": [],
            "accumulation": [],
            "distribution": [],
            "sector_rotation": []
        }
        self._index: Dict[str, Set[str]] = {
            "by_symbol": {},
            "by_sector": {},
            "by_time": {}
        }
        self._pattern_half_life = pattern_half_life
        self._max_archive_size = max_archive_size
        self._retain_ratio = retain_ratio

    def _compute_pattern_weight(self, archive: PatternArchive) -> float:
        """
        计算模式的综合权重

        权重 = success × freshness
        """
        freshness = math.exp(-(time.time() - archive.archived_at) / self._pattern_half_life)
        weight = 1.0 * freshness if archive.success else 0.3 * freshness
        return weight

    def _cleanup_archive(self, pattern_type: str):
        """
        清理归档列表

        保留成功率高的模式，同时保留一些最近的失败模式用于分析
        """
        pattern_list = self._archives.get(pattern_type, [])
        if len(pattern_list) <= self._max_archive_size:
            return

        keep_count = int(self._max_archive_size * self._retain_ratio)
        recent_count = self._max_archive_size - keep_count

        successful = [p for p in pattern_list if p.success]
        failed = [p for p in pattern_list if not p.success]

        successful.sort(key=lambda x: x.archived_at, reverse=True)
        failed.sort(key=lambda x: x.archived_at, reverse=True)

        kept = successful[:keep_count] + failed[:recent_count]
        kept.sort(key=lambda x: x.archived_at, reverse=True)

        self._archives[pattern_type] = kept

    def archive(
        self,
        pattern_id: str,
        pattern_type: str,
        market_context: Dict[str, Any],
        outcome: Dict[str, Any]
    ):
        """归档模式"""
        if pattern_type not in self._archives:
            self._archives[pattern_type] = []

        success = outcome.get("return", 0) > 0

        archive_entry = PatternArchive(
            pattern_id=pattern_id,
            pattern_type=pattern_type,
            market_context=market_context,
            outcome=outcome,
            success=success,
            archived_at=time.time()
        )

        self._archives[pattern_type].append(archive_entry)

        self._update_index(archive_entry)

        self._cleanup_archive(pattern_type)

    def _update_index(self, archive: PatternArchive):
        """更新索引"""
        symbol = archive.market_context.get("symbol")
        if symbol:
            if symbol not in self._index["by_symbol"]:
                self._index["by_symbol"][symbol] = set()
            self._index["by_symbol"][symbol].add(archive.pattern_id)

        sector = archive.market_context.get("sector")
        if sector:
            if sector not in self._index["by_sector"]:
                self._index["by_sector"][sector] = set()
            self._index["by_sector"][sector].add(archive.pattern_id)

    def recall(
        self,
        pattern_type: Optional[str] = None,
        symbol: Optional[str] = None,
        sector: Optional[str] = None,
        limit: int = 10
    ) -> List[PatternArchive]:
        """
        召回匹配的模式

        按综合权重排序返回
        """
        candidates = []

        if pattern_type and pattern_type in self._archives:
            candidates.extend(self._archives[pattern_type])

        if symbol and symbol in self._index["by_symbol"]:
            pattern_ids = self._index["by_symbol"][symbol]
            for pattern_list in self._archives.values():
                candidates.extend([p for p in pattern_list if p.pattern_id in pattern_ids])

        if sector and sector in self._index["by_sector"]:
            pattern_ids = self._index["by_sector"][sector]
            for pattern_list in self._archives.values():
                candidates.extend([p for p in pattern_list if p.pattern_id in pattern_ids])

        unique_candidates = {id(c): c for c in candidates}.values()

        weighted = []
        for c in unique_candidates:
            weight = self._compute_pattern_weight(c)
            weighted.append((c, weight))

        weighted.sort(key=lambda x: x[1], reverse=True)

        return [c for c, _ in weighted[:limit]]

    def get_archive_stats(self) -> Dict[str, Any]:
        """获取归档统计"""
        stats = {}
        for pattern_type, archives in self._archives.items():
            success_count = sum(1 for p in archives if p.success)
            weights = [self._compute_pattern_weight(p) for p in archives]
            stats[pattern_type] = {
                "total": len(archives),
                "success": success_count,
                "success_rate": success_count / len(archives) if archives else 0,
                "avg_weight": sum(weights) / len(weights) if weights else 0,
            }
        return stats

    PERSISTENCE_TABLE = "naja_pattern_archive"
    PERSISTENCE_KEY = "pattern_archive"

    def save_state(self) -> Dict[str, Any]:
        """保存模式归档状态"""
        if not NB_AVAILABLE:
            return {"success": False, "error": "NB not available"}

        try:
            archives_data = {}
            for pattern_type, archives in self._archives.items():
                archives_data[pattern_type] = [
                    {
                        "pattern_id": p.pattern_id,
                        "pattern_type": p.pattern_type,
                        "market_context": p.market_context,
                        "outcome": p.outcome,
                        "success": p.success,
                        "archived_at": p.archived_at,
                    }
                    for p in archives
                ]

            state_data = {
                "archives": archives_data,
                "_pattern_half_life": self._pattern_half_life,
                "_max_archive_size": self._max_archive_size,
                "_retain_ratio": self._retain_ratio,
                "saved_at": time.time(),
            }
            db = NB(self.PERSISTENCE_TABLE)
            db[self.PERSISTENCE_KEY] = state_data
            return {
                "success": True,
                "total_archives": sum(len(a) for a in self._archives.values()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_state(self) -> Dict[str, Any]:
        """加载模式归档状态"""
        if not NB_AVAILABLE:
            return {"success": False, "error": "NB not available"}

        try:
            db = NB(self.PERSISTENCE_TABLE)
            if self.PERSISTENCE_KEY not in db:
                return {"success": True, "loaded": False, "message": "No saved state"}

            state_data = db.get(self.PERSISTENCE_KEY)

            self._pattern_half_life = state_data.get("_pattern_half_life", 604800.0)
            self._max_archive_size = state_data.get("_max_archive_size", 1000)
            self._retain_ratio = state_data.get("_retain_ratio", 0.5)

            archives_data = state_data.get("archives", {})
            self._archives = {}
            self._index = {"by_symbol": {}, "by_sector": {}, "by_time": {}}

            for pattern_type, pattern_list in archives_data.items():
                self._archives[pattern_type] = []
                for p_data in pattern_list:
                    p = PatternArchive(
                        pattern_id=p_data.get("pattern_id", ""),
                        pattern_type=p_data.get("pattern_type", ""),
                        market_context=p_data.get("market_context", {}),
                        outcome=p_data.get("outcome", {}),
                        success=p_data.get("success", False),
                        archived_at=p_data.get("archived_at", time.time()),
                    )
                    self._archives[pattern_type].append(p)
                    self._update_index(p)

            return {
                "success": True,
                "loaded": True,
                "total_archives": sum(len(a) for a in self._archives.values()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class AwakeningEngine:
    """
    觉醒引擎

    当多个弱信号汇聚时，触发顿悟

    衰减机制设计：
    1. 新鲜度加权：每个信号根据时间衰减
    2. 有效信号分数：confidence * freshness_weight 的加权和
    3. 惰性评估：只在 check_for_awakening 时计算
    """

    def __init__(
        self,
        freshness_half_life: float = 60.0,
        awakening_thresholds: dict = None
    ):
        """
        初始化觉醒引擎

        Args:
            freshness_half_life: 新鲜度半衰期（秒），默认 60
            awakening_thresholds: 觉醒等级阈值配置
        """
        self._weak_signals: deque = deque(maxlen=30)
        self._awakenings: deque = deque(maxlen=50)
        self._awakening_level = AwakeningLevel.DORMANT
        self._freshness_half_life = freshness_half_life
        self._awakening_thresholds = awakening_thresholds or {
            "DORMANT": 3,
            "AWAKENING": 8,
            "ILLUMINATED": 15,
        }
        self._last_evaluation_time: float = time.time()
        self._cached_effective_score: float = 0.0

    def _compute_freshness_weight(self, timestamp: float) -> float:
        """
        计算信号的新鲜度权重

        使用指数衰减：weight = exp(-dt / half_life)
        """
        dt = time.time() - timestamp
        return math.exp(-dt / self._freshness_half_life)

    def _compute_effective_score(self) -> float:
        """
        计算有效信号分数

        有效分数 = sum(confidence * freshness_weight)
        """
        total = 0.0
        for signal in self._weak_signals:
            freshness = self._compute_freshness_weight(signal["timestamp"])
            total += signal.get("confidence", 0.5) * freshness
        return total

    def _count_high_confidence_signals(self) -> int:
        """计算高置信度信号数量（考虑新鲜度）"""
        count = 0
        for signal in self._weak_signals:
            freshness = self._compute_freshness_weight(signal["timestamp"])
            effective_confidence = signal.get("confidence", 0.5) * freshness
            if effective_confidence >= 0.5:
                count += 1
        return count

    def receive_signal(self, signal_type: str, content: str, confidence: float, conditions: Dict[str, Any]):
        """接收弱信号"""
        self._weak_signals.append({
            "type": signal_type,
            "content": content,
            "confidence": confidence,
            "conditions": conditions,
            "timestamp": time.time()
        })

        self._update_awakening_level()

    def _update_awakening_level(self):
        """更新觉醒层次（基于有效信号分数）"""
        effective_score = self._compute_effective_score()
        self._cached_effective_score = effective_score
        self._last_evaluation_time = time.time()

        thresholds = self._awakening_thresholds

        if effective_score < thresholds["DORMANT"]:
            self._awakening_level = AwakeningLevel.DORMANT
        elif effective_score < thresholds["AWAKENING"]:
            self._awakening_level = AwakeningLevel.AWAKENING
        elif effective_score < thresholds["ILLUMINATED"]:
            self._awakening_level = AwakeningLevel.ILLUMINATED
        else:
            high_conf_count = self._count_high_confidence_signals()
            if high_conf_count >= 5:
                self._awakening_level = AwakeningLevel.ENLIGHTENED
            else:
                self._awakening_level = AwakeningLevel.ILLUMINATED

    def check_for_awakening(self) -> Optional[AwakeningSignal]:
        """检查是否顿悟（基于有效信号分数）"""
        effective_score = self._compute_effective_score()

        if effective_score < 5:
            return None

        signals_by_type: Dict[str, float] = {}
        total_conflict_weight = 0.0
        timing_weight = 0.0

        for signal in self._weak_signals:
            freshness = self._compute_freshness_weight(signal["timestamp"])
            weight = signal.get("confidence", 0.5) * freshness

            signal_type = signal.get("type", "unknown")
            if signal_type not in signals_by_type:
                signals_by_type[signal_type] = 0.0
            signals_by_type[signal_type] += weight

            if signal_type == "timing":
                timing_weight += weight

            direction = signal.get("conditions", {}).get("direction", 0)
            if direction != 0:
                for other in self._weak_signals:
                    other_dir = other.get("conditions", {}).get("direction", 0)
                    if other_dir != 0 and direction != other_dir:
                        total_conflict_weight += weight * 0.5

        type_diversity = len([w for w in signals_by_type.values() if w >= 1.0])

        if type_diversity >= 3 and effective_score >= 10:
            return AwakeningSignal(
                signal_type="pattern_match",
                trigger_conditions=[f"{k}:{v:.1f}" for k, v in signals_by_type.items()],
                confidence=min(0.95, 0.6 + effective_score * 0.02),
                illumination_content="多类型信号汇聚，可能存在重大模式机会"
            )

        if total_conflict_weight >= 5:
            return AwakeningSignal(
                signal_type="contradiction",
                trigger_conditions=[f"冲突加权:{total_conflict_weight:.1f}"],
                confidence=min(0.95, 0.7 + total_conflict_weight * 0.03),
                illumination_content="多空信号冲突严重，市场可能即将转折"
            )

        if timing_weight >= 5:
            return AwakeningSignal(
                signal_type="timing",
                trigger_conditions=[f"时机加权:{timing_weight:.1f}"],
                confidence=min(0.9, 0.6 + timing_weight * 0.04),
                illumination_content="多个时机信号共振，入场时机成熟"
            )

        return None

    def _are_conflicting(self, s1: Dict[str, Any], s2: Dict[str, Any]) -> bool:
        """判断两个信号是否冲突"""
        c1 = s1.get("conditions", {}).get("direction", 0)
        c2 = s2.get("conditions", {}).get("direction", 0)

        if c1 != 0 and c2 != 0 and c1 != c2:
            return True

        return False

    def record_outcome(self, awakening: AwakeningSignal, success: bool):
        """记录顿悟结果"""
        awakening.usefulness = 0.8 if success else 0.3
        self._awakenings.append(awakening)

        if success:
            self._awakening_level = AwakeningLevel.ENLIGHTENED

    def get_awakening_level(self) -> str:
        """获取觉醒层次"""
        self._update_awakening_level()
        return self._awakening_level.value

    def get_stats(self) -> Dict[str, Any]:
        """获取引擎统计信息"""
        effective_score = self._compute_effective_score()
        high_conf_count = self._count_high_confidence_signals()

        signals_by_type: Dict[str, int] = {}
        for signal in self._weak_signals:
            t = signal.get("type", "unknown")
            signals_by_type[t] = signals_by_type.get(t, 0) + 1

        return {
            "signal_count": len(self._weak_signals),
            "effective_score": effective_score,
            "awakening_level": self._awakening_level.value,
            "high_confidence_count": high_conf_count,
            "signals_by_type": signals_by_type,
            "freshness_half_life": self._freshness_half_life,
            "awakening_count": len(self._awakenings),
        }

    PERSISTENCE_TABLE = "naja_awakening_engine"
    PERSISTENCE_KEY = "awakening_engine"

    def save_state(self) -> Dict[str, Any]:
        """保存觉醒引擎状态"""
        if not NB_AVAILABLE:
            return {"success": False, "error": "NB not available"}

        try:
            state_data = {
                "weak_signals": list(self._weak_signals),
                "awakenings": [
                    {
                        "signal_type": a.signal_type,
                        "trigger_conditions": a.trigger_conditions,
                        "confidence": a.confidence,
                        "illumination_content": a.illumination_content,
                        "timestamp": a.timestamp,
                        "usefulness": getattr(a, 'usefulness', 0.5),
                    }
                    for a in self._awakenings
                ],
                "_awakening_level": self._awakening_level.value,
                "_freshness_half_life": self._freshness_half_life,
                "_awakening_thresholds": self._awakening_thresholds,
                "_last_evaluation_time": self._last_evaluation_time,
                "_cached_effective_score": self._cached_effective_score,
                "saved_at": time.time(),
            }
            db = NB(self.PERSISTENCE_TABLE)
            db[self.PERSISTENCE_KEY] = state_data
            return {
                "success": True,
                "weak_signals_count": len(self._weak_signals),
                "awakenings_count": len(self._awakenings),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_state(self) -> Dict[str, Any]:
        """加载觉醒引擎状态"""
        if not NB_AVAILABLE:
            return {"success": False, "error": "NB not available"}

        try:
            db = NB(self.PERSISTENCE_TABLE)
            if self.PERSISTENCE_KEY not in db:
                return {"success": True, "loaded": False, "message": "No saved state"}

            state_data = db.get(self.PERSISTENCE_KEY)

            self._weak_signals = deque(
                state_data.get("weak_signals", []),
                maxlen=30
            )
            self._awakening_level = AwakeningLevel(
                state_data.get("_awakening_level", "dormant")
            )
            self._freshness_half_life = state_data.get("_freshness_half_life", 60.0)
            self._awakening_thresholds = state_data.get("_awakening_thresholds", {
                "DORMANT": 3, "AWAKENING": 8, "ILLUMINATED": 15,
            })
            self._last_evaluation_time = state_data.get("_last_evaluation_time", time.time())
            self._cached_effective_score = state_data.get("_cached_effective_score", 0.0)

            awakenings_data = state_data.get("awakenings", [])
            self._awakenings = deque(maxlen=50)
            for a_data in awakenings_data:
                signal = AwakeningSignal(
                    signal_type=a_data.get("signal_type", "unknown"),
                    trigger_conditions=a_data.get("trigger_conditions", []),
                    confidence=a_data.get("confidence", 0.5),
                    illumination_content=a_data.get("illumination_content", ""),
                    timestamp=a_data.get("timestamp", time.time()),
                )
                if "usefulness" in a_data:
                    signal.usefulness = a_data["usefulness"]
                self._awakenings.append(signal)

            return {
                "success": True,
                "loaded": True,
                "weak_signals_count": len(self._weak_signals),
                "awakenings_count": len(self._awakenings),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class AwakenedAlaya:
    """
    觉醒阿赖耶识

    整合光明藏、顿悟引擎、跨市场记忆
    支持 UnifiedManas 持仓盈亏触发顿悟
    """

    def __init__(self):
        self.cross_market_memory = CrossMarketMemory()
        self.pattern_archive = PatternArchiveManager()
        self.awakening_engine = AwakeningEngine()
        self._epiphany_engine = None

        self._integration_count = 0
        self._last_illumination_time = 0.0
        self._alaya_stats = {}

    def set_epiphany_engine(self, epiphany_engine):
        """设置顿悟引擎（用于持仓顿悟）"""
        self._epiphany_engine = epiphany_engine

    def illuminate(
        self,
        market_data: Dict[str, Any],
        signals: Optional[List[Dict[str, Any]]] = None,
        unified_manas_output: Optional[Dict[str, Any]] = None,
        fp_insights: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        照亮模式

        Args:
            market_data: 市场数据
            signals: 信号列表
            unified_manas_output: UnifiedManas 输出（包含持仓信息）
            fp_insights: FirstPrinciples 洞察列表

        Returns:
            包含 illumination, awakenings, archived_patterns 的字典
        """
        with _get_audit()(loop_type="alaya", stage="illuminate", data_in={"market_data_keys": list(market_data.keys()) if market_data else []}) as audit:
            self._integration_count += 1

            if fp_insights:
                self._process_fp_insights(fp_insights)

            awakening_result = self._process_awakening(signals or [])

            portfolio_awakening = self._process_portfolio_awakening(unified_manas_output)

            recalled_patterns = self._recall_relevant_patterns(market_data)

            illumination = self._generate_illumination(
                market_data, recalled_patterns, awakening_result, portfolio_awakening
            )

            if illumination:
                self._last_illumination_time = time.time()

            result = {
                "illumination": illumination,
                "awakening": awakening_result,
                "portfolio_awakening": portfolio_awakening,
                "recalled_patterns": recalled_patterns,
                "awakening_level": self.awakening_engine.get_awakening_level()
            }
            audit.record_data_out({
                "illumination": bool(illumination),
                "recalled_count": len(recalled_patterns) if recalled_patterns else 0,
                "awakening_level": result["awakening_level"]
            })
            return result

    def _process_portfolio_awakening(
        self,
        unified_manas_output: Optional[Dict[str, Any]]
    ) -> Optional[AwakeningSignal]:
        """处理持仓驱动的顿悟"""
        if not unified_manas_output:
            return None

        if self._epiphany_engine is None:
            try:
                from deva.naja.alaya.epiphany_engine import EpiphanyEngine
                self._epiphany_engine = EpiphanyEngine()
            except ImportError:
                return None

        portfolio_loss = unified_manas_output.get("portfolio_loss_pct", 0.0)
        market_deterioration = unified_manas_output.get("market_deterioration", False)
        regime = "unknown"

        regime_score = unified_manas_output.get("regime_score", 0.0)
        if regime_score < -0.3:
            regime = "bear"
        elif regime_score > 0.3:
            regime = "bull"
        else:
            regime = "neutral"

        epiphany = self._epiphany_engine.check_portfolio_epiphany(
            portfolio_loss=portfolio_loss,
            market_deterioration=market_deterioration,
            regime=regime
        )

        if epiphany:
            return AwakeningSignal(
                signal_type=epiphany.epiphany_type,
                trigger_conditions=epiphany.triggered_by,
                confidence=epiphany.confidence,
                illumination_content=epiphany.content
            )

        return None

    def _process_awakening(self, signals: List[Dict[str, Any]]) -> Optional[AwakeningSignal]:
        """处理顿悟"""
        for signal in signals:
            self.awakening_engine.receive_signal(
                signal_type=signal.get("type", "unknown"),
                content=signal.get("content", ""),
                confidence=signal.get("confidence", 0.5),
                conditions=signal.get("conditions", {})
            )

        return self.awakening_engine.check_for_awakening()

    def _process_fp_insights(self, insights: List[Any]) -> None:
        """
        处理 FirstPrinciples 洞察，将其转换为弱信号输入到觉醒引擎

        这让慢思考的洞察能够累积觉醒等级
        """
        for insight in insights:
            try:
                insight_type = insight.insight_type if hasattr(insight, 'insight_type') else str(insight.get('insight_type', 'unknown'))
                insight_level = insight.level.value if hasattr(insight, 'level') else str(insight.get('level', 'unknown'))
                insight_confidence = insight.confidence if hasattr(insight, 'confidence') else float(insight.get('confidence', 0.5))
                insight_content = insight.content if hasattr(insight, 'content') else str(insight.get('content', ''))

                conditions = {
                    "level": insight_level,
                    "from_first_principles": True
                }

                if insight_type == "opportunity":
                    self.awakening_engine.receive_signal(
                        signal_type="fp_opportunity",
                        content=f"[{insight_level}] {insight_content[:80]}",
                        confidence=insight_confidence,
                        conditions=conditions
                    )
                elif insight_type == "risk":
                    self.awakening_engine.receive_signal(
                        signal_type="fp_risk",
                        content=f"[{insight_level}] {insight_content[:80]}",
                        confidence=insight_confidence,
                        conditions=conditions
                    )
                elif insight_type == "causal":
                    self.awakening_engine.receive_signal(
                        signal_type="fp_causal",
                        content=f"[{insight_level}] {insight_content[:80]}",
                        confidence=insight_confidence,
                        conditions=conditions
                    )
                elif insight_type == "contradiction":
                    self.awakening_engine.receive_signal(
                        signal_type="fp_contradiction",
                        content=f"矛盾: {insight_content[:80]}",
                        confidence=insight_confidence,
                        conditions=conditions
                    )

                self._alaya_stats["fp_insights_processed"] = self._alaya_stats.get("fp_insights_processed", 0) + 1

            except Exception:
                pass

    def _recall_relevant_patterns(self, market_data: Dict[str, Any]) -> List[PatternArchive]:
        """召回相关模式"""
        symbol = market_data.get("symbol")
        sector = market_data.get("sector")
        pattern_type = market_data.get("pattern_type")

        patterns = self.pattern_archive.recall(
            pattern_type=pattern_type,
            symbol=symbol,
            sector=sector
        )

        cross_patterns = self.cross_market_memory.recall_applicable_patterns(
            target_market="a_stock",
            current_conditions=market_data
        )

        return patterns[:5]

    def _generate_illumination(
        self,
        market_data: Dict[str, Any],
        recalled_patterns: List[PatternArchive],
        awakening: Optional[AwakeningSignal],
        portfolio_awakening: Optional[AwakeningSignal] = None
    ) -> Optional[Dict[str, Any]]:
        """生成照亮结果"""
        if not recalled_patterns and not awakening and not portfolio_awakening:
            return None

        content_parts = []

        if awakening:
            content_parts.append(f"顿悟: {awakening.illumination_content}")
            content_parts.append(f"置信度: {awakening.confidence:.2f}")

        if portfolio_awakening:
            content_parts.append(f"持仓顿悟: {portfolio_awakening.illumination_content}")
            content_parts.append(f"持仓置信度: {portfolio_awakening.confidence:.2f}")

        if recalled_patterns:
            avg_success_rate = sum(1 for p in recalled_patterns if p.success) / len(recalled_patterns)
            content_parts.append(f"历史模式匹配数: {len(recalled_patterns)}, 成功率: {avg_success_rate:.1%}")

        return {
            "content": " | ".join(content_parts),
            "awakening": awakening,
            "patterns": [
                {
                    "pattern_id": p.pattern_id,
                    "type": p.pattern_type,
                    "success": p.success
                }
                for p in recalled_patterns[:3]
            ],
            "timestamp": time.time()
        }

    def archive_pattern(
        self,
        pattern_id: str,
        pattern_type: str,
        market_context: Dict[str, Any],
        outcome: Dict[str, Any]
    ):
        """归档模式"""
        self.pattern_archive.archive(pattern_id, pattern_type, market_context, outcome)

        if outcome.get("return", 0) > 0.05:
            self.cross_market_memory.store_success_pattern(
                source_market=market_context.get("source_market", "a_stock"),
                pattern={
                    "pattern_id": pattern_id,
                    "conditions": market_context
                }
            )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "integration_count": self._integration_count,
            "awakening_level": self.awakening_engine.get_awakening_level(),
            "pattern_archive": self.pattern_archive.get_archive_stats(),
            "cross_market_sources": list(self.cross_market_memory._source_memories.keys())
        }
