"""
BlindSpotInvestigator - 盲区主动探究器

═══════════════════════════════════════════════════════════════════════════
                              架 构 定 位
═══════════════════════════════════════════════════════════════════════════

【被动发现层】BlindSpotInvestigator 是外部热点的被动发现机制

    当 ConvictionValidator 检测到 blind_spot（外部热 ∩ 我们没关注）时
    → BlindSpotInvestigator 被触发
    → 追溯热度背后的根因
    → 找到解决者（resolver）
    → 通过 FocusManager 自动加入关注
    → 下一轮融合时，这些block进入"我们的"系统

═══════════════════════════════════════════════════════════════════════════
                              核 心 流 程
═══════════════════════════════════════════════════════════════════════════

    ConvictionValidator 检测 blind_spot
              ↓
    BlindSpotInvestigator.investigate(block_id)
              ↓
    ┌────────────────────────────────────────┐
    │ 1. _infer_narrative_from_block()       │
    │    推断该block关联的叙事                │
    └────────────────────────────────────────┘
              ↓
    ┌────────────────────────────────────────┐
    │ 2. _get_causal_info(narrative)         │
    │    从 CAUSAL_KNOWLEDGE 获取根因知识     │
    │    · root_cause: 根本原因               │
    │    · causal_chain: 因果链              │
    │    · resolvers: 解决者股票列表          │
    └────────────────────────────────────────┘
              ↓
    ┌────────────────────────────────────────┐
    │ 3. _auto_follow_stocks(resolvers)      │
    │    FocusManager.follow_stock()         │
    │    → 自动关注解决者股票                 │
    └────────────────────────────────────────┘
              ↓
    ┌────────────────────────────────────────┐
    │ 4. _auto_follow_narratives()           │
    │    FocusManager.follow_narrative()     │
    │    → 自动关注叙事                       │
    └────────────────────────────────────────┘
              ↓
    ┌────────────────────────────────────────┐
    │ 5. _make_recommendation()              │
    │    生成推荐：follow_stock/narrative/..  │
    └────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
                              知 识 库
═══════════════════════════════════════════════════════════════════════════

CAUSAL_KNOWLEDGE 包含预定义的叙事因果链：
    AI, 芯片, 新能源, 固态电池, 光刻机, 云计算,
    自动驾驶, 机器人, 量子计算, 半导体

每个条目包含：
    root_cause        = 根本原因描述
    causal_chain      = 因果链（问题→机会→解决者）
    resolvers         = 解决者股票列表
    investigation_prompt = 探究提示

═══════════════════════════════════════════════════════════════════════════
                              叙 事 别 名
═══════════════════════════════════════════════════════════════════════════

NARRATIVE_ALIAS_MAP 处理中英文别名：
    new_energy → 新能源
    ai → AI
    chip → 芯片
    ...

═══════════════════════════════════════════════════════════════════════════
                              与天道发现的关系
═══════════════════════════════════════════════════════════════════════════

【主动发现-天道】 NarrativeTracker.get_value_market_summary()
    - 我们主动检测外部事件中的价值信号
    - 基于 TIANDAO_KEYWORDS 命中
    - "替天行道"的天道

【被动发现-盲区】 BlindSpotInvestigator
    - ConvictionValidator 触发，我们被动响应
    - 基于 CAUSAL_KNOWLEDGE 推理
    - 外部热但我们没关注 → 必须探究

两者都是"认知扩展"机制，区别在于触发方式不同。
"""

from __future__ import annotations
import time
from typing import Dict, List, Optional, Set, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from deva.naja.attention.focus_manager import AttentionFocusManager, FocusItem
    from deva.naja.cognition.narrative_tracker import NarrativeTracker


