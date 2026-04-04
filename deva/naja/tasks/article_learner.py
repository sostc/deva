"""
Naja文章深度学习器
像专业分析师一样系统性地消化文章内容
"""
import re
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

# 导入知识注入器
import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')
try:
    from deva.naja.tasks.ai_knowledge_injector import AIKnowledgeInjector
    HAS_INJECTOR = True
except ImportError:
    HAS_INJECTOR = False
    print("[学习器] 警告: AIKnowledgeInjector不可用，知识将不会注入决策系统")

# 存储路径
KNOWLEDGE_DIR = "/Users/spark/.naja/ai_knowledge"
NARRATIVE_FILE = f"{KNOWLEDGE_DIR}/narratives.json"


# ============== 数据结构 ==============
@dataclass
class SupplyDemandAnalysis:
    """供需关系分析"""
    demand_side: List[str] = field(default_factory=list)      # 需求方
    supply_side: List[str] = field(default_factory=list)      # 供给方
    demand_trend: str = ""                                     # 需求趋势
    supply_trend: str = ""                                     # 供给趋势
    imbalance: str = ""                                        # 供需失衡情况
    key_gap: str = ""                                          # 关键缺口

@dataclass
class NarrativeAnalysis:
    """热点叙事分析"""
    current_narratives: List[str] = field(default_factory=list)  # 当前市场叙事
    this_content_narrative: str = ""                            # 本文支持的叙事
    narrative_alignment: str = ""                               # 叙事一致性: 支持/反对/中性/颠覆
    narrative_strength: float = 0.5                             # 叙事强度 0-1
    narrative_shift: str = ""                                   # 叙事变化

@dataclass
class CausalityChain:
    """因果链条"""
    cause: str = ""                                             # 原因
    mechanism: str = ""                                         # 传导机制
    effect: str = ""                                            # 结果
    timeframe: str = ""                                         # 时间维度
    confidence: float = 0.5                                      # 置信度 0-1
    evidence: List[str] = field(default_factory=list)           # 支持证据

@dataclass
class InvestmentInsight:
    """投资启示"""
    opportunities: List[str] = field(default_factory=list)     # 机会点
    risks: List[str] = field(default_factory=list)              # 风险点
    direction: List[str] = field(default_factory=list)          # 行业方向
    position_suggestion: str = ""                                # 仓位建议
    validation_signals: List[str] = field(default_factory=list) # 验证信号

@dataclass
class LearningResult:
    """完整学习结果"""
    # 基础信息
    url: str = ""
    title: str = ""
    source: str = ""
    publish_time: str = ""
    learned_at: str = ""

    # 核心内容
    summary: str = ""                                           # 一句话总结
    key_points: List[str] = field(default_factory=list)         # 核心要点

    # 深度分析
    supply_demand: SupplyDemandAnalysis = field(default_factory=SupplyDemandAnalysis)
    narrative: NarrativeAnalysis = field(default_factory=NarrativeAnalysis)
    causality_chains: List[CausalityChain] = field(default_factory=list)
    investment: InvestmentInsight = field(default_factory=InvestmentInsight)

    # 元数据
    confidence: float = 0.5                                     # 综合置信度
    status: str = "observing"                                    # 状态
    related_narratives: List[str] = field(default_factory=list)


# ============== 工具函数 ==============
def load_narratives() -> Dict[str, Any]:
    """加载当前叙事库"""
    try:
        with open(NARRATIVE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"narratives": []}

