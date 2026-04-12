"""
WisdomRetriever - 知识库检索器

根据 Manas 的状态，从爸爸的知识库中检索相关文章片段，
用于在合适的时机分享给爸爸，或校准 Naja 自身。

触发场景：
- attention_focus 切换（止损/止盈/积累/观望）
- harmony_state 变化（共振→阻力）
- bias_state 为 fear/greed
- portfolio_loss_pct > 阈值
- 长时间无操作后的突破时刻
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)


# IMA API 配置
IMA_API_BASE = "https://ima.qq.com/openapi/wiki/v1"
IMA_CLIENT_ID = os.environ.get("IMA_OPENAPI_CLIENTID", "")
IMA_API_KEY = os.environ.get("IMA_OPENAPI_APIKEY", "")
IMA_KB_ID = "cP5JYg2B-mVAzee2TMF6FoKQnSSnK6rgttsDETpj7To="


@dataclass
class WisdomSnippet:
    """知识片段"""
    title: str
    highlight: str
    media_id: str

    def clean_highlight(self) -> str:
        """去除 HTML 标签，清理高亮文本"""
        text = re.sub(r'<[^>]+>', '', self.highlight)
        return text.strip()


@dataclass
class TriggerContext:
    """触发上下文 - Manas 的状态快照"""
    attention_focus: str
    harmony_state: str
    bias_state: str
    should_act: bool
    portfolio_loss_pct: float
    portfolio_signal: str
    confidence_score: float
    action_type: str

    @classmethod
    def from_manas_output(cls, manas_dict: Dict[str, Any]) -> "TriggerContext":
        return cls(
            attention_focus=manas_dict.get("attention_focus", "watch"),
            harmony_state=manas_dict.get("harmony_state", "neutral"),
            bias_state=manas_dict.get("bias_state", "neutral"),
            should_act=manas_dict.get("should_act", False),
            portfolio_loss_pct=manas_dict.get("portfolio_loss_pct", 0.0),
            portfolio_signal=manas_dict.get("portfolio_signal", "none"),
            confidence_score=manas_dict.get("confidence_score", 0.5),
            action_type=manas_dict.get("action_type", "hold"),
        )


class WisdomRetriever:
    """
    知识库检索器

    将 Manas 的状态映射为搜索关键词，检索爸爸的文章片段，
    判断是否适合分享。
    """

    # 触发场景 → 搜索关键词映射（优化为更精准的一句话检索）
    TRIGGER_QUERIES: Dict[str, List[str]] = {
        "stop_loss": ["止损安慰 亏损接受 鼓励", "亏损不丢人 勇气", "知错就改 止损"],
        "take_profit": ["止盈见好就收 理性", "收获满足 落袋为安", "知足常乐"],
        "accumulate": ["定投积累 耐心坚持", "逆向投资 勇气信念", "慢慢变富 长期主义"],
        "rebalance": ["仓位平衡 风险管理", "动态调整 配置"],
        "watch": ["观望等待 不动", "休息也是投资", "耐心等机会"],
        "fear": ["市场恐惧 冷静应对", "不恐慌 理性", "别人恐惧我冷静"],
        "greed": ["贪婪警惕 理性", "市场狂热 清醒", "不贪是智慧"],
        "resistance": ["逆风坚持 突破", "困难勇气 信念", "阻力转化 成长"],
        "resonance": ["顺势而为 好运感恩", "顺势而为 知命", "好运要珍惜"],
        "breakthrough": ["突破成长 转折", "飞跃时刻 把握"],
    }

    # 需要触发检索的信号
    TRIGGER_SIGNALS = {
        "attention_focus", "harmony_state", "bias_state",
        "portfolio_signal", "confidence_score"
    }

    # 高置信度触发阈值
    LOW_CONFIDENCE_THRESHOLD = 0.4
    HIGH_LOSS_THRESHOLD = 0.05  # 5%

    def __init__(self):
        self._last_trigger_focus = None
        self._last_trigger_bias = None
        self._last_trigger_harmony = None
        self._recent_snippets: List[WisdomSnippet] = []
        
        # 统计信息
        self._trigger_count = 0
        self._last_trigger_time = None
        self._last_query = None
        self._last_best_snippet = None

    def should_trigger(self, context: TriggerContext) -> bool:
        """
        判断是否应该触发检索

        触发条件：
        1. 首次调用：检查是否有高优先级信号（亏损、fear/greed）
        2. attention_focus 变化
        3. harmony_state 变化（共振→阻力 或 反过来）
        4. bias_state 变成 fear/greed
        5. 亏损超过阈值
        """
        # 首次调用：检查高优先级信号
        if self._last_trigger_focus is None:
            self._last_trigger_focus = context.attention_focus
            self._last_trigger_bias = context.bias_state
            self._last_trigger_harmony = context.harmony_state
            
            # 首次也检查高优先级信号
            if context.portfolio_loss_pct > self.HIGH_LOSS_THRESHOLD:
                return True
            if context.bias_state in ("fear", "greed"):
                return True
            if context.attention_focus not in ("watch", "neutral"):
                return True
            return False

        # attention_focus 变化
        if context.attention_focus != self._last_trigger_focus:
            return True

        # bias_state 变成 fear/greed
        if context.bias_state in ("fear", "greed") and \
           context.bias_state != self._last_trigger_bias:
            return True

        # harmony_state 变化
        if context.harmony_state != self._last_trigger_harmony:
            return True

        # 亏损超过阈值
        if context.portfolio_loss_pct > self.HIGH_LOSS_THRESHOLD:
            return True

        # 更新状态
        self._last_trigger_focus = context.attention_focus
        self._last_trigger_bias = context.bias_state
        self._last_trigger_harmony = context.harmony_state

        return False

    def build_queries(self, context: TriggerContext) -> List[str]:
        """根据上下文构建搜索关键词列表"""
        queries = []

        # 1. 主要触发源
        if context.attention_focus != "watch":
            queries.extend(self.TRIGGER_QUERIES.get(context.attention_focus, []))

        # 2. bias 状态
        if context.bias_state in ("fear", "greed"):
            queries.extend(self.TRIGGER_QUERIES.get(context.bias_state, []))

        # 3. harmony 状态
        if context.harmony_state != "neutral":
            queries.extend(self.TRIGGER_QUERIES.get(context.harmony_state, []))

        # 4. 亏损时的额外关键词
        if context.portfolio_loss_pct > self.HIGH_LOSS_THRESHOLD:
            queries.extend(["亏损 接受 放下", "被套 应对"])

        # 去重，限制数量
        seen = set()
        unique_queries = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)

        return unique_queries[:3]

    def search(self, query: str, limit: int = 5) -> List[WisdomSnippet]:
        """
        搜索知识库

        Args:
            query: 搜索关键词
            limit: 返回数量

        Returns:
            知识片段列表
        """
        if not IMA_CLIENT_ID or not IMA_API_KEY:
            log.warning("[WisdomRetriever] IMA API credentials not configured")
            return []

        try:
            log.info(f"[WisdomRetriever] Searching knowledge base: query='{query}', limit={limit}")
            resp = requests.post(
                f"{IMA_API_BASE}/search_knowledge",
                headers={
                    "ima-openapi-clientid": IMA_CLIENT_ID,
                    "ima-openapi-apikey": IMA_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "knowledge_base_id": IMA_KB_ID,
                    "cursor": "",
                },
                timeout=10,
            )
            log.debug(f"[WisdomRetriever] Response status: {resp.status_code}")

            resp.raise_for_status()
            data = resp.json()
            log.debug(f"[WisdomRetriever] Response code: {data.get('code')}, msg: {data.get('msg')}")

            if data.get("code") != 0 and data.get("err") != 0:
                log.warning(f"[WisdomRetriever] API error: {data}")
                return []

            items = data.get("data", {}).get("info_list", [])
            snippets = []
            for item in items[:limit]:
                highlight = item.get("highlight_content", "")
                if highlight:
                    snippets.append(WisdomSnippet(
                        title=item.get("title", ""),
                        highlight=highlight,
                        media_id=item.get("media_id", ""),
                    ))

            log.info(f"[WisdomRetriever] Found {len(snippets)} snippets")
            return snippets

        except Exception as e:
            log.error(f"[WisdomRetriever] Search failed: {e}")
            return []

    def retrieve(self, context: TriggerContext) -> Dict[str, Any]:
        """
        完整检索流程

        1. 判断是否触发
        2. 构建查询
        3. 执行搜索
        4. 返回结果
        """
        if not self.should_trigger(context):
            return {"should_speak": False, "reason": "no_trigger"}

        queries = self.build_queries(context)
        if not queries:
            return {"should_speak": False, "reason": "no_query"}

        # 用第一个查询词搜索
        snippets = self.search(queries[0])

        if not snippets:
            return {
                "should_speak": False,
                "reason": "no_result",
                "query": queries[0],
            }

        self._recent_snippets = snippets

        # 记录统计
        import time
        self._trigger_count += 1
        self._last_trigger_time = time.time()
        self._last_query = queries[0]
        self._last_best_snippet = snippets[0].clean_highlight()

        return {
            "should_speak": True,
            "reason": f"triggered_by_{context.attention_focus}",
            "query": queries[0],
            "snippets": [
                {
                    "title": s.title,
                    "highlight": s.clean_highlight(),
                    "raw_highlight": s.highlight,
                }
                for s in snippets
            ],
            "best_snippet": snippets[0].clean_highlight(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息，用于 UI 展示"""
        return {
            "trigger_count": self._trigger_count,
            "last_trigger_time": self._last_trigger_time,
            "last_query": self._last_query,
            "last_best_snippet": self._last_best_snippet,
            "last_focus": self._last_trigger_focus,
            "last_bias": self._last_trigger_bias,
            "last_harmony": self._last_trigger_harmony,
        }

    def format_wisdom_speech(self, context: TriggerContext) -> Optional[str]:
        """
        格式化要说的话

        根据上下文把检索到的知识片段转化成自然的语言。
        这个方法由外部 LLM 调用更好，这里只是基础格式化。
        """
        result = self.retrieve(context)

        if not result.get("should_speak"):
            return None

        snippet = result.get("best_snippet", "")
        trigger_reason = result.get("reason", "")

        # 简单格式化
        # 实际应该由 LLM 根据上下文生成更自然的话
        return f"【来自你的文章】{snippet}"