CAUSAL_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
    "AI": {
        "root_cause": "大模型能力爆发 + 算力成本下降 + 应用场景爆发",
        "causal_chain": ["GPT-4发布", "API降价", "应用爆发", "算力需求激增"],
        "resolvers": ["NVDA", "AMD", "MSFT", "GOOGL", "AMZN"],
        "investigation_prompt": "为什么AI叙事突然变热？背后的供需逻辑是什么？",
    },
    "芯片": {
        "root_cause": "先进制程受限 + AI芯片需求爆发 + 国产替代加速",
        "causal_chain": ["美国制裁", "AI需求爆发", "国产替代", "产能扩张"],
        "resolvers": ["华为昇腾", "寒武纪", "台积电", "日月光"],
        "investigation_prompt": "芯片供需问题的根本原因是什么？谁能解决这个问题？",
    },
    "新能源": {
        "root_cause": "碳中和政策 + 锂电池成本下降 + 电车渗透率快速提升",
        "causal_chain": ["政策推动", "成本下降", "需求爆发", "产能扩张"],
        "resolvers": ["宁德时代", "比亚迪", "特斯拉", "LG新能源"],
        "investigation_prompt": "新能源供需失衡的根因是什么？技术突破在哪里？",
    },
    "固态电池": {
        "root_cause": "续航焦虑 + 能量密度瓶颈 + 固态电解质技术接近量产",
        "causal_chain": ["电车续航问题", "液态电池安全隐患", "固态电解质突破", "量产临近"],
        "resolvers": ["QuantumScape", "丰田", "宁德时代", "比亚迪"],
        "investigation_prompt": "固态电池为什么突然受关注？量产时间线是什么？",
    },
    "光刻机": {
        "root_cause": "EUV技术垄断 + 先进制程需求 + 国产替代迫切",
        "causal_chain": ["美国制裁", "EUV禁运", "国产替代", "技术攻关"],
        "resolvers": ["ASML", "上海微电子", "中芯国际"],
        "investigation_prompt": "光刻机卡脖子的根因是什么？国产替代进度如何？",
    },
    "云计算": {
        "root_cause": "企业数字化转型 + AI需求 + 边缘计算兴起",
        "causal_chain": ["数字化转型", "AI渗透率提升", "云需求爆发", "资本开支增加"],
        "resolvers": ["AWS", "Azure", "阿里云", "腾讯云"],
        "investigation_prompt": "云计算高速增长的驱动因素是什么？竞争格局如何？",
    },
    "自动驾驶": {
        "root_cause": "视觉算法突破 + 激光雷达成本下降 + 法规逐步开放",
        "causal_chain": ["算法进步", "传感器降价", "政策开放", "商业化加速"],
        "resolvers": ["特斯拉", "Waymo", "小马智行", "百度Apollo"],
        "investigation_prompt": "自动驾驶商业化落地的关键是什么？",
    },
    "机器人": {
        "root_cause": "劳动力短缺 + 灵巧操作AI突破 + 本体成本下降",
        "causal_chain": ["人口老龄化", "用工成本上升", "AI视觉突破", "本体降价"],
        "resolvers": ["Tesla", "Figure", "宇树科技", "追觅科技"],
        "investigation_prompt": "人形机器人为什么现在火？产业链受益环节是什么？",
    },
    "半导体设备": {
        "root_cause": "国产替代紧迫 + 先进制程突破 + 资本大力投入",
        "causal_chain": ["美国制裁", "国产替代加速", "设备需求激增", "技术突破"],
        "resolvers": ["中微公司", "北方华创", "拓荆科技", "华海清科"],
        "investigation_prompt": "半导体设备国产化的卡点在哪里？谁能突破？",
    },
    "AI应用": {
        "root_cause": "大模型能力溢出 + 垂直场景落地 + 商业模式跑通",
        "causal_chain": ["大模型开源", "API成本下降", "垂直场景验证", "规模化复制"],
        "resolvers": ["OpenAI", "Anthropic", "Character.AI", "Jasper"],
        "investigation_prompt": "AI应用层的机会在哪里？什么场景最先商业化？",
    },
}