def save_narratives(data: Dict[str, Any]):
    """保存叙事库"""
    import os
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    with open(NARRATIVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_url(text: str) -> Optional[str]:
    """提取URL"""
    urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
    return urls[0] if urls else None

def extract_title_from_content(content: str) -> str:
    """从内容中提取标题"""
    lines = content.strip().split('\n')
    for line in lines[:5]:
        line = line.strip()
        if len(line) > 5 and len(line) < 100:
            return line
    return "未知标题"


# ============== 深度分析引擎 ==============
class ArticleAnalyzer:
    """文章深度分析引擎"""

    # 常见叙事关键词
    NARRATIVE_KEYWORDS = {
        "算力军备竞赛": ["芯片", "GPU", "算力", "H100", "训练", "推理", "算力"],
        "开源vs闭源": ["开源", "Llama", "闭源", "OpenAI", "Meta", "开源模型"],
        "AI应用落地": ["落地", "应用", "商业化", "变现", "企业", "垂直"],
        "监管与安全": ["监管", "安全", "对齐", "风险", "伦理", "治理"],
        "中美竞争": ["美国", "中国", "出口管制", "芯片禁令", "竞争"],
        "AGI突破": ["AGI", "通用人工智能", "超越人类", "突破", "革命"],
        "Agent时代": ["Agent", "智能体", "自动化", "执行", "工具"],
        "多模态融合": ["多模态", "视觉", "音频", "视频", "融合"],
    }

    # 因果关系模式
    CAUSALITY_PATTERNS = [
        (r"(\w+)发布.*?模型", "模型发布", "技术进步 → 竞争力变化"),
        (r"(\w+)获得.*?融资", "融资事件", "资本涌入 → 加速发展"),
        (r"(\w+)开源.*?模型", "开源发布", "开源 → 普及加速"),
        (r"监管.*?AI|AI.*?监管", "监管政策", "政策变化 → 行业格局调整"),
        (r"(\w+)合作.*?(\w+)", "战略合作", "合作 → 资源整合"),
        (r"(\w+)收购.*?公司", "并购", "并购 → 市场集中"),
        (r"(\w+)发布.*?芯片|芯片.*?(\w+)", "硬件发布", "硬件突破 → 算力提升"),
    ]

    def analyze_supply_demand(self, title: str, content: str) -> SupplyDemandAnalysis:
        """分析供需关系"""
        sd = SupplyDemandAnalysis()

        content_lower = content.lower()

        # 识别需求方
        if any(k in content_lower for k in ["企业", "公司", "商业", "客户"]):
            sd.demand_side.append("企业客户")
        if any(k in content_lower for k in ["开发者", "研究人员", "学术"]):
            sd.demand_side.append("开发者/研究人员")
        if any(k in content_lower for k in ["个人", "消费者", "用户"]):
            sd.demand_side.append("个人用户")

        # 识别供给方
        if any(k in content_lower for k in ["大厂", "巨头", "头部", "OpenAI", "Google", "Meta"]):
            sd.supply_side.append("大厂/巨头")
        if any(k in content_lower for k in ["创业公司", "Startup", "独角兽"]):
            sd.supply_side.append("创业公司")
        if any(k in content_lower for k in ["开源社区", "开源", "社区"]):
            sd.supply_side.append("开源社区")

        # 分析趋势
        if any(k in content_lower for k in ["供不应求", "短缺", "稀缺", "不够"]):
            sd.imbalance = "供给不足"
        elif any(k in content_lower for k in ["过剩", "供过于求", "价格战"]):
            sd.imbalance = "供给过剩"
        else:
            sd.imbalance = "供需平衡"

        # 关键缺口
        if any(k in content_lower for k in ["算力", "芯片", "GPU"]):
            sd.key_gap = "算力缺口"
        elif any(k in content_lower for k in ["数据", "高质量数据"]):
            sd.key_gap = "数据缺口"
        elif any(k in content_lower for k in ["人才", "工程师", "专家"]):
            sd.key_gap = "人才缺口"
        else:
            sd.key_gap = "暂无明确缺口"

        return sd

    def analyze_narrative(self, title: str, content: str) -> NarrativeAnalysis:
        """分析热点叙事"""
        narr = NarrativeAnalysis()

        content_full = title + " " + content

        # 识别当前叙事
        for narrative, keywords in self.NARRATIVE_KEYWORDS.items():
            if any(k.lower() in content_full.lower() for k in keywords):
                narr.current_narratives.append(narrative)

        if not narr.current_narratives:
            narr.current_narratives = ["暂无明确叙事"]

        # 判断叙事一致性
        positive_words = ["突破", "领先", "超越", "创新", "成功", "增长", "爆发"]
        negative_words = ["失败", "困境", "危机", "风险", "问题", "挑战", "放缓"]

        pos_count = sum(1 for w in positive_words if w in content_full)
        neg_count = sum(1 for w in negative_words if w in content_full)

        if pos_count > neg_count:
            narr.narrative_alignment = "支持"
            narr.narrative_strength = min(0.9, 0.5 + pos_count * 0.1)
        elif neg_count > pos_count:
            narr.narrative_alignment = "反对/警示"
            narr.narrative_strength = min(0.9, 0.5 + neg_count * 0.1)
        else:
            narr.narrative_alignment = "中性"
            narr.narrative_strength = 0.5

        # 本文叙事
        if narr.current_narratives:
            narr.this_content_narrative = narr.current_narratives[0]

        return narr

    def analyze_causality(self, title: str, content: str) -> List[CausalityChain]:
        """分析因果链条"""
        chains = []

        content_full = title + " " + content

        for pattern, cause_type, mechanism in self.CAUSALITY_PATTERNS:
            matches = re.findall(pattern, content_full)
            if matches:
                for match in matches[:2]:  # 最多2个因果链
                    chain = CausalityChain(
                        cause=f"{match} - {cause_type}",
                        mechanism=mechanism,
                        effect="待确认，需持续跟踪",
                        timeframe="中期(3-12个月)",
                        confidence=0.6,
                        evidence=[f"来源: {title[:50]}"]
                    )
                    chains.append(chain)

        # 如果没有匹配到模式，尝试从内容中提取
        if not chains:
            # 检查是否有明确的因果表述
            if "导致" in content_full or "使得" in content_full or "因此" in content_full:
                chain = CausalityChain(
                    cause="内容中提及的事件",
                    mechanism="因果关系待分析",
                    effect="详见内容",
                    timeframe="待评估",
                    confidence=0.4,
                    evidence=["因果表述存在但需人工确认"]
                )
                chains.append(chain)

        return chains

    def analyze_investment(self, title: str, content: str,
                           supply_demand: SupplyDemandAnalysis,
                           narrative: NarrativeAnalysis) -> InvestmentInsight:
        """分析投资启示"""
        inv = InvestmentInsight()

        content_full = title + " " + content

        # 方向判断
        if any(k in content_full for k in ["算力", "芯片", "GPU", "硬件"]):
            inv.direction.append("算力基础设施")
        if any(k in content_full for k in ["模型", "LLM", "基础模型", "大模型"]):
            inv.direction.append("模型层")
        if any(k in content_full for k in ["应用", "落地", "垂直", "SaaS"]):
            inv.direction.append("应用层")
        if any(k in content_full for k in ["数据", "数据服务"]):
            inv.direction.append("数据服务")

        # 机会点
        if narrative.narrative_alignment == "支持" and narrative.narrative_strength > 0.6:
            inv.opportunities.append(f"叙事强势，建议关注{inv.direction[0] if inv.direction else '相关领域'}机会")
        if supply_demand.imbalance == "供给不足":
            inv.opportunities.append("供需失衡，存在结构性机会")
        if any(k in content_full for k in ["新产品", "新发布", "突破性"]):
            inv.opportunities.append("新产品发布，关注早期采用者")

        # 风险点
        if narrative.narrative_alignment == "反对/警示":
            inv.risks.append("叙事偏空，需谨慎")
        if any(k in content_full for k in ["监管", "禁令", "限制", "风险"]):
            inv.risks.append("监管风险")
        if any(k in content_full for k in ["竞争激烈", "内卷", "价格战"]):
            inv.risks.append("竞争风险")

        # 验证信号
        if "模型" in content_full:
            inv.validation_signals.append("关注模型实际使用数据和用户反馈")
        if "芯片" in content_full:
            inv.validation_signals.append("跟踪芯片产能和交付情况")
        inv.validation_signals.append("持续跟踪本叙事相关进展")

        # 仓位建议
        if narrative.narrative_strength > 0.8:
            inv.position_suggestion = "可以考虑适当布局，但需设置止损"
        elif narrative.narrative_strength < 0.4:
            inv.position_suggestion = "保持观察，暂不参与"
        else:
            inv.position_suggestion = "轻仓试探，跟踪验证"

        return inv


# ============== 文章学习器 ==============
class ArticleLearner:
    """文章深度学习器"""

    def __init__(self):
        self.analyzer = ArticleAnalyzer()

    def learn(self, url: str) -> LearningResult:
        """学习文章并生成完整分析报告"""

        print(f"[学习器] 开始学习: {url}")

        # 1. 获取内容
        content, title, source = self._fetch_content(url)

        # 2. 创建基础结果
        result = LearningResult(
            url=url,
            title=title,
            source=source,
            learned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        # 3. 一句话总结
        result.summary = self._generate_summary(title, content)

        # 4. 核心要点
        result.key_points = self._extract_key_points(content)

        # 5. 供需分析
        result.supply_demand = self.analyzer.analyze_supply_demand(title, content)

        # 6. 叙事分析
        result.narrative = self.analyzer.analyze_narrative(title, content)

        # 7. 因果分析
        result.causality_chains = self.analyzer.analyze_causality(title, content)

        # 8. 投资分析
        result.investment = self.analyzer.analyze_investment(
            title, content, result.supply_demand, result.narrative
        )

        # 9. 计算综合置信度
        result.confidence = self._calculate_confidence(result)

        # 10. 关联叙事
        result.related_narratives = result.narrative.current_narratives

        # 11. 保存知识
        self._save_knowledge(result)

        # 12. 更新叙事库
        self._update_narrative_db(result)

        # 13. 注入到交易决策系统（关键步骤！）
        self._inject_to_decision_system(result)

        print(f"[学习器] 完成 - 置信度: {result.confidence:.2f}")
        return result

    def _fetch_content(self, url: str) -> tuple:
        """获取文章内容"""
        import subprocess

        # 优先使用wechat-article-for-ai
        if "mp.weixin.qq.com" in url:
            try:
                result = subprocess.run(
                    ["wechat-to-md", url],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    content = result.stdout
                    title = extract_title_from_content(content)
                    return content, title, "微信公众号"
            except:
                pass

        # 备选：使用WebFetch
        try:
            from deva.naja.tools.web_fetch import fetch_url
            content = fetch_url(url)
            title = extract_title_from_content(content)
            return content, title, "网页"
        except:
            pass

        return "无法获取内容", "未知标题", "未知"

    def _generate_summary(self, title: str, content: str) -> str:
        """生成一句话总结"""
        # 简单实现：取标题
        return title

    def _extract_key_points(self, content: str) -> List[str]:
        """提取核心要点"""
        points = []

        # 简单实现：查找包含数字的行
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if any(c.isdigit() for c in line) and len(line) > 20 and len(line) < 200:
                points.append(line)
                if len(points) >= 5:
                    break

        if not points:
            points = ["内容已记录，待进一步分析"]

        return points

    def _calculate_confidence(self, result: LearningResult) -> float:
        """计算综合置信度"""
        conf = 0.5  # 基础置信度

        # 来源加成
        if result.source == "微信公众号":
            conf += 0.1
        elif result.source == "TechCrunch" or result.source == "36kr":
            conf += 0.15

        # 叙事强度加成
        conf += (result.narrative.narrative_strength - 0.5) * 0.2

        # 因果链数量加成
        conf += min(0.1, len(result.causality_chains) * 0.05)

        # 投资信号加成
        if result.investment.direction:
            conf += 0.1

        return min(0.9, max(0.3, conf))

    def _save_knowledge(self, result: LearningResult):
        """保存知识到文件"""
        import os
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)

        # 保存到知识库
        knowledge_file = f"{KNOWLEDGE_DIR}/article_knowledge.json"
        try:
            with open(knowledge_file, 'r', encoding='utf-8') as f:
                knowledge_list = json.load(f)
        except:
            knowledge_list = []

        # 添加新知识
        knowledge_list.append(asdict(result))

        # 只保留最近100条
        knowledge_list = knowledge_list[-100:]

        with open(knowledge_file, 'w', encoding='utf-8') as f:
            json.dump(knowledge_list, f, ensure_ascii=False, indent=2)

    def _update_narrative_db(self, result: LearningResult):
        """更新叙事数据库"""
        narratives = load_narratives()

        for narrative_name in result.related_narratives:
            found = False
            for n in narratives.get("narratives", []):
                if n.get("name") == narrative_name:
                    n["count"] = n.get("count", 0) + 1
                    n["last_seen"] = result.learned_at
                    found = True
                    break

            if not found:
                narratives.setdefault("narratives", []).append({
                    "name": narrative_name,
                    "count": 1,
                    "first_seen": result.learned_at,
                    "last_seen": result.learned_at,
                    "strength": result.narrative.narrative_strength
                })

        save_narratives(narratives)

    def _inject_to_decision_system(self, result: LearningResult) -> bool:
        """将因果关系注入到交易决策系统"""
        if not HAS_INJECTOR:
            print("[学习器] 跳过知识注入：AIKnowledgeInjector不可用")
            return False

        try:
            injector = AIKnowledgeInjector()

            # 构建要注入的知识条目
            new_knowledge = []

            # 从因果链条提取因果对
            for chain in result.causality_chains:
                entry = {
                    "id": f"article_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(new_knowledge)}",
                    "cause": chain.cause,
                    "effect": chain.effect,
                    "base_confidence": chain.confidence * 0.5,  # 文章知识降权
                    "source": result.source,
                    "original_title": result.title,
                    "extracted_at": datetime.now().isoformat(),
                    "category": "article_analysis",
                    "status": "observing",
                    "adjusted_confidence": chain.confidence * 0.25,  # 观察期折算
                    "evidence_count": 1,
                    "quality_score": 0,
                    "mechanism": chain.mechanism,
                    "timeframe": chain.timeframe
                }
                new_knowledge.append(entry)

            # 从投资方向提取因果对
            for direction in result.investment.direction:
                entry = {
                    "id": f"article_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(new_knowledge)}",
                    "cause": f"关注{direction}",
                    "effect": f"{direction}相关投资机会",
                    "base_confidence": result.confidence * 0.6,
                    "source": result.source,
                    "original_title": result.title,
                    "extracted_at": datetime.now().isoformat(),
                    "category": "article_analysis",
                    "status": "observing",
                    "adjusted_confidence": result.confidence * 0.3,
                    "evidence_count": 1,
                    "quality_score": 0,
                    "timeframe": "待评估"
                }
                new_knowledge.append(entry)

            # 从叙事提取因果对
            if result.narrative.current_narratives and result.narrative.narrative_alignment == "支持":
                entry = {
                    "id": f"article_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(new_knowledge)}",
                    "cause": f"叙事支持：{result.narrative.current_narratives[0]}",
                    "effect": "叙事强势，相关机会值得布局",
                    "base_confidence": result.narrative.narrative_strength * 0.5,
                    "source": result.source,
                    "original_title": result.title,
                    "extracted_at": datetime.now().isoformat(),
                    "category": "article_analysis",
                    "status": "observing",
                    "adjusted_confidence": result.narrative.narrative_strength * 0.25,
                    "evidence_count": 1,
                    "quality_score": 0,
                    "timeframe": "待评估"
                }
                new_knowledge.append(entry)

            # 调用注入器
            if new_knowledge:
                evaluation_result = {"new_knowledge": new_knowledge}
                counts = injector.inject_knowledge(evaluation_result)
                print(f"[学习器] ✅ 已注入到决策系统: {counts}")
                return True
            else:
                print("[学习器] 没有可注入的因果关系")
                return False

        except Exception as e:
            print(f"[学习器] 知识注入失败: {e}")
            import traceback
            traceback.print_exc()
            return False


# ============== 格式化输出 ==============
def format_learning_result(result: LearningResult) -> str:
    """格式化学习结果为微信回复"""

    reply = f"✅ 学习完成！\n\n"
    reply += f"📖 {result.title}\n"
    reply += f"📰 {result.source}\n"
    reply += f"🕐 {result.learned_at}\n\n"

    # 一句话总结
    reply += f"💬 {result.summary}\n\n"

    # 供需分析
    reply += "━━━━━━━━━━━━━━━\n"
    reply += "📊 供需关系\n"
    reply += "━━━━━━━━━━━━━━━\n"
    if result.supply_demand.demand_side:
        reply += f"需求方: {', '.join(result.supply_demand.demand_side)}\n"
    if result.supply_demand.supply_side:
        reply += f"供给方: {', '.join(result.supply_demand.supply_side)}\n"
    reply += f"状态: {result.supply_demand.imbalance}\n"
    if result.supply_demand.key_gap:
        reply += f"关键缺口: {result.supply_demand.key_gap}\n"
    reply += "\n"

    # 叙事分析
    reply += "━━━━━━━━━━━━━━━\n"
    reply += "🎯 热点叙事\n"
    reply += "━━━━━━━━━━━━━━━\n"
    if result.narrative.current_narratives:
        reply += f"当前叙事: {', '.join(result.narrative.current_narratives)}\n"
    reply += f"立场: {result.narrative.narrative_alignment}\n"
    reply += f"强度: {'🔴强' if result.narrative.narrative_strength > 0.7 else '🟡中' if result.narrative.narrative_strength > 0.4 else '🟢弱'}\n"
    reply += "\n"

    # 因果分析
    if result.causality_chains:
        reply += "━━━━━━━━━━━━━━━\n"
        reply += "🔗 因果链条\n"
        reply += "━━━━━━━━━━━━━━━\n"
        for i, chain in enumerate(result.causality_chains[:2], 1):
            reply += f"{i}. {chain.cause}\n"
            reply += f"   机制: {chain.mechanism}\n"
            reply += f"   预期: {chain.effect}\n"
            reply += f"   时间: {chain.timeframe}\n"
        reply += "\n"

    # 投资启示
    reply += "━━━━━━━━━━━━━━━\n"
    reply += "💰 投资启示\n"
    reply += "━━━━━━━━━━━━━━━\n"
    if result.investment.direction:
        reply += f"方向: {', '.join(result.investment.direction)}\n"
    if result.investment.opportunities:
        for opp in result.investment.opportunities[:2]:
            reply += f"✓ {opp}\n"
    if result.investment.risks:
        for risk in result.investment.risks[:2]:
            reply += f"⚠️ {risk}\n"
    reply += f"建议: {result.investment.position_suggestion}\n"
    reply += "\n"

    # 验证信号
    if result.investment.validation_signals:
        reply += "📡 验证信号:\n"
        for sig in result.investment.validation_signals[:2]:
            reply += f"   • {sig}\n"

    reply += "\n━━━━━━━━━━━━━━━\n"
    reply += f"🧠 置信度: {result.confidence:.0%} | 状态: 观察期\n"
    reply += "7天后验证通过将参与决策参考"

    return reply


# ============== 便捷函数 ==============
def learn_article_url(url: str) -> LearningResult:
    """学习文章URL"""
    learner = ArticleLearner()
    return learner.learn(url)


# ============== 与注意力文本处理架构集成 ==============

def learn_with_attention_pipeline(url: str) -> tuple[LearningResult, dict]:
    """
    使用注意力文本处理流水线学习文章

    这个函数整合了 ArticleLearner 的深度分析能力和新的 TextProcessingPipeline
    实现：一次处理、多方复用的效果

    Returns:
        (LearningResult, attention_info): 学习结果和注意力处理信息

    使用示例：
        result, info = learn_with_attention_pipeline("https://...")
        print(f"注意力分数: {info['attention_score']}")
        print(f"处理层级: {info['routing_level']}")
        print(f"信号已广播到: {info['subscribers']}")
    """
    # 尝试导入注意力处理模块
    try:
        from deva.naja.cognition.attention_text_router import (
            AttentionTextItem,
            TextSource,
            ManasState,
        )
        from deva.naja.cognition.text_processing_pipeline import get_text_pipeline
    except ImportError:
        # 如果没有新架构，降级到传统方式
        learner = ArticleLearner()
        return learner.learn(url), {}

    learner = ArticleLearner()

    # 1. 获取文章内容
    content, title, source = learner._fetch_content(url)

    # 2. 创建注意力文本项
    item = AttentionTextItem(
        text=content,
        title=title,
        url=url,
        source=TextSource.USER_ARTICLE,
        metadata={"original_source": source},
    )

    # 3. 使用流水线处理
    pipeline = get_text_pipeline()
    item = pipeline.process(item)

    # 4. 原有深度分析
    result = learner._analyze_content(content, title, url, source)

    # 5. 补充注意力处理信息
    attention_info = {
        "attention_score": item.attention_score,
        "routing_level": item.routing_level(),
        "raw_keywords": item.raw_keywords,
        "topic_candidates": item.topic_candidates,
        "matched_focus_topics": item.matched_focus_topics,
        "sentiment": item.sentiment if hasattr(item, 'sentiment') else None,
        "narrative_tags": item.narrative_tags if hasattr(item, 'narrative_tags') else [],
        "processed": item.processed,
        "bus_stats": pipeline.get_stats().get("bus_stats", {}),
    }

    # 6. 将分析结果同步回结构化信号
    if item.structured_signal:
        item.structured_signal.sentiment = result.narrative.narrative_strength
        item.structured_signal.narrative_tags = result.narrative.current_narratives

    # 7. 重新广播（带着深度分析结果）
    pipeline._bus.publish(item)

    return result, attention_info


def subscribe_article_learning(module_name: str, min_attention: float = 0.6):
    """
    订阅文章学习信号

    当有高注意力文章被处理时，会收到通知

    Args:
        module_name: 订阅模块名称
        min_attention: 最小注意力阈值

    使用示例：
        def on_article(item):
            print(f"收到高注意力文章: {item.title}")

        subscribe_article_learning("MyModule", min_attention=0.7)
    """
    from deva.naja.cognition.text_processing_pipeline import subscribe_to_signals

    def callback(item):
        # 这里可以添加自定义处理逻辑
        pass

    subscribe_to_signals(module_name, callback, min_attention=min_attention)


# ============== 测试 ==============
if __name__ == "__main__":
    # 测试
    result = LearningResult(
        title="测试：AI芯片供需失衡持续加剧",
        source="TechCrunch",
        learned_at="2026-04-03",
        summary="芯片短缺推动国产替代加速",
        supply_demand=SupplyDemandAnalysis(
            demand_side=["大厂", "创业公司"],
            supply_side=["英伟达", "AMD"],
            imbalance="供给不足",
            key_gap="高端芯片"
        ),
        narrative=NarrativeAnalysis(
            current_narratives=["算力军备竞赛", "中美竞争"],
            narrative_alignment="支持",
            narrative_strength=0.8
        ),
        causality_chains=[
            CausalityChain(
                cause="美国芯片禁令",
                mechanism="加速国产替代",
                effect="国产芯片公司机会",
                timeframe="中长期"
            )
        ],
        investment=InvestmentInsight(
            direction=["算力基础设施", "芯片设计"],
            opportunities=["国产替代机会"],
            risks=["技术差距风险"],
            position_suggestion="适度布局，观察验证"
        ),
        confidence=0.7,
        status="observing"
    )

    print(format_learning_result(result))