# 便捷函数
def retrieve_wisdom(manas_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    便捷函数：根据 Manas 输出检索知识

    Usage:
        wisdom = retrieve_wisdom(manas_output.to_dict())
        if wisdom.get("should_speak"):
            best = wisdom["best_snippet"]
            ...
    """
    retriever = WisdomRetriever()
    context = TriggerContext.from_manas_output(manas_dict)
    return retriever.retrieve(context)


class WisdomSpeaker:
    """
    智慧播报器

    将检索到的知识片段 + 当前状态发给 LLM，
    生成一句适合当前场景的自然语言。
    """

    # 不同场景的 prompt 模板
    PROMPT_TEMPLATES = {
        "stop_loss": """你是一个贴心的投资顾问，正在帮助一个成熟的投资者面对止损时刻。
刚刚从知识库检索到一段话：
「{snippet}」

当前场景：
- 爸爸正在面对亏损，需要做出止损决策
- 他可能会有些沮丧或犹豫

请结合检索内容，用温暖但有力量的口吻，说一句适合此刻的话。
要求：
- 口语化，自然，不要书面腔
- 30-50字左右
- 不要空洞的大道理，要有具体的关怀
- 可以适当引用或化用检索内容
- 不要加引号或书名号""",

        "take_profit": """你是一个理性的投资顾问，正在帮助一个投资者面对止盈时刻。
刚刚从知识库检索到一段话：
「{snippet}」

当前场景：
- 爸爸的投资盈利了，可能有些舍不得卖
- 市场可能有些过热的信号

请结合检索内容，用轻松释然的语气，说一句适合此刻的话。
要求：
- 口语化，自然
- 30-50字左右
- 让他感到收获的满足感，同时保持理性
- 不要加引号或书名号""",

        "accumulate": """你是一个耐心的投资顾问，正在鼓励一个定投者。
刚刚从知识库检索到一段话：
「{snippet}」

当前场景：
- 市场可能有些低迷，爸爸在坚持定投
- 需要耐心和信念的支持

请结合检索内容，用温暖鼓励的语气，说一句适合此刻的话。
要求：
- 口语化，自然
- 30-50字左右
- 传递坚持的价值和长期主义
- 不要加引号或书名号""",

        "fear": """你是一个沉稳的投资顾问，正在安抚一个有些恐慌的投资者。
刚刚从知识库检索到一段话：
「{snippet}」

当前场景：
- 市场下跌，爸爸可能有些害怕
- 需要冷静和理性的声音

请结合检索内容，用沉稳有力的语气，说一句适合此刻的话。
要求：
- 口语化，自然
- 30-50字左右
- 帮助他冷静下来
- 不要加引号或书名号""",

        "greed": """你是一个清醒的投资顾问，正在提醒一个有些贪婪的投资者。
刚刚从知识库检索到一段话：
「{snippet}」

当前场景：
- 市场火热，爸爸可能有些冲动了
- 需要一盆冷水让他清醒

请结合检索内容，用睿智警醒的语气，说一句适合此刻的话。
要求：
- 口语化，自然
- 30-50字左右
- 让他意识到风险
- 不要加引号或书名号""",

        "resistance": """你是一个坚定的投资顾问，正在支持一个逆风的投资者。
刚刚从知识库检索到一段话：
「{snippet}」

当前场景：
- 爸爸的投资遇到了困难，市场不利
- 需要毅力和信念的支持

请结合检索内容，用坚定温暖的语气，说一句适合此刻的话。
要求：
- 口语化，自然
- 30-50字左右
- 传递坚持和突破的力量
- 不要加引号或书名号""",

        "resonance": """你是一个感恩的投资顾问，和爸爸分享顺势的喜悦。
刚刚从知识库检索到一段话：
「{snippet}」

当前场景：
- 市场走好，爸爸的投资顺应了趋势
- 这是难得的好运气

请结合检索内容，用愉悦感恩的语气，说一句适合此刻的话。
要求：
- 口语化，自然
- 30-50字左右
- 让他感受顺势的美好
- 不要加引号或书名号""",
    }

    # 默认场景 prompt
    DEFAULT_PROMPT = """你是一个贴心的投资顾问。
刚刚从知识库检索到一段话：
「{snippet}」

请用温暖自然的语气，把这段内容的核心思想转化成一句说给投资者听的话。
要求：
- 口语化，自然
- 30-50字左右
- 不要空洞的大道理
- 不要加引号或书名号"""

    def speak(self, snippet: str, scenario: str = "default") -> str:
        """
        根据场景生成自然语言

        Args:
            snippet: 检索到的知识片段
            scenario: 场景类型 (stop_loss/take_profit/accumulate/fear/greed/resistance/resonance/default)

        Returns:
            一句适合当前场景的自然语言
        """
        try:
            from deva.llm import sync_gpt

            template = self.PROMPT_TEMPLATES.get(scenario, self.DEFAULT_PROMPT)
            prompt = template.format(snippet=snippet)

            result = sync_gpt(prompt)
            if result:
                # 清理结果，去除首尾空白
                return result.strip()

            # LLM 调用失败，返回原始片段
            return snippet[:50] + "..." if len(snippet) > 50 else snippet

        except ImportError:
            log.warning("LLM not available, returning raw snippet")
            return snippet[:50] + "..." if len(snippet) > 50 else snippet
        except Exception as e:
            log.error(f"WisdomSpeaker.speak failed: {e}")
            return snippet[:50] + "..." if len(snippet) > 50 else snippet


def format_wisdom_for_speech(wisdom_result: Dict[str, Any], context: TriggerContext) -> Optional[str]:
    """
    格式化智慧输出为说给爸爸的话

    这个函数应该由有 LLM 调用能力的模块使用，
    用 LLM 生成更自然、符合语境的表达。
    """
    if not wisdom_result.get("should_speak"):
        return None

    speaker = WisdomSpeaker()

    # 确定场景
    scenario = context.attention_focus
    if context.bias_state in ("fear", "greed"):
        scenario = context.bias_state

    return speaker.speak(
        snippet=wisdom_result.get("best_snippet", ""),
        scenario=scenario
    )