@dataclass
class InvestigationResult:
    """
    【被动发现层】盲区探究结果

    字段说明：
        block_id               = 被探究的block
        narrative              = 关联的叙事
        root_cause            = 根因（从CAUSAL_KNOWLEDGE获取）
        causal_chain          = 因果链
        resolvers             = 解决者股票列表
        auto_followed_stocks  = 自动关注的股票（通过FocusManager）
        auto_followed_narratives = 自动关注的叙事
        investigation_confidence = 探究置信度
        is_actionable         = 是否可操作（有resolver）
        recommendation        = 推荐操作
        investigation_prompt  = 探究提示
    """
    block_id: str                                    # 【输入】block标识
    narrative: str                                   # 【推理】关联叙事
    root_cause: str                                  # 【根因】根本原因
    causal_chain: List[str]                          # 【因果】因果链
    resolvers: List[str]                             # 【解决者】解决者股票
    auto_followed_stocks: List[str]                  # 【执行】自动关注股票
    auto_followed_narratives: List[str]              # 【执行】自动关注叙事
    investigation_confidence: float                   # 【质量】置信度
    is_actionable: bool                              # 【决策】是否可操作
    recommendation: str                              # 【决策】推荐操作
    investigation_prompt: str                         # 【参考】探究提示
    timestamp: float = field(default_factory=time.time)


@dataclass
class BatchInvestigationResult:
    """
    【被动发现层】批量探究结果

    用于investigate_all()对多个blind_spot批量探究
    """
    investigations: List[InvestigationResult]         # 各blind_spot的探究结果
    total_investigated: int                         # 探究总数
    actionable_count: int                            # 可操作数量
    new_discoveries: List[str]                       # 新发现
    suggestions: List[Dict[str, Any]]                # 建议


