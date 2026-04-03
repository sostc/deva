"""NarrativeTracker - 认知系统/叙事追踪/故事追踪

别名/关键词: 叙事、故事、市场叙事、narrative、story tracking
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple


DEFAULT_NARRATIVE_KEYWORDS: Dict[str, List[str]] = {
    "AI": [
        "AI", "AIGC", "人工智能", "大模型", "多模态", "生成式", "GPT", "ChatGPT", "Sora",
        "算力", "智能体", "机器人", "自动驾驶", "NLP", "语音", "视觉",
        "LLM", "Agent", "RAG", "向量数据库", "Embedding",
        "OpenAI", "Anthropic", "Claude", "Gemini",
        "文心一言", "通义千问", "Kimi", "豆包", "智谱清言", "百川", "零一",
        "昇腾", "昆仑", "寒武纪", "燧原",
        "AI手机", "AI PC", "端侧AI", "边缘AI", "AI应用",
    ],
    "芯片": [
        "芯片", "半导体", "集成电路", "晶圆", "光刻", "EDA", "封测", "制程", "GPU", "CPU",
        "HBM", "DRAM", "NAND", "SoC", "ASIC", "FPGA", "存储",
        "先进封装", "CoWoS", "HBM3", "HBM3e",
        "英伟达", "AMD", "英特尔", "高通", "联发科", "博通",
        "台积电", "三星", "中芯国际", "华虹半导体",
    ],
    "天道": [
        "设备交付延迟", "AI改造", "限流", "训练成本下降", "降本增效", "良品率", "限速", "token不够", "渗透率", "API调用量增长",
        "token消耗", "算力短缺", "GPU排队", "算力不足",
        "API限流", "ChatGPT限流", "Claude限流", "Gemini限流",
        "模型服务不可用", "服务器过载", "负载过高",
        "卡脖子", "产能不足", "良品率", "HBM缺货",
        "EUV产能", "先进封装产能", "CoWoS满载", "封装排队",
        "晶圆厂产能满", "产能告急", "设备交付延迟",
        "性能提升", "成本下降", "新一代", "突破", "效率提升",
        "推理加速", "训练成本下降", "功耗降低", "算力翻倍",
        "新架构", "技术创新", "技术路线突破",
        "渗透率", "落地", "商业化", "盈利", "行业AI化",
        "AI改造", "降本增效", "收入增长",
        "付费转化", "用户增长", "API调用量增长",
    ],
    "民心": [
        "上涨", "下跌", "大涨", "大跌", "暴涨", "暴跌",
        "牛市", "熊市", "反弹", "回调", "震荡",
        "资金流入", "资金流出", "净流入", "净流出",
        "市场认为", "分析师称", "机构表示", "情绪乐观",
        "情绪悲观", "恐慌", "贪婪", "风险偏好",
        "避险", "风险情绪", "市场信心",
        "热门", "热搜", "刷屏", "引爆", "疯狂",
        "泡沫", "投机", "炒作", "概念股",
    ],
    "新能源": [
        "新能源", "光伏", "风电", "储能", "锂电", "电池", "充电桩", "氢能", "碳中和", "碳达峰",
        "新能源车", "电动车", "逆变器", "光伏逆变器",
        "宁德时代", "比亚迪", "亿纬锂能", "国轩高科",
        "隆基绿能", "通威股份", "阳光电源", "晶澳科技",
        "特斯拉", "理想汽车", "蔚来汽车", "小鹏汽车",
    ],
    "医药": [
        "医药", "生物医药", "创新药", "疫苗", "医疗", "医疗器械", "临床", "试验", "基因",
        "细胞治疗", "CXO", "医院", "药品", "药企",
        "创新药", "仿制药", "中药", "生物药", "ADC", "双抗", "CAR-T",
        "恒瑞医药", "百济神州", "君实生物", "信达生物",
    ],
    "华为": [
        "华为", "昇腾", "鸿蒙", "HarmonyOS", "Harmony", "麒麟芯片",
        "鲲鹏", "昇思", "华为云", "HiCar", "智能驾驶",
        "Mate", "P系列", "问界", "智界",
    ],
    "中美关系": [
        "关税", "制裁", "贸易战", "出口管制", "实体清单", "黑名单",
        "美国商务部", "BIS", "EAR", "FDPR",
        "中美关系", "中美贸易", "美中", "中美会谈", "战略对话",
    ],
    "地缘政治": [
        "伊朗", "以色列", "中东", "霍尔木兹海峡", "红海",
        "俄乌", "乌克兰", "俄罗斯", "北约",
        "朝鲜", "朝鲜半岛", "韩朝", "台海",
        "巴以", "加沙", "耶路撒冷", "联合国安理会",
    ],
    "贵金属": [
        "黄金", "白银", "铂金", "钯金", "金价", "银价",
        "COMEX", "伦敦金", "现货金", "国际金", "黄金期货",
        "黄金ETF", "黄金股", "金币", "金条",
        "央行购金", "黄金储备", "黄金突破", "黄金下跌",
    ],
    "外汇与美元": [
        "美元", "美元指数", "DXY", "USD", "欧元", "EUR", "日元", "JPY",
        "英镑", "GBP", "人民币", "CNY", "离岸人民币", "在岸人民币",
        "美元兑", "美元走强", "美元走弱", "美元反弹", "美元回落",
        "美联储", "Fed", "利率决策", "加息", "降息", "鲍威尔",
    ],
    "经济增长": [
        "GDP", "国内生产总值", "经济增速", "经济增长", "经济扩张", "经济放缓", "经济衰退",
        "PMI", "制造业 PMI", "服务业 PMI", "非制造业 PMI", "采购经理指数",
        "非农", "非农就业", "就业人数", "失业率", "初请失业金", "续请失业金",
        "零售销售", "消费数据", "社会消费品", "零售额",
        "工业产出", "工业增加值", "制造业产出",
        "耐用品订单", "资本品订单",
        "新屋开工", "成屋销售", "营建许可",
        "消费者信心", "密歇根信心", "消费者预期",
        "经济领先指标", "经济同步指标", "经济滞后指标",
        "软着陆", "硬着陆", "经济复苏", "经济过热",
    ],
    "通胀数据": [
        "CPI", "消费者物价指数", "通胀率", "通胀数据", "物价指数",
        "核心 CPI", "核心通胀", "通胀预期",
        "PCE", "个人消费支出", "核心 PCE", "美联储通胀目标",
        "PPI", "生产者物价指数", "出厂价格", "投入价格",
        "薪资增长", "工资增速", "平均时薪", "就业成本指数",
        "通胀压力", "通胀飙升", "通胀降温", "通胀见顶",
        "通胀目标", "通胀中枢", "通胀粘性",
        "超级通胀", "恶性通胀", "通缩", "通货紧缩",
    ],
    "全球宏观": [
        "全球市场", "全球流动性", "金融危机", "经济衰退", "硬着陆", "软着陆",
        "OECD", "IMF", "世界银行", "G20", "G7",
        "美股", "纳斯达克", "标普", "道琼斯", "日经", "恒生", "欧股",
        "债券市场", "信用利差", "高收益债", "投资级债",
    ],
    "债券市场": [
        "美债", "国债", "国债收益率", "十年期国债", "两年期国债", "三十年期国债",
        "收益率曲线", "收益率倒挂", "收益率曲线陡峭", "收益率曲线平坦",
        "债券价格", "债券上涨", "债券下跌", "债券牛市", "债券熊市",
        "长期国债", "短期国债", "中期国债", "国开行", "政策性银行",
        "企业债", "公司债", "城投债", "信用债", "利率债",
        "配置资金", "交易资金", "机构买入", "机构卖出",
        "债券回购", "逆回购", "公开市场操作", "OMO",
        "TIPS", "通胀保值债券", "垃圾债", "投资级",
        "美债收益率", "中债收益率", "德债收益率", "日债收益率",
    ],
    "股票市场": [
        "美股", "纳斯达克", "标普500", "标普", "道琼斯", "道指", "罗素2000",
        "日经225", "日经指数", "恒生指数", "恒生", "上证指数", "上证", "深证",
        "欧股", "德国DAX", "法国CAC", "英国富时",
        "科技股", "成长股", "价值股", "蓝筹股", "白马股",
        "小盘股", "中盘股", "大盘股", "微盘股",
        "A股", "港股", "美股三大指数", "美股市场",
        "股市上涨", "股市下跌", "股市反弹", "股市回调", "股市崩盘",
        "资金流入股市", "资金流出股市", "股市估值", "股市泡沫",
    ],
    "大宗商品": [
        "原油", "布伦特原油", "WTI原油", "原油期货", "原油价格", "原油上涨", "原油下跌",
        "天然气", "液化天然气", "LNG", "天然气价格",
        "铜", "铝", "锌", "镍", "铅", "锡", "铁矿石", "螺纹钢", "钢材",
        "煤炭", "焦煤", "动力煤", "焦炭",
        "大豆", "玉米", "小麦", "稻米", "农产品", "大宗商品",
        "商品指数", "CRB指数", "彭博商品指数", "高盛商品指数",
        "商品上涨", "商品下跌", "商品牛市", "商品熊市",
        "供需关系", "库存下降", "库存上升", "产能不足", "产能过剩",
        "OPEC", "沙特", "俄罗斯石油", "伊朗石油", "石油出口",
        "工业金属", "贵金属", "农产品", "能源商品",
    ],
    "现金与货币": [
        "现金", "货币市场", "货币基金", "余额宝", "理财",
        "银行理财", "短期理财", "定期存款", "大额存单",
        "逆回购", "短期拆借", "隔夜利率", "超额准备金",
        "M0", "M1", "M2", "广义货币", "狭义货币",
        "央行资产负债表", "缩表", "扩表", "量化宽松", "QE",
        "流动性投放", "流动性回收", "资金空转", "套利",
        "美元流动性", "离岸美元", "欧洲美元", "美元荒",
        "货币宽松", "货币紧缩", "银根收紧", "银根放松",
        "降准", "升准", "存款准备金", "法定准备金",
    ],
    "流动性紧张": [
        "流动性", "流动性紧张", "流动性危机", "资金面", "资金紧张",
        "银行间隔夜拆借", "回购利率", "SHIBOR", "LIBOR", "SOFR",
        "融资", "融资融券", "两融", "保证金", "强平", "平仓",
        "爆仓", "追加保证金", "Margin Call", "Call 贷",
        "量化踩踏", "流动性踩踏", "闪崩", "乌龙指",
    ],
}

TIANDAO_KEYWORDS: Dict[str, List[str]] = {
    "token供需": [
        "限流", "限速", "token不够", "算力告急", "API排队",
        "token消耗", "算力短缺", "GPU排队", "算力不足",
        "API限流", "ChatGPT限流", "Claude限流", "Gemini限流",
        "模型服务不可用", "服务器过载", "负载过高",
    ],
    "技术瓶颈": [
        "卡脖子", "产能不足", "良品率", "光刻机", "HBM缺货",
        "EUV产能", "先进封装产能", "CoWoS满载", "封装排队",
        "晶圆厂产能满", "产能告急", "设备交付延迟",
    ],
    "效率突破": [
        "性能提升", "成本下降", "新一代", "突破", "效率提升",
        "推理加速", "训练成本下降", "功耗降低", "算力翻倍",
        "新架构", "技术创新", "技术路线突破",
    ],
    "AI落地": [
        "渗透率", "落地", "商业化", "盈利", "效率提升",
        "行业AI化", "AI改造", "降本增效", "收入增长",
        "付费转化", "用户增长", "API调用量增长",
    ],
}

MINXIN_KEYWORDS: Dict[str, List[str]] = {
    "行情涨跌": [
        "上涨", "下跌", "大涨", "大跌", "暴涨", "暴跌",
        "牛市", "熊市", "反弹", "回调", "震荡",
        "资金流入", "资金流出", "净流入", "净流出",
    ],
    "市场情绪": [
        "市场认为", "分析师称", "机构表示", "情绪乐观",
        "情绪悲观", "恐慌", "贪婪", "风险偏好",
        "避险", "风险情绪", "市场信心",
    ],
    "舆论热点": [
        "热门", "热搜", "刷屏", "引爆", "疯狂",
        "泡沫", "投机", "炒作", "概念股",
    ],
}


NARRATIVE_PERSISTENCE_TABLE = "naja_narrative_tracker_state"
MAX_PERSIST_STATES = 10
MAX_PERSIST_HITS = 50


@dataclass
class NarrativeState:
    name: str
    stage: str = "萌芽"
    attention_score: float = 0.0
    total_count: int = 0
    recent_count: int = 0
    trend: float = 0.0
    last_updated: float = 0.0
    last_stage_change: float = 0.0
    hits: Deque[Tuple[float, float, List[str]]] = field(default_factory=deque)
    last_keywords: List[str] = field(default_factory=list)
    last_emit: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "name": self.name,
            "stage": self.stage,
            "attention_score": self.attention_score,
            "total_count": self.total_count,
            "recent_count": self.recent_count,
            "trend": self.trend,
            "last_updated": self.last_updated,
            "last_stage_change": self.last_stage_change,
            "hits": list(self.hits),
            "last_keywords": self.last_keywords,
            "last_emit": self.last_emit,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeState":
        """从字典反序列化"""
        state = cls(name=data["name"])
        state.stage = data.get("stage", "萌芽")
        state.attention_score = data.get("attention_score", 0.0)
        state.total_count = data.get("total_count", 0)
        state.recent_count = data.get("recent_count", 0)
        state.trend = data.get("trend", 0.0)
        state.last_updated = data.get("last_updated", 0.0)
        state.last_stage_change = data.get("last_stage_change", 0.0)
        state.hits = Deque(data.get("hits", []))
        state.last_keywords = data.get("last_keywords", [])
        state.last_emit = data.get("last_emit", {})
        return state


class NarrativeTracker:
    """Track narrative lifecycle, attention, and relationship graph."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("narrative_enabled", True))
        self._keywords = cfg.get("narrative_keywords") or DEFAULT_NARRATIVE_KEYWORDS
        self._recent_window = float(cfg.get("narrative_recent_window_seconds", 6 * 3600))
        self._prev_window = float(cfg.get("narrative_prev_window_seconds", 6 * 3600))
        self._history_window = float(cfg.get("narrative_history_window_seconds", 72 * 3600))
        self._graph_window = float(cfg.get("narrative_graph_window_seconds", 6 * 3600))
        self._count_scale = float(cfg.get("narrative_count_scale", 8.0))
        self._peak_score = float(cfg.get("narrative_peak_score", 0.8))
        self._spread_score = float(cfg.get("narrative_spread_score", 0.55))
        self._fade_score = float(cfg.get("narrative_fade_score", 0.25))
        self._peak_count = int(cfg.get("narrative_peak_count", 8))
        self._spread_count = int(cfg.get("narrative_spread_count", 4))
        self._fade_count = int(cfg.get("narrative_fade_count", 1))
        self._trend_threshold = float(cfg.get("narrative_trend_threshold", 0.5))
        self._spike_threshold = float(cfg.get("narrative_attention_spike_threshold", 0.75))
        self._spike_delta = float(cfg.get("narrative_spike_delta", 0.15))
        self._emit_cooldown = float(cfg.get("narrative_emit_cooldown_seconds", 120))
        self._graph_same_weight = float(cfg.get("narrative_graph_same_event_weight", 1.0))
        self._graph_temporal_weight = float(cfg.get("narrative_graph_temporal_weight", 0.3))

        self._states: Dict[str, NarrativeState] = {}
        self._graph_edges: Dict[Tuple[str, str], float] = defaultdict(float)
        self._recent_hits: Deque[Tuple[float, List[str]]] = deque()

        self._load_state()

    def _load_state(self) -> bool:
        """从数据库加载状态"""
        try:
            from deva import NB
            nb = NB(NARRATIVE_PERSISTENCE_TABLE)
            data = nb.get("narrative_states")
            if not data or not isinstance(data, dict):
                return False

            now_ts = time.time()
            loaded_count = 0

            for name, state_data in data.items():
                if loaded_count >= MAX_PERSIST_STATES:
                    break
                try:
                    state = NarrativeState.from_dict(state_data)
                    if now_ts - state.last_updated < 72 * 3600:
                        self._states[name] = state
                        loaded_count += 1
                except Exception:
                    continue

            if loaded_count > 0:
                print(f"[NarrativeTracker] 从持久化恢复 {loaded_count} 个叙事状态")
            return loaded_count > 0
        except Exception:
            return False

    def save_state(self) -> bool:
        """保存状态到数据库"""
        try:
            from deva import NB
            nb = NB(NARRATIVE_PERSISTENCE_TABLE)

            sorted_states = sorted(
                self._states.values(),
                key=lambda s: s.attention_score,
                reverse=True
            )

            persist_data = {}
            for state in sorted_states[:MAX_PERSIST_STATES]:
                state_dict = state.to_dict()
                if len(state_dict.get("hits", [])) > MAX_PERSIST_HITS:
                    state_dict["hits"] = state_dict["hits"][-MAX_PERSIST_HITS:]
                persist_data[state.name] = state_dict

            nb["narrative_states"] = persist_data
            nb["saved_at"] = time.time()
            return True
        except Exception:
            return False

    def detect_narratives(self, event: Any) -> Dict[str, List[str]]:
        if not self.enabled:
            return {}

        texts = self._collect_texts(event)
        if not texts:
            return {}

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()
        matches: Dict[str, List[str]] = {}

        for narrative, keywords in self._keywords.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                matches[narrative] = hit_keywords

        return matches

    def ingest_event(self, event: Any) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        matches = self.detect_narratives(event)
        if not matches:
            return []

        now_ts = self._get_timestamp(event)
        attention = self._clamp_score(getattr(event, "attention_score", 0.0))
        results: List[Dict[str, Any]] = []

        narratives = list(matches.keys())
        self._update_graph(now_ts, narratives)

        for narrative, keywords in matches.items():
            state = self._states.get(narrative)
            if state is None:
                state = NarrativeState(name=narrative, last_stage_change=now_ts)
                self._states[narrative] = state

            state.hits.append((now_ts, attention, keywords))
            state.total_count += 1
            state.last_keywords = keywords
            state.last_updated = now_ts

            self._prune_hits(state, now_ts)
            metrics = self._compute_metrics(state, now_ts)
            new_stage = self._determine_stage(metrics)
            new_score = metrics["attention_score"]

            stage_changed = new_stage != state.stage
            spike = new_score >= self._spike_threshold and (new_score - state.attention_score) >= self._spike_delta

            state.recent_count = metrics["recent_count"]
            state.trend = metrics["trend"]
            state.attention_score = new_score

            if stage_changed:
                state.stage = new_stage
                state.last_stage_change = now_ts
                event_payload = self._build_event_payload(
                    narrative=narrative,
                    event_type="narrative_stage_change",
                    stage=new_stage,
                    metrics=metrics,
                    keywords=keywords,
                )
                if self._should_emit(state, "stage", now_ts):
                    results.append(event_payload)

            if spike:
                event_payload = self._build_event_payload(
                    narrative=narrative,
                    event_type="narrative_attention_spike",
                    stage=new_stage,
                    metrics=metrics,
                    keywords=keywords,
                )
                if self._should_emit(state, "spike", now_ts):
                    results.append(event_payload)

        return results

    def get_summary(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self._states:
            return []
        sorted_states = sorted(self._states.values(), key=lambda s: s.attention_score, reverse=True)
        summary = []
        for state in sorted_states[:limit]:
            summary.append({
                "narrative": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "recent_count": state.recent_count,
                "trend": round(state.trend, 3),
                "last_updated": state.last_updated,
                "keywords": state.last_keywords,
            })
        return summary

    def get_graph(self, min_weight: float = 0.2) -> Dict[str, Any]:
        nodes = []
        for state in self._states.values():
            nodes.append({
                "id": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "recent_count": state.recent_count,
            })

        edges = []
        for (left, right), weight in self._graph_edges.items():
            if weight < min_weight:
                continue
            edges.append({
                "source": left,
                "target": right,
                "weight": round(weight, 3),
            })

        return {"nodes": nodes, "edges": edges}

    def get_linked_sectors(self, narrative: str) -> List[str]:
        """获取叙事主题关联的板块列表

        这是叙事-板块联动的关键接口：
        NarrativeTracker 识别叙事主题后，通过此方法获取关联的 sector_id，
        从而实现"舆情 → 板块轮动"的联动。

        Args:
            narrative: 叙事主题名称，如 "AI"、"芯片"、"新能源"

        Returns:
            关联的 sector_id 列表
        """
        from .narrative_sector_mapping import get_linked_sectors as _get_linked_sectors
        return _get_linked_sectors(narrative)

    def get_narrative_with_sectors(self) -> List[Dict[str, Any]]:
        """获取所有叙事主题及其关联板块

        Returns:
            包含 narrative 和 linked_sectors 的字典列表
        """
        from .narrative_sector_mapping import get_linked_sectors as _get_linked_sectors

        result = []
        for state in self._states.values():
            result.append({
                "narrative": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "linked_sectors": _get_linked_sectors(state.name),
            })
        return result

    def get_liquidity_structure(self) -> Dict[str, Any]:
        """获取美林时钟四象限流动性结构

        Returns:
            包含四象限状态的字典，以及流动性结论
        """
        liquidity_quadrants = {
            "股票市场": {"icon": "📈", "color": "#4ade80", "desc": "资金风险偏好"},
            "债券市场": {"icon": "📊", "color": "#60a5fa", "desc": "资金避险"},
            "大宗商品": {"icon": "🛢️", "color": "#f97316", "desc": "通胀预期"},
            "现金与货币": {"icon": "💵", "color": "#a855f7", "desc": "资金观望"},
        }

        related_narratives = {
            "贵金属": {"quadrant": "大宗商品", "icon": "🥇"},
            "全球宏观": {"quadrant": "股票市场", "icon": "🌍"},
            "外汇与美元": {"quadrant": "现金与货币", "icon": "💱"},
            "流动性紧张": {"quadrant": "现金与货币", "icon": "⚠️"},
        }

        quadrants = {}
        for name, info in liquidity_quadrants.items():
            state = self._states.get(name)
            if state:
                quadrants[name] = {
                    "stage": state.stage,
                    "attention_score": round(state.attention_score, 3),
                    "recent_count": state.recent_count,
                    "trend": round(state.trend, 3),
                    "icon": info["icon"],
                    "color": info["color"],
                    "desc": info["desc"],
                }
            else:
                quadrants[name] = {
                    "stage": "无数据",
                    "attention_score": 0,
                    "recent_count": 0,
                    "trend": 0,
                    "icon": info["icon"],
                    "color": info["color"],
                    "desc": info["desc"],
                }

        related = {}
        for nar_name, nar_info in related_narratives.items():
            state = self._states.get(nar_name)
            if state:
                related[nar_name] = {
                    "stage": state.stage,
                    "attention_score": round(state.attention_score, 3),
                    "quadrant": nar_info["quadrant"],
                    "icon": nar_info["icon"],
                }

        active_quadrants = [name for name, data in quadrants.items() if data["stage"] in ("高潮", "扩散")]
        active_related_quadrants = list(set([nar_info["quadrant"] for nar_info in related.values()]))

        conclusion_parts = []
        if active_quadrants:
            conclusion_parts.append(f"资金偏好: {', '.join(active_quadrants)}")
        if active_related_quadrants:
            quadrant_short = {"大宗商品": "商品", "股票市场": "股市", "现金与货币": "货币"}
            short_names = [quadrant_short.get(q, q) for q in active_related_quadrants]
            conclusion_parts.append(f"宏观信号: {', '.join(short_names)}")

        conclusion = " | ".join(conclusion_parts) if conclusion_parts else "象限数据收集中..."

        # ========== 整合美林时钟周期判断 ==========
        try:
            from deva.naja.cognition.merrill_clock_engine import get_merrill_clock_engine
            clock_engine = get_merrill_clock_engine()
            clock_signal = clock_engine.get_current_signal()
            
            if clock_signal:
                clock_phase = clock_signal.phase.value
                clock_confidence = clock_signal.confidence
                asset_ranking = clock_signal.asset_ranking
                clock_reason = clock_signal.reason
                
                phase_best_asset = {
                    "复苏": "股票",
                    "过热": "商品",
                    "滞胀": "现金",
                    "衰退": "债券",
                }
                best_asset = phase_best_asset.get(clock_phase, "")
                
                long_term = f"周期：{clock_phase}({clock_confidence:.0%})→{best_asset}最佳"
            else:
                long_term = "周期数据收集中..."
                clock_phase = None
                asset_ranking = []
        except Exception as e:
            long_term = "周期判断暂不可用"
            clock_phase = None
            asset_ranking = []

        final_conclusion = f"{long_term} | {conclusion}"

        return {
            "quadrants": quadrants,
            "related": related,
            "clock_phase": clock_phase,
            "asset_ranking": asset_ranking,
            "short_term": conclusion,
            "long_term": long_term,
            "conclusion": final_conclusion,
            "timestamp": time.time(),
        }

    def detect_tiandao_signals(self, event: Any) -> Dict[str, List[str]]:
        """检测天道信号 - 真正的供需失衡/效率提升信号

        Returns:
            Dict[str, List[str]] - 按天道类别分类的命中关键词
        """
        if not self.enabled:
            return {}

        texts = self._collect_texts(event)
        if not texts:
            return {}

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()
        matches: Dict[str, List[str]] = {}

        for signal_type, keywords in TIANDAO_KEYWORDS.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                matches[signal_type] = hit_keywords

        return matches

    def detect_minxin_signals(self, event: Any) -> Dict[str, List[str]]:
        """检测民心信号 - 市场情绪/舆论信号（仅作参考）

        Returns:
            Dict[str, List[str]] - 按民心类别分类的命中关键词
        """
        if not self.enabled:
            return {}

        texts = self._collect_texts(event)
        if not texts:
            return {}

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()
        matches: Dict[str, List[str]] = {}

        for signal_type, keywords in MINXIN_KEYWORDS.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                matches[signal_type] = hit_keywords

        return matches

    def get_tiandao_minxin_summary(self) -> Dict[str, Any]:
        """获取天道/民心评分摘要

        这是'遵循天道，驾驭民心'的核心接口：
        - 天道评分：基于TIANDAO_KEYWORDS命中情况
        - 民心评分：基于MINXIN_KEYWORDS命中情况
        - 推荐行动：基于天道而非民心

        Returns:
            包含天道评分、民心评分、投资建议的字典
        """
        if not self._states:
            return {
                "tiandao_score": 0.0,
                "minxin_score": 0.0,
                "recommendation": "WATCH",
                "reason": "暂无数据",
                "signals": {"tiandao": {}, "minxin": {}},
                "principle": "天道大于民心 - 遵循天道，驾驭民心",
            }

        tiandao_signals = {k: [] for k in ["token供需", "技术瓶颈", "效率突破", "AI落地"]}
        minxin_signals = {k: [] for k in ["行情涨跌", "市场情绪", "舆论热点"]}

        for state in self._states.values():
            for keyword in state.last_keywords:
                for tiandao_type, tiandao_kws in TIANDAO_KEYWORDS.items():
                    for kw in tiandao_kws:
                        if kw in keyword or keyword in kw:
                            if kw not in tiandao_signals[tiandao_type]:
                                tiandao_signals[tiandao_type].append(kw)
                for minxin_type, minxin_kws in MINXIN_KEYWORDS.items():
                    for kw in minxin_kws:
                        if kw in keyword or keyword in kw:
                            if kw not in minxin_signals[minxin_type]:
                                minxin_signals[minxin_type].append(kw)

            for hit_ts, attention, keywords in state.hits:
                for keyword in keywords:
                    for tiandao_type, tiandao_kws in TIANDAO_KEYWORDS.items():
                        for kw in tiandao_kws:
                            if kw in keyword or keyword in kw:
                                if kw not in tiandao_signals[tiandao_type]:
                                    tiandao_signals[tiandao_type].append(kw)
                    for minxin_type, minxin_kws in MINXIN_KEYWORDS.items():
                        for kw in minxin_kws:
                            if kw in keyword or keyword in kw:
                                if kw not in minxin_signals[minxin_type]:
                                    minxin_signals[minxin_type].append(kw)

        tiandao_hits = sum(len(v) for v in tiandao_signals.values())
        minxin_hits = sum(len(v) for v in minxin_signals.values())
        tiandao_score = min(1.0, tiandao_hits / 10.0)
        minxin_score = min(1.0, minxin_hits / 15.0)

        if tiandao_hits >= 3 and minxin_hits <= 1:
            recommendation = "STRONG_BUY"
            reason = "天道强 + 市场错判（价格跌）= 最佳买入时机"
        elif tiandao_score > 0.6:
            recommendation = "ALL_IN"
            reason = "天道信号强劲，继续持有/买入"
        elif tiandao_score > 0.3:
            recommendation = "HOLD"
            reason = "天道信号存在，继续观察"
        elif tiandao_hits > 0 and tiandao_score < 0.2:
            recommendation = "REDUCE"
            reason = "供给可能过剩，天道信号减弱"
        else:
            recommendation = "WATCH"
            reason = "天道信号不明显，继续观察"

        market_opportunity = None
        if tiandao_hits >= 3 and minxin_hits <= 1:
            market_opportunity = "天道强 + 价格跌 = 最佳买入时机（驾驭民心）"
        elif tiandao_score > 0.5 and minxin_score > 0.5:
            market_opportunity = "天道强 + 价格涨 = 顺势持有"

        return {
            "tiandao_score": round(tiandao_score, 3),
            "minxin_score": round(minxin_score, 3),
            "recommendation": recommendation,
            "reason": reason,
            "signals": {
                "tiandao": {k: list(set(v)) for k, v in tiandao_signals.items() if v},
                "minxin": {k: list(set(v)) for k, v in minxin_signals.items() if v},
            },
            "market_opportunity": market_opportunity,
            "principle": "天道大于民心 - 遵循天道，驾驭民心",
            "timestamp": time.time(),
        }

    def get_markdown_summary(self) -> str:
        """获取Markdown格式的每日反思摘要 - 用于报告和展示

        简洁格式，适合直接给用户查看
        """
        if not self._states:
            return "## 📊 每日反思\n\n暂无数据"

        tiandao_summary = self.get_tiandao_minxin_summary()
        trading_signal = self.get_trading_signal()

        tiandao_score = tiandao_summary.get("tiandao_score", 0)
        minxin_score = tiandao_summary.get("minxin_score", 0)
        recommendation = tiandao_summary.get("recommendation", "WATCH")

        verdict_map = {
            "STRONG_BUY": "✅ 重大机会",
            "ALL_IN": "🟢 顺势持有",
            "HOLD": "🟡 继续观察",
            "REDUCE": "🟠 考虑减仓",
            "WATCH": "⚪ 保持观望",
        }
        verdict = verdict_map.get(recommendation, "⚪ 观察中")

        lines = [
            "## 📊 每日反思",
            "",
            f"**日期**: {time.strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "### 🎯 天道 vs 民心",
            "",
            f"| 维度 | 评分 | 说明 |",
            f"|------|------|------|",
            f"| 天道 | {tiandao_score:.0%} | {tiandao_summary.get('reason', '待观察')} |",
            f"| 民心 | {minxin_score:.0%} | {tiandao_summary.get('market_opportunity', '无特殊')} |",
            "",
            f"**结论**: {verdict} - {recommendation}",
            "",
            "---",
            "",
            "### 📈 交易信号",
            "",
            f"- 信号: **{trading_signal.get('signal', 'WATCH')}**",
            f"- 波动: {trading_signal.get('volatility', 'UNKNOWN')}",
            f"- 操作: {trading_signal.get('action', '正常持有')}",
            f"- 原因: {trading_signal.get('reason', '趋势不明显')}",
            "",
            "---",
            "",
            "### 💡 操作建议",
            "",
        ]

        if recommendation == "STRONG_BUY":
            lines.append("🎯 **重大机会**: 天道强 + 价格低，建议加仓")
        elif recommendation == "ALL_IN":
            lines.append("🟢 **顺势持有**: 天道支持，继续持有或加仓")
        elif recommendation == "HOLD":
            lines.append("🟡 **继续观察**: 等待更明确信号")
        elif recommendation == "REDUCE":
            lines.append("🟠 **考虑减仓**: 天道减弱，注意风险")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"*{tiandao_summary.get('principle', '天道大于民心')}*")

        return "\n".join(lines)

    def generate_daily_reflection(self) -> Dict[str, Any]:
        """生成每日反思报告 - 将数据分析转化为自我校准

        反思维度：
        1. 天道判断：我的价值判断是否正确
        2. 民心判断：我对市场的理解是否正确
        3. 交易决策：我的决策是否有效
        4. 进化方向：下一步如何改进
        """
        if not self._states:
            return {
                "date": time.strftime("%Y-%m-%d"),
                "summary": "暂无数据，无法反思",
                "reflections": [],
                "recommendations": [],
            }

        tiandao_summary = self.get_tiandao_minxin_summary()
        trading_signal = self.get_trading_signal()

        reflections = []
        recommendations = []

        tiandao_score = tiandao_summary.get("tiandao_score", 0)
        minxin_score = tiandao_summary.get("minxin_score", 0)
        recommendation = tiandao_summary.get("recommendation", "WATCH")

        reflections.append({
            "aspect": "天道判断",
            "observation": f"天道评分{tiandao_score:.1%}，{tiandao_summary.get('reason', '')}",
            "verdict": "正确" if tiandao_score > 0.5 else "需观察",
        })

        reflections.append({
            "aspect": "民心判断",
            "observation": f"民心评分{minxin_score:.1%}，{tiandao_summary.get('market_opportunity', '无特殊机会')}",
            "verdict": "市场错判" if minxin_score < 0.3 and tiandao_score > 0.5 else "正常",
        })

        signal = trading_signal.get("signal", "WATCH")
        volatility = trading_signal.get("volatility", "UNKNOWN")

        if signal == "OVERSOLD":
            reflections.append({
                "aspect": "波动判断",
                "observation": f"检测到超卖信号：{trading_signal.get('reason', '')}",
                "verdict": "可能是买入机会",
            })
            recommendations.append("可以考虑分批买入，等反弹后高抛")
        elif signal == "OVERBOUGHT":
            reflections.append({
                "aspect": "波动判断",
                "observation": f"检测到超买信号：{trading_signal.get('reason', '')}",
                "verdict": "注意风险",
            })
            recommendations.append("可以适当减仓，等回调再买")
        else:
            reflections.append({
                "aspect": "波动判断",
                "observation": f"市场波动正常：{trading_signal.get('reason', '')}",
                "verdict": "正常持有",
            })

        if recommendation == "STRONG_BUY":
            recommendations.append("重大机会：天道强+价格低，建议加仓")
        elif recommendation == "ALL_IN":
            recommendations.append("天道支持：继续持有或加仓")
        elif recommendation == "REDUCE":
            recommendations.append("天道减弱：考虑减仓")

        if recommendations:
            recommendations.append("坚持天道大于民心，不被市场情绪左右")

        ai_state = self._states.get("AI")
        chip_state = self._states.get("芯片")
        if ai_state and chip_state:
            ai_trend = ai_state.trend
            chip_trend = chip_state.trend
            if ai_trend > 0.3 and chip_trend > 0.3:
                reflections.append({
                    "aspect": "趋势判断",
                    "observation": f"AI叙事趋势{ai_trend:+.1f}，芯片叙事趋势{chip_trend:+.1f}",
                    "verdict": "强势方向，继续持有",
                })
            elif ai_trend < -0.3 or chip_trend < -0.3:
                reflections.append({
                    "aspect": "趋势判断",
                    "observation": f"AI叙事趋势{ai_trend:+.1f}，芯片叙事趋势{chip_trend:+.1f}",
                    "verdict": "趋势减弱，谨慎观望",
                })

        verdict_map = {
            "STRONG_BUY": "✅ 重大机会",
            "ALL_IN": "🟢 顺势持有",
            "HOLD": "🟡 继续观察",
            "REDUCE": "🟠 考虑减仓",
            "WATCH": "⚪ 保持观望",
        }

        return {
            "date": time.strftime("%Y-%m-%d"),
            "verdict": verdict_map.get(recommendation, "⚪ 观察中"),
            "tiandao_score": tiandao_score,
            "minxin_score": minxin_score,
            "signal": signal,
            "summary": f"天道{tiandao_score:.0%} vs 民心{minxin_score:.0%} → {recommendation}",
            "reflections": reflections,
            "recommendations": list(set(recommendations)),
            "principle": "天道大于民心 - 遵循天道，驾驭民心",
            "timestamp": time.time(),
        }

    _market_analysis_db = None

    def analyze_market_full(self) -> Dict[str, Any]:
        """全市场深度分析

        步骤1：全量股票 → 板块映射 → River异常检测
        步骤2：只关注行业+持仓 → River二次分析（重点）

        Returns:
            包含全市场分析、持仓分析、综合判断的字典
        """
        import logging
        log = logging.getLogger(__name__)

        log.info("[NarrativeTracker] 开始全市场深度分析...")

        step1_result = self._analyze_full_market()

        step2_result = self._analyze_focused_sectors(step1_result)

        combined_result = {
            "step1_full_market": step1_result,
            "step2_focused": step2_result,
            "summary": self._generate_market_summary(step1_result, step2_result),
            "timestamp": time.time(),
        }

        db = self._get_market_analysis_db()
        db["full_analysis"] = combined_result

        log.info("[NarrativeTracker] 全市场深度分析完成")

        return combined_result

    def _analyze_full_market(self) -> Dict[str, Any]:
        """第一步：全市场分析"""
        import logging
        log = logging.getLogger(__name__)

        stock_data = self._fetch_all_stock_data()
        if not stock_data:
            return {"success": False, "message": "无法获取市场数据"}

        sector_analysis = self._map_sectors(stock_data)

        stocks_with_sector = self._merge_sector_to_stocks(stock_data, sector_analysis)

        anomaly_result = self._run_river_anomaly_detection(stocks_with_sector)

        return {
            "success": True,
            "stock_count": len(stock_data),
            "sector_analysis": sector_analysis,
            "anomaly_result": anomaly_result,
            "top_movers": self._get_top_movers(stock_data, limit=5),
        }

    def _merge_sector_to_stocks(self, stock_data: Dict[str, Dict], sector_analysis: Dict[str, List[Dict]]) -> List[Dict]:
        """把sector信息合并到股票数据中"""
        symbol_to_sector = {}
        for sector, stocks in sector_analysis.items():
            for stock in stocks:
                sym = stock.get("symbol", stock.get("code"))
                if sym:
                    symbol_to_sector[sym] = {
                        "sector": sector,
                        "narrative": stock.get("narrative", ""),
                        "blocks": stock.get("blocks", []),
                    }

        result = []
        for sym, data in stock_data.items():
            merged = dict(data)
            if sym in symbol_to_sector:
                merged.update(symbol_to_sector[sym])
            else:
                merged["sector"] = "other"
                merged["narrative"] = ""
                merged["blocks"] = []
            result.append(merged)

        return result

    def _analyze_focused_sectors(self, step1_result: Dict[str, Any]) -> Dict[str, Any]:
        """第二步：持仓+关注行业二次分析（重点）"""
        import logging
        log = logging.getLogger(__name__)

        if not step1_result.get("success"):
            return {"success": False}

        all_stocks = step1_result.get("stock_data", {})
        if not all_stocks:
            all_stocks = self._fetch_all_stock_data()

        focus_symbols = self._get_focus_symbols()

        focus_stocks = {
            symbol: data for symbol, data in all_stocks.items()
            if symbol.upper() in [s.upper() for s in focus_symbols]
        }

        if not focus_stocks:
            log.warning("[NarrativeTracker] 持仓/关注股票无数据")
            return {"success": False, "message": "无持仓/关注股票数据"}

        sector_analysis = self._map_sectors(focus_stocks)

        anomaly_result = self._run_river_anomaly_detection(list(focus_stocks.values()))

        holding_analysis = self._analyze_holdings(focus_stocks)

        return {
            "success": True,
            "focus_stock_count": len(focus_stocks),
            "focus_symbols": list(focus_stocks.keys()),
            "sector_analysis": sector_analysis,
            "anomaly_result": anomaly_result,
            "holding_analysis": holding_analysis,
            "top_movers": self._get_top_movers(focus_stocks, limit=5),
        }

    def _fetch_all_stock_data(self) -> Dict[str, Dict]:
        """获取全量股票数据（A股+美股）"""
        result = {}

        result.update(self._fetch_ashare_data())

        result.update(self._fetch_us_stock_data())

        return result

    def _fetch_ashare_data(self) -> Dict[str, Dict]:
        """获取A股数据 - 使用历史快照数据库（已过滤噪音股票）"""
        try:
            from deva import NB

            snapshot_db = NB('quant_snapshot_5min_window', key_mode='time')
            keys = list(snapshot_db.keys())
            if not keys:
                return {}

            latest_key = keys[-1]
            data_list = snapshot_db.get(latest_key)

            if not data_list or not isinstance(data_list, list):
                return {}

            result = {}
            for item in data_list:
                code = str(item.get("code", ""))
                if not code:
                    continue

                try:
                    now = item.get("now", 0)
                    close = item.get("close", 0)
                    if close > 0:
                        p_change = (now - close) / close
                    else:
                        p_change = 0
                    result[code] = {
                        "code": code,
                        "name": item.get("name", code),
                        "price": now,
                        "change_pct": p_change,
                        "volume": int(item.get("volume", 0)),
                        "high": item.get("high", 0),
                        "low": item.get("low", 0),
                        "prev_close": close,
                        "open": item.get("open", 0),
                        "market": "A",
                    }
                except Exception:
                    continue

            return result
        except Exception:
            return {}

    def _fetch_us_stock_data(self) -> Dict[str, Dict]:
        """获取美股数据"""
        try:
            from deva.naja.attention.data.global_market_futures import GlobalMarketAPI
            import asyncio
            import nest_asyncio
            nest_asyncio.apply()

            async def fetch():
                async with GlobalMarketAPI() as api:
                    return await api.fetch_us_stocks()

            try:
                loop = asyncio.get_event_loop()
                data = loop.run_until_complete(fetch())
            except RuntimeError:
                asyncio.run(fetch())

            result = {}
            for code, market_data in data.items():
                if market_data and hasattr(market_data, 'code'):
                    change_pct = market_data.change_pct
                    if abs(change_pct) > 1:
                        change_pct = change_pct / 100
                    result[code.upper()] = {
                        "code": market_data.code.upper(),
                        "name": market_data.name,
                        "price": market_data.current,
                        "change_pct": change_pct,
                        "p_change": change_pct,
                        "volume": market_data.volume,
                        "high": market_data.high,
                        "low": market_data.low,
                        "prev_close": market_data.prev_close,
                        "market": "US",
                    }

            return result
        except Exception:
            return {}

    def _get_focus_symbols(self) -> List[str]:
        """获取关注的股票列表：持仓+行业关注"""
        symbols = []

        try:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager
            pm = get_portfolio_manager()
            if pm:
                for account_name in ["Spark", "Cutie"]:
                    portfolio = pm.get_us_portfolio(account_name)
                    if portfolio:
                        positions = portfolio.get_open_positions()
                        for pos in positions:
                            if hasattr(pos, 'stock_code'):
                                symbols.append(pos.stock_code)
        except Exception:
            pass

        symbols.extend(["NVDA", "AMD", "META", "TSLA", "AAPL", "MSFT", "GOOG", "AMZN"])

        return list(set(symbols))

    def _map_sectors(self, stocks: Dict[str, Dict]) -> Dict[str, List[Dict]]:
        """板块映射分析 - A股用通达信，美股用US_STOCK_SECTORS"""
        from deva.naja.bandit.stock_sector_map import US_STOCK_SECTORS, SECTOR_INDUSTRY_MAP, NARRATIVE_SECTOR_MAP

        try:
            from deva.naja.dictionary.tongdaxin_blocks import get_stock_blocks, _parse_blocks_file
            _parse_blocks_file()
            has_tdx = True
        except Exception:
            has_tdx = False

        sector_map: Dict[str, List[Dict]] = defaultdict(list)

        for symbol, data in stocks.items():
            market = data.get("market", "A")

            if market == "US":
                stock_info = US_STOCK_SECTORS.get(symbol.lower(), {})
                if stock_info:
                    sector = stock_info.get("sector", "other")
                    blocks = stock_info.get("blocks", [])
                    narrative = stock_info.get("narrative", "")
                else:
                    sector = "other"
                    blocks = []
                    narrative = ""
            else:
                sector = "other"
                blocks = []
                narrative = ""

                if has_tdx:
                    code = symbol.replace("sh", "").replace("sz", "")
                    blocks = get_stock_blocks(code)
                    if blocks:
                        sector = blocks[0]

            sector_map[sector].append({
                "symbol": symbol,
                "name": data.get("name", symbol),
                "price": data.get("price", 0),
                "change_pct": data.get("change_pct", 0),
                "blocks": blocks,
                "narrative": narrative,
            })

        return dict(sector_map)

    def _run_river_anomaly_detection(self, stocks: List[Dict]) -> Dict[str, Any]:
        """使用River风格进行单日横截面分析

        1. RiverTickSingleDayAnalyzer - 单日全市场横截面分析
        2. 板块表现分析
        3. 异常波动检测
        4. 市场情绪判断
        """
        try:
            from deva.naja.strategy.river_single_day_analyzer import RiverTickSingleDayAnalyzer

            analyzer = RiverTickSingleDayAnalyzer()

            for stock in stocks:
                analyzer.on_data(stock)

            result = analyzer.get_signal()

            if not result:
                return {"error": "无数据"}

            return {
                "total_analyzed": result.stock_count,
                "market_breadth": round(result.market_breadth, 3),
                "market_sentiment": result.market_sentiment,
                "fund_flow": result.fund_flow,
                "market_feature": result.market_feature,
                "avg_change": round(result.avg_change, 3),
                "median_change": round(result.median_change, 3),
                "advancing_count": result.advancing_count,
                "declining_count": result.declining_count,
                "sectors": {
                    name: {
                        "stock_count": s.stock_count,
                        "avg_change": round(s.avg_change, 3),
                        "gainer_count": s.gainer_count,
                        "loser_count": s.loser_count,
                    }
                    for name, s in result.sectors.items()
                    if s.stock_count >= 1
                },
                "anomalies": result.anomalies[:10],
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_top_movers(self, stocks: Dict[str, Dict], limit: int = 5) -> Dict[str, List]:
        """获取涨幅/跌幅最大的股票"""
        sorted_stocks = sorted(stocks.values(), key=lambda x: x.get("change_pct", 0), reverse=True)
        return {
            "gainers": [{
                "symbol": s.get("code", ""),
                "name": s.get("name", ""),
                "change_pct": s.get("change_pct", 0),
            } for s in sorted_stocks[:limit]],
            "losers": [{
                "symbol": s.get("code", ""),
                "name": s.get("name", ""),
                "change_pct": s.get("change_pct", 0),
            } for s in sorted_stocks[-limit:]],
        }

    def _analyze_holdings(self, stocks: Dict[str, Dict]) -> Dict[str, Any]:
        """分析持仓股票"""
        holdings = []

        try:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager
            pm = get_portfolio_manager()
            if pm:
                for account_name in ["Spark", "Cutie"]:
                    portfolio = pm.get_us_portfolio(account_name)
                    if portfolio:
                        positions = portfolio.get_open_positions()
                        for pos in positions:
                            symbol = pos.stock_code.upper()
                            if symbol in stocks:
                                stock_data = stocks[symbol]
                                holdings.append({
                                    "account": account_name,
                                    "symbol": symbol,
                                    "name": stock_data.get("name", symbol),
                                    "quantity": pos.quantity,
                                    "entry_price": pos.entry_price,
                                    "current_price": stock_data.get("price", 0),
                                    "profit_loss": pos.profit_loss,
                                    "return_pct": pos.return_pct,
                                    "current_change_pct": stock_data.get("change_pct", 0),
                                })
        except Exception:
            pass

        return {"holdings": holdings}

    def _generate_market_summary(self, step1: Dict, step2: Dict) -> str:
        """生成市场总结"""
        parts = []

        if step1.get("success"):
            top_movers = step1.get("top_movers", {})
            gainers = top_movers.get("gainers", [])
            if gainers:
                best = gainers[0]
                parts.append(f"全市场涨幅最大: {best['name']}({best['symbol']}) {best['change_pct']:+.2f}%")

        if step2.get("success"):
            holding_analysis = step2.get("holding_analysis", {})
            holdings = holding_analysis.get("holdings", [])
            if holdings:
                total_pnl = sum(h.get("profit_loss", 0) for h in holdings)
                parts.append(f"持仓盈亏: ${total_pnl:+.2f}")

        return " | ".join(parts) if parts else "暂无数据"

    @classmethod
    def _get_market_analysis_db(cls):
        if cls._market_analysis_db is None:
            from deva import NB
            cls._market_analysis_db = NB("naja_market_analysis")
        return cls._market_analysis_db

    def analyze_market_data(self) -> Dict[str, Any]:
        """盘后市场分析 - 由定时任务调用

        获取主要指数行情，分析市场状态，存储分析结果
        供LLM反思时收集
        """
        import logging
        log = logging.getLogger(__name__)

        try:
            market_data = self._fetch_market_indices()
            if not market_data:
                return {"success": False, "message": "无法获取市场数据"}

            analysis = self._analyze_market_indices(market_data)

            market_analysis = {
                "data": market_data,
                "analysis": analysis,
                "timestamp": time.time(),
            }

            db = self._get_market_analysis_db()
            db["latest"] = market_analysis

            log.info(f"[NarrativeTracker] 盘后市场分析完成: {analysis.get('summary', 'N/A')}")

            return {
                "success": True,
                "market_data": market_data,
                "analysis": analysis,
            }
        except Exception as e:
            log.error(f"[NarrativeTracker] 盘后市场分析失败: {e}")
            return {"success": False, "message": str(e)}

    def _fetch_market_indices(self) -> Dict[str, Dict]:
        """获取主要指数行情"""
        try:
            import urllib.request
            import json

            indices = ["^NDX", "^SPX", "^QQQ", "^DJI", "^VIX"]
            result = {}

            for symbol in indices:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                try:
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode())
                        result_data = data.get("chart", {}).get("result", [{}])[0]
                        meta = result_data.get("meta", {})
                        price = meta.get("regularMarketPrice")
                        prev_close = meta.get("previousClose")
                        change_pct = (price - prev_close) / prev_close * 100 if price and prev_close else 0

                        symbol_name = symbol.replace("^", "")
                        result[symbol_name] = {
                            "price": price,
                            "change_pct": round(change_pct, 2),
                            "prev_close": prev_close,
                        }
                except Exception:
                    continue

            return result
        except Exception:
            return {}

    def _analyze_market_indices(self, data: Dict[str, Dict]) -> Dict[str, Any]:
        """分析市场指数数据"""
        if not data:
            return {"summary": "无数据", "status": "unknown"}

        ndx_change = data.get("NDX", {}).get("change_pct", 0)
        spy_change = data.get("SPX", {}).get("change_pct", 0)
        qqq_change = data.get("QQQ", {}).get("change_pct", 0)
        vix = data.get("VIX", {}).get("price", 20)

        avg_change = (ndx_change + spy_change + qqq_change) / 3

        if avg_change > 2:
            status = "强势上涨"
            description = f"市场强势上涨，纳指{ndx_change:+.2f}%，标普{spy_change:+.2f}%"
        elif avg_change > 0.5:
            status = "小幅上涨"
            description = f"市场温和上涨，纳指{ndx_change:+.2f}%"
        elif avg_change > -0.5:
            status = "震荡整理"
            description = f"市场震荡，纳指{ndx_change:+.2f}%"
        elif avg_change > -2:
            status = "小幅下跌"
            description = f"市场小幅回调，纳指{ndx_change:+.2f}%"
        else:
            status = "大幅下跌"
            description = f"市场大幅下跌，纳指{ndx_change:+.2f}%，标普{spy_change:+.2f}%"

        if vix > 30:
            description += f"，VIX高企({vix:.1f})，市场恐慌"
        elif vix > 20:
            description += f"，VIX中性({vix:.1f})"

        return {
            "status": status,
            "summary": description,
            "ndx_change": ndx_change,
            "spy_change": spy_change,
            "qqq_change": qqq_change,
            "vix": vix,
            "avg_change": round(avg_change, 2),
        }

    def get_market_analysis(self) -> Dict[str, Any]:
        """获取缓存的市场分析结果"""
        try:
            db = self._get_market_analysis_db()
            return db.get("latest", {})
        except Exception:
            return {}

    def get_trading_signal(self) -> Dict[str, Any]:
        """获取交易信号 - 基于叙事状态判断超卖/超买

        利用NarrativeState的trend和stage判断：
        - 超卖：叙事衰退+价格跌 = 买入机会
        - 超买：叙事高潮+价格涨 = 卖出机会
        """
        if not self._states:
            return {
                "signal": "WATCH",
                "volatility": "UNKNOWN",
                "action": "暂无数据，继续观察",
                "reason": "",
            }

        ai_state = self._states.get("AI")
        chip_state = self._states.get("芯片")
        price_state = self._states.get("民心")

        signal = "WATCH"
        volatility = "NORMAL"
        action = "正常持有"
        reason_parts = []

        if ai_state and chip_state:
            ai_trend = ai_state.trend
            chip_trend = chip_state.trend
            ai_stage = ai_state.stage
            chip_stage = chip_state.stage

            if ai_trend < -0.5 and ai_stage in ("消退", "萌芽"):
                signal = "OVERSOLD"
                volatility = "LOW"
                action = "可以考虑买入，等反弹后高抛"
                reason_parts.append("AI叙事衰退，可能是买入机会")
            elif ai_trend > 0.5 and ai_stage in ("高潮", "扩散"):
                signal = "OVERBOUGHT"
                volatility = "HIGH"
                action = "可以考虑减仓，等回调再买"
                reason_parts.append("AI叙事过热，注意风险")

        if price_state:
            price_trend = price_state.trend
            if price_trend < -0.3:
                reason_parts.append("价格下跌趋势")
            elif price_trend > 0.3:
                reason_parts.append("价格上涨趋势")

        tiandao_summary = self.get_tiandao_minxin_summary()
        tiandao_score = tiandao_summary.get("tiandao_score", 0)

        if signal == "OVERSOLD" and tiandao_score > 0.3:
            action = "最佳买入时机：天道好+价格低"
            reason_parts.append("天道强+价格低")
        elif signal == "OVERBOUGHT" and tiandao_score > 0.3:
            action = "可以适当减仓：天道好+价格高"
            reason_parts.append("天道强+价格高")

        reason = "；".join(reason_parts) if reason_parts else "趋势不明显"

        return {
            "signal": signal,
            "volatility": volatility,
            "action": action,
            "reason": reason,
            "tiandao_score": tiandao_score,
            "timestamp": time.time(),
        }

    def _collect_texts(self, event: Any) -> List[str]:
        texts: List[str] = []
        if event is None:
            return texts
        content = getattr(event, "content", None)
        if content:
            texts.append(str(content))
        meta = getattr(event, "meta", {}) or {}

        for key in ("title", "topic", "sector", "industry", "theme", "summary"):
            val = meta.get(key)
            if val:
                texts.append(str(val))

        for key in ("tags", "keywords", "narratives", "narrative"):
            val = meta.get(key)
            if isinstance(val, list):
                texts.extend([str(v) for v in val])
            elif val:
                texts.append(str(val))

        return texts

    def _keyword_in_text(self, keyword: str, text: str, text_lower: str) -> bool:
        if not keyword:
            return False
        if keyword.isascii():
            return keyword.lower() in text_lower
        return keyword in text

    def _get_timestamp(self, event: Any) -> float:
        ts = getattr(event, "timestamp", None)
        if ts is None:
            return time.time()
        if hasattr(ts, "timestamp"):
            try:
                return float(ts.timestamp())
            except Exception:
                return time.time()
        try:
            return float(ts)
        except Exception:
            return time.time()

    def _clamp_score(self, score: Any) -> float:
        try:
            value = float(score)
        except Exception:
            return 0.0
        if value < 0:
            return 0.0
        if value <= 1.0:
            return value
        return min(1.0, value / 5.0)

    def _prune_hits(self, state: NarrativeState, now_ts: float) -> None:
        cutoff = now_ts - self._history_window
        while state.hits and state.hits[0][0] < cutoff:
            state.hits.popleft()

    def _compute_metrics(self, state: NarrativeState, now_ts: float) -> Dict[str, Any]:
        recent_cutoff = now_ts - self._recent_window
        prev_cutoff = recent_cutoff - self._prev_window
        recent_hits = [h for h in state.hits if h[0] >= recent_cutoff]
        prev_hits = [h for h in state.hits if prev_cutoff <= h[0] < recent_cutoff]

        recent_count = len(recent_hits)
        prev_count = len(prev_hits)
        recent_attention = sum(h[1] for h in recent_hits) / recent_count if recent_hits else 0.0
        count_score = 1.0 - math.exp(-recent_count / max(self._count_scale, 1e-6))
        attention_score = 0.6 * count_score + 0.4 * recent_attention
        trend = (recent_count - prev_count) / max(prev_count, 1)

        return {
            "recent_count": recent_count,
            "prev_count": prev_count,
            "attention_score": attention_score,
            "recent_attention": recent_attention,
            "trend": trend,
        }

    def _determine_stage(self, metrics: Dict[str, Any]) -> str:
        recent_count = metrics["recent_count"]
        attention_score = metrics["attention_score"]
        trend = metrics["trend"]

        if recent_count <= self._fade_count and attention_score <= self._fade_score:
            return "消退"
        if recent_count >= self._peak_count or attention_score >= self._peak_score:
            return "高潮"
        if recent_count >= self._spread_count or trend >= self._trend_threshold or attention_score >= self._spread_score:
            return "扩散"
        return "萌芽"

    def _should_emit(self, state: NarrativeState, key: str, now_ts: float) -> bool:
        last_ts = state.last_emit.get(key, 0.0)
        if now_ts - last_ts < self._emit_cooldown:
            return False
        state.last_emit[key] = now_ts
        return True

    def _build_event_payload(
        self,
        *,
        narrative: str,
        event_type: str,
        stage: str,
        metrics: Dict[str, Any],
        keywords: List[str],
    ) -> Dict[str, Any]:
        payload = {
            "type": event_type,
            "event_type": event_type,
            "narrative": narrative,
            "stage": stage,
            "attention_score": round(metrics["attention_score"], 3),
            "recent_count": metrics["recent_count"],
            "prev_count": metrics["prev_count"],
            "trend": round(metrics["trend"], 3),
            "keywords": keywords,
            "linked_sectors": self.get_linked_sectors(narrative),
            "timestamp": time.time(),
        }
        return payload

    def _update_graph(self, now_ts: float, narratives: List[str]) -> None:
        cutoff = now_ts - self._graph_window
        while self._recent_hits and self._recent_hits[0][0] < cutoff:
            self._recent_hits.popleft()

        if len(narratives) > 1:
            pairs = self._pairs(narratives)
            for left, right in pairs:
                key = self._edge_key(left, right)
                self._graph_edges[key] += self._graph_same_weight

        for hit_ts, hit_list in self._recent_hits:
            if now_ts - hit_ts > self._graph_window:
                continue
            for left in narratives:
                for right in hit_list:
                    if left == right:
                        continue
                    key = self._edge_key(left, right)
                    self._graph_edges[key] += self._graph_temporal_weight

        self._recent_hits.append((now_ts, narratives))

    @staticmethod
    def _edge_key(left: str, right: str) -> Tuple[str, str]:
        return tuple(sorted((left, right)))

    @staticmethod
    def _pairs(items: Iterable[str]) -> List[Tuple[str, str]]:
        unique = list(dict.fromkeys(items))
        pairs: List[Tuple[str, str]] = []
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                pairs.append((unique[i], unique[j]))
        return pairs