class BlindSpotInvestigator:
    """
    【被动发现层】盲区主动探究器

    当 ConvictionValidator 检测到 blind_spot（外部热 ∩ 我们没关注）时：
    1. 主动探究热度背后的根因（调用 CAUSAL_KNOWLEDGE）
    2. 找到可能的解决者公司
    3. 自动 follow_stock(解决者) + follow_narrative(相关叙事)
    4. 输出探究结果供融合层使用

    与天道发现（NarrativeTracker.get_value_market_summary）的区别：
        天道发现 = 我们主动看外部事件，找价值信号
        盲区发现 = ConvictionValidator 触发，我们被动响应外部热点

    使用方式:

        investigator = BlindSpotInvestigator()

        result = investigator.investigate("固态电池")

        print(f"根因: {result.root_cause}")
        print(f"解决者: {result.resolvers}")
        print(f"已自动关注: {result.auto_followed_stocks}")
    """

    _instance: Optional["BlindSpotInvestigator"] = None

    def __new__(cls) -> "BlindSpotInvestigator":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        focus_manager: Optional["AttentionFocusManager"] = None,
        narrative_tracker: Optional["NarrativeTracker"] = None,
    ):
        if self._initialized:
            return

        from deva.naja.attention.focus_manager import get_attention_focus_manager
        from deva.naja.cognition.narrative_tracker import get_narrative_tracker

        self._focus_manager = focus_manager or get_attention_focus_manager()
        self._narrative_tracker = narrative_tracker or get_narrative_tracker()
        self._investigation_cache: Dict[str, InvestigationResult] = {}
        self._cache_ttl: float = 3600.0
        self._initialized = True

    def investigate(
        self,
        block_id: str,
        narrative: Optional[str] = None,
        force_refresh: bool = False,
    ) -> InvestigationResult:
        """
        探究一个盲区热点

        Args:
            block_id: 被检测为盲区的 block_id
            narrative: 可选，该 block 对应的叙事
            force_refresh: 是否强制刷新缓存

        Returns:
            InvestigationResult: 包含根因、解决者、自动关注结果
        """
        cache_key = f"{block_id}:{narrative or ''}"
        if not force_refresh and cache_key in self._investigation_cache:
            cached = self._investigation_cache[cache_key]
            if time.time() - cached.timestamp < self._cache_ttl:
                return cached

        if narrative is None:
            narrative = self._infer_narrative_from_block(block_id)

        causal_info = self._get_causal_info(narrative)

        resolvers = list(causal_info.get("resolvers", []))
        root_cause = causal_info.get("root_cause", "")
        causal_chain = causal_info.get("causal_chain", [])
        investigation_prompt = causal_info.get(
            "investigation_prompt", f"为什么 {block_id} 突然变热？"
        )

        auto_followed_stocks = self._auto_follow_stocks(resolvers)
        auto_followed_narratives = self._auto_follow_narratives(narrative, block_id)

        confidence = self._compute_confidence(
            root_cause, resolvers, len(causal_chain)
        )

        is_actionable = len(resolvers) > 0 and len(root_cause) > 0

        recommendation = self._make_recommendation(
            auto_followed_stocks, auto_followed_narratives, is_actionable
        )

        result = InvestigationResult(
            block_id=block_id,
            narrative=narrative or "未知",
            root_cause=root_cause,
            causal_chain=causal_chain,
            resolvers=resolvers,
            auto_followed_stocks=auto_followed_stocks,
            auto_followed_narratives=auto_followed_narratives,
            investigation_confidence=confidence,
            is_actionable=is_actionable,
            recommendation=recommendation,
            investigation_prompt=investigation_prompt,
        )

        self._investigation_cache[cache_key] = result
        return result

    def investigate_all(
        self,
        blind_spot_blocks: List[Any],
    ) -> BatchInvestigationResult:
        """
        批量探究所有盲区

        Args:
            blind_spot_blocks: List[(block_id, attention_score)] 或 List[str]
        """
        investigations: List[InvestigationResult] = []
        new_discoveries: List[str] = []
        suggestions: List[Dict[str, Any]] = []

        for item in blind_spot_blocks:
            if isinstance(item, (list, tuple)):
                block_id = item[0]
                attention_score = item[1] if len(item) > 1 else 0.0
            else:
                block_id = str(item)
                attention_score = 0.0

            result = self.investigate(block_id)
            investigations.append(result)

            if result.is_actionable:
                if result.auto_followed_stocks:
                    new_discoveries.extend(result.auto_followed_stocks)

                if result.investigation_confidence > 0.7:
                    suggestions.append({
                        "block_id": result.block_id,
                        "root_cause": result.root_cause,
                        "resolvers": result.resolvers,
                        "confidence": result.investigation_confidence,
                        "recommendation": result.recommendation,
                    })

        actionable_count = sum(1 for r in investigations if r.is_actionable)

        return BatchInvestigationResult(
            investigations=investigations,
            total_investigated=len(investigations),
            actionable_count=actionable_count,
            new_discoveries=list(set(new_discoveries)),
            suggestions=suggestions,
        )

    NARRATIVE_ALIAS_MAP: Dict[str, str] = {
        "new_energy": "新能源",
        "ai": "AI",
        "a_i": "AI",
        "chip": "芯片",
        "semiconductor": "半导体",
        "cloud_compute": "云算力",
        "cloud_ai": "云AI",
        "robot": "机器人",
        "quantum": "量子计算",
        "solid_state_battery": "固态电池",
    }

    def _infer_narrative_from_block(self, block_id: str) -> str:
        """从 block_id 推断关联的叙事"""
        try:
            linked = self._narrative_tracker.get_linked_blocks(block_id)
            if linked:
                return linked[0] if isinstance(linked, list) else str(linked)
        except Exception:
            pass

        block_lower = block_id.lower()
        if block_lower in self.NARRATIVE_ALIAS_MAP:
            return self.NARRATIVE_ALIAS_MAP[block_lower]

        known_narratives = list(CAUSAL_KNOWLEDGE.keys())
        for narrative in known_narratives:
            if narrative in block_lower or block_lower in narrative:
                return narrative

        return block_id

    def _get_causal_info(self, narrative: str) -> Dict[str, Any]:
        """获取叙事的因果知识"""
        # 首先检查是否直接匹配（已经是中文key）
        if narrative in CAUSAL_KNOWLEDGE:
            return CAUSAL_KNOWLEDGE[narrative]

        # 检查是否是英文别名，需要映射到中文key
        narrative_lower = narrative.lower()
        if narrative_lower in self.NARRATIVE_ALIAS_MAP:
            resolved = self.NARRATIVE_ALIAS_MAP[narrative_lower]
            if resolved in CAUSAL_KNOWLEDGE:
                return CAUSAL_KNOWLEDGE[resolved]

        known_narratives = list(CAUSAL_KNOWLEDGE.keys())
        for known in known_narratives:
            if known in narrative or narrative in known:
                return CAUSAL_KNOWLEDGE[known]

        return {
            "root_cause": f"{narrative}供需关系发生变化",
            "causal_chain": ["需求变化", "供给调整", "价格变动"],
            "resolvers": [],
            "investigation_prompt": f"为什么 {narrative} 变热？背后的供需逻辑是什么？",
        }

    def _auto_follow_stocks(self, resolvers: List[str]) -> List[str]:
        """自动关注解决者股票"""
        followed = []
        for resolver in resolvers:
            try:
                self._focus_manager.follow_stock(
                    stock_code=resolver,
                    priority=0.6,
                    source="investigation",
                    as_watchlist=True,
                )
                followed.append(resolver)
            except Exception:
                pass
        return followed

    def _auto_follow_narratives(
        self, narrative: str, block_id: str
    ) -> List[str]:
        """自动关注相关叙事"""
        followed = []
        if narrative and not self._focus_manager.is_watched_narrative(narrative):
            try:
                self._focus_manager.follow_narrative(
                    narrative=narrative,
                    priority=0.5,
                    source="investigation",
                )
                followed.append(narrative)
            except Exception:
                pass
        return followed

    def _compute_confidence(
        self,
        root_cause: str,
        resolvers: List[str],
        chain_length: int,
    ) -> float:
        """计算探究置信度"""
        score = 0.0
        if root_cause:
            score += 0.3
        if len(resolvers) >= 3:
            score += 0.4
        elif len(resolvers) >= 1:
            score += 0.2
        if chain_length >= 3:
            score += 0.3
        elif chain_length >= 1:
            score += 0.1
        return min(1.0, score)

    def _make_recommendation(
        self,
        followed_stocks: List[str],
        followed_narratives: List[str],
        is_actionable: bool,
    ) -> str:
        """生成推荐动作"""
        if not is_actionable:
            return "no_action"
        if followed_stocks and followed_narratives:
            return "follow_stock_and_narrative"
        elif followed_stocks:
            return "follow_stock"
        elif followed_narratives:
            return "follow_narrative"
        return "monitor"

    def get_investigation_prompt(self, block_id: str) -> str:
        """获取探究提示词"""
        result = self.investigate(block_id)
        return result.investigation_prompt

    def get_root_cause(self, block_id: str) -> str:
        """获取根因"""
        result = self.investigate(block_id)
        return result.root_cause

    def get_resolvers(self, block_id: str) -> List[str]:
        """获取解决者"""
        result = self.investigate(block_id)
        return result.resolvers

    def invalidate_cache(self, block_id: Optional[str] = None) -> None:
        """使缓存失效"""
        if block_id:
            keys_to_remove = [
                k for k in self._investigation_cache.keys()
                if k.startswith(block_id)
            ]
            for k in keys_to_remove:
                del self._investigation_cache[k]
        else:
            self._investigation_cache.clear()


_investigator_instance: Optional[BlindSpotInvestigator] = None


def get_blind_spot_investigator() -> BlindSpotInvestigator:
    """获取 BlindSpotInvestigator 单例"""
    global _investigator_instance
    if _investigator_instance is None:
        _investigator_instance = BlindSpotInvestigator()
    return _investigator_instance
