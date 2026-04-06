"""
AI Knowledge Injector v2.0 - AI知识注入器（深思熟虑版）

核心设计：
1. 新知识进入"观察期"，只记录不参与决策
2. 累积验证后（多来源/多天/强信号）才考虑加入决策
3. 重大变化时通知爸爸确认
4. 所有知识都需要"实习期"，不能直接上岗

注意：存储位置已迁移到 deva/naja/knowledge/
"""

import json
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from enum import Enum

from deva.naja.knowledge import get_knowledge_store, get_state_manager, get_cognition_interface

log = logging.getLogger(__name__)

# 知识存储路径 - 现在使用项目目录，方便 AI Agent 读取
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
KNOWLEDGE_FILE = KNOWLEDGE_DIR / "causality_knowledge_v2.json"

# 知识状态枚举
class KnowledgeStatus(Enum):
    OBSERVING = "observing"      # 观察期：新知识
    VALIDATING = "validating"    # 验证中：证据积累中
    QUALIFIED = "qualified"      # 合格：可参与决策
    EXPIRED = "expired"          # 过期：长时间无新证据

# 来源可信度权重
SOURCE_WEIGHTS = {
    "TechCrunch": 1.0,
    "VentureBeat": 0.9,
    "机器之心": 0.8,
    "量子位": 0.8,
    "HackerNews": 0.6,
    "Twitter": 0.5,
    "微信公众号": 0.5,
    "arXiv": 0.7,
    "HuggingFace": 0.5,
    "GitHub": 0.4,
    "unknown": 0.3
}

# 事件强度阈值
EVENT_INTENSITY = {
    # 融资规模（美元）
    "mega_funding": (100_000_000, 1.0),      # >1亿 满分
    "large_funding": (10_000_000, 0.8),      # >1000万
    "medium_funding": (1_000_000, 0.5),       # >100万
    "small_funding": (0, 0.2),                # <100万 低权重

    # 模型发布
    "major_model": ["GPT-5", "Gemini", "Claude", "Llama", "GPT-4", "o1", "o3", "o4"],
    "minor_model": ["Gemma", "Mistral", "Phi", "Qwen", "Yi"],

    # 收购
    "major_acquisition": 1_000_000_000,  # >10亿
}


class AIKnowledgeInjector:
    """
    AI知识注入器 v2.0 - 深思熟虑版

    设计原则：
    - 新知识先观察，不直接参与交易
    - 累积足够证据后才考虑加入决策
    - 重大变化必须通知用户确认
    """

    def __init__(self):
        self._knowledge_entries: List[Dict] = []
        self._load_existing()

    def _load_existing(self):
        """加载已有知识"""
        if KNOWLEDGE_FILE.exists():
            try:
                with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._knowledge_entries = data.get("knowledge", [])
                log.info(f"[AI_Knowledge_v2] 加载了 {len(self._knowledge_entries)} 条已有知识")

                # 统计各状态数量
                status_counts = {}
                for e in self._knowledge_entries:
                    status = e.get("status", "observing")
                    status_counts[status] = status_counts.get(status, 0) + 1
                log.info(f"[AI_Knowledge_v2] 状态分布: {status_counts}")
            except Exception as e:
                log.warning(f"[AI_Knowledge_v2] 加载知识失败: {e}")
                self._knowledge_entries = []

    def _save_knowledge(self):
        """保存知识到文件"""
        try:
            KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

            data = {
                "version": "2.0",
                "last_updated": datetime.now().isoformat(),
                "knowledge_count": len(self._knowledge_entries),
                "knowledge": self._knowledge_entries
            }

            with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            log.info(f"[AI_Knowledge_v2] 已保存 {len(self._knowledge_entries)} 条知识")
        except Exception as e:
            log.error(f"[AI_Knowledge_v2] 保存知识失败: {e}")

    def _extract_funding_amount(self, text: str) -> Optional[float]:
        """从文本中提取融资金额（美元）"""
        patterns = [
            r'\$([0-9,]+)\s*(?:million|M|m)',
            r'\$([0-9,]+)\s*(?:billion|B)',
            r'([0-9,]+)\s*(?:million|M)\s*(?:dollar|美元)',
            r'([0-9,]+)\s*(?:billion|B)\s*(?:dollar|美元)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                amount = float(amount_str)

                if 'billion' in pattern.lower() or 'B' in pattern:
                    amount *= 1_000_000_000
                elif 'million' in pattern.lower() or 'M' in pattern:
                    amount *= 1_000_000

                return amount

        return None

    def _is_major_event(self, title: str, source: str) -> tuple[bool, float, str]:
        """
        判断是否为重大事件

        Returns:
            (是否重大, 强度分数, 原因)
        """
        score = SOURCE_WEIGHTS.get(source, 0.3)

        # 检查融资规模
        funding = self._extract_funding_amount(title)
        if funding:
            if funding >= EVENT_INTENSITY["mega_funding"][0]:
                return True, 1.0, f"超大融资: ${funding/1e9:.1f}B"
            elif funding >= EVENT_INTENSITY["large_funding"][0]:
                return True, 0.8, f"大额融资: ${funding/1e6:.0f}M"
            elif funding >= EVENT_INTENSITY["medium_funding"][0]:
                return False, 0.5, f"中等融资: ${funding/1e6:.0f}M"
            else:
                return False, 0.2, f"小额融资: ${funding/1e3:.0f}K"

        # 检查模型发布
        for major in EVENT_INTENSITY["major_model"]:
            if major.lower() in title.lower():
                return True, 0.9, f"重磅模型: {major}"

        for minor in EVENT_INTENSITY["minor_model"]:
            if minor.lower() in title.lower():
                return True, 0.6, f"模型更新: {minor}"

        # 检查收购
        if "acquired" in title.lower() or "收购" in title:
            if funding and funding >= EVENT_INTENSITY["major_acquisition"]:
                return True, 1.0, f"重大收购: ${funding/1e9:.1f}B"

        return False, score, f"普通AI动态"

    def _evaluate_knowledge_quality(self, entry: Dict, existing_same_type: List[Dict]) -> Dict[str, Any]:
        """
        评估知识质量

        Returns:
            评估结果：状态、置信度、是否通知用户
        """
        status = KnowledgeStatus.OBSERVING.value
        adjusted_confidence = entry.get("base_confidence", 0.5) * 0.5  # 观察期权重减半
        notify_user = False
        notify_reason = ""

        # 1. 检查是否重大事件
        is_major, intensity, reason = self._is_major_event(
            entry.get("original_title", ""),
            entry.get("source", "unknown")
        )

        if is_major:
            adjusted_confidence = entry.get("base_confidence", 0.5) * 0.7
            status = KnowledgeStatus.VALIDATING.value
            notify_user = True
            notify_reason = f"⚠️ 重大AI事件: {reason}，进入观察期"

        # 2. 检查多源验证
        same_cause_count = len(existing_same_type)
        if same_cause_count >= 2:
            status = KnowledgeStatus.VALIDATING.value
            adjusted_confidence *= 1.2  # 多源加成
            notify_user = True
            notify_reason = f"📊 同类证据+{same_cause_count}条，进入验证期"

        # 3. 检查时间累积（需要多天验证）
        days_tracked = (datetime.now() - datetime.fromisoformat(entry["extracted_at"])).days
        if days_tracked >= 7 and same_cause_count >= 1:
            status = KnowledgeStatus.QUALIFIED.value
            adjusted_confidence = entry.get("base_confidence", 0.5)
            notify_reason = f"✅ 经过{days_tracked}天验证，知识正式上岗"

        # 4. 检查过期
        if days_tracked >= 30 and status == KnowledgeStatus.OBSERVING.value:
            status = KnowledgeStatus.EXPIRED.value

        return {
            "status": status,
            "adjusted_confidence": min(adjusted_confidence, 0.9),  # 最高0.9
            "notify_user": notify_user,
            "notify_reason": notify_reason,
            "quality_score": intensity * 0.5 + same_cause_count * 0.1
        }

    def extract_and_evaluate_knowledge(self, news_items: List[Dict], invest_news: List[Dict] = None) -> Dict[str, Any]:
        """
        提取并评估知识（深思熟虑版）

        Returns:
            {
                "new_knowledge": [...],     # 新知识
                "validating_knowledge": [...],  # 验证中的知识
                "qualified_knowledge": [...],   # 正式可用的知识
                "notifications": [...]     # 需要通知用户的内容
            }
        """
        all_news = (news_items or []) + (invest_news or [])

        result = {
            "new_knowledge": [],
            "validating_knowledge": [],
            "qualified_knowledge": [],
            "notifications": []
        }

        for news in all_news:
            title = news.get("title", "")
            source = news.get("source", "unknown")

            # 提取因果关系
            entries = self._extract_causality(title, source)
            if not entries:
                continue

            for entry in entries:
                # 检查是否重复
                existing_same_type = [
                    e for e in self._knowledge_entries
                    if e.get("cause", "").lower() in entry["cause"].lower()
                ]

                # 评估质量
                evaluation = self._evaluate_knowledge_quality(entry, existing_same_type)

                entry["status"] = evaluation["status"]
                entry["adjusted_confidence"] = evaluation["adjusted_confidence"]
                entry["quality_score"] = evaluation["quality_score"]
                entry["evidence_count"] = len(existing_same_type) + 1

                result["new_knowledge"].append(entry)

                # 分类
                if evaluation["status"] == KnowledgeStatus.QUALIFIED.value:
                    result["qualified_knowledge"].append(entry)
                elif evaluation["status"] == KnowledgeStatus.VALIDATING.value:
                    result["validating_knowledge"].append(entry)

                # 通知
                if evaluation["notify_user"]:
                    result["notifications"].append({
                        "type": "knowledge_update",
                        "reason": evaluation["notify_reason"],
                        "knowledge": entry
                    })

        return result

    def _extract_causality(self, title: str, source: str) -> List[Dict]:
        """从标题中提取因果关系"""
        entries = []

        # 因果规则
        rules = [
            {
                "keywords": ["GPT", "Claude", "Gemini", "Llama", "Mistral", "新模型", "开源模型", "o1", "o3"],
                "cause_prefix": "大模型发布",
                "effect": "AI概念股/科技股可能受益",
                "base_confidence": 0.75
            },
            {
                "keywords": ["融资", "funding", "raises", "Series", "invested", "accquires"],
                "cause_prefix": "AI公司融资",
                "effect": "AI赛道关注度提升",
                "base_confidence": 0.8
            },
            {
                "keywords": ["Nvidia", "GPU", "芯片", "H100", "算力", "hardware", "AMD"],
                "cause_prefix": "AI硬件突破",
                "effect": "算力/芯片概念股受益",
                "base_confidence": 0.85
            },
            {
                "keywords": ["开源", "open source", "released", "available"],
                "cause_prefix": "AI技术开源",
                "effect": "AI应用层机会增加",
                "base_confidence": 0.7
            },
            {
                "keywords": ["监管", "regulation", "ban", "policy", "政府", "安全"],
                "cause_prefix": "AI监管消息",
                "effect": "AI行业短期承压",
                "base_confidence": 0.65
            },
            {
                "keywords": ["收购", "acquired", "acquisition", "并购"],
                "cause_prefix": "AI公司收购",
                "effect": "AI整合趋势加速",
                "base_confidence": 0.8
            }
        ]

        for rule in rules:
            if any(kw.lower() in title.lower() for kw in rule["keywords"]):
                entry = {
                    "id": f"ai_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(entries)}",
                    "cause": f"{rule['cause_prefix']}: {title[:50]}",
                    "effect": rule["effect"],
                    "base_confidence": rule["base_confidence"],
                    "source": source,
                    "original_title": title,
                    "extracted_at": datetime.now().isoformat(),
                    "category": "ai_tech",
                    "status": KnowledgeStatus.OBSERVING.value,  # 默认观察期
                    "adjusted_confidence": rule["base_confidence"] * 0.5,
                    "evidence_count": 1,
                    "quality_score": 0
                }
                entries.append(entry)

        return entries

    def inject_knowledge(self, evaluation_result: Dict[str, Any]) -> Dict[str, int]:
        """
        注入评估后的知识

        同时写入：
        1. 原有的 self._knowledge_entries (向后兼容)
        2. 新的 knowledge_store (学习层)

        Returns:
            各状态注入数量
        """
        counts = {"new": 0, "validating": 0, "qualified": 0}

        existing_causes = {e.get("cause", ""): e for e in self._knowledge_entries}

        new_store_entries = []

        for entry in evaluation_result.get("new_knowledge", []):
            cause = entry.get("cause", "")

            if cause in existing_causes:
                existing = existing_causes[cause]
                existing["evidence_count"] = max(existing.get("evidence_count", 1), entry.get("evidence_count", 1))
                existing["last_seen"] = entry["extracted_at"]
                existing["status"] = entry["status"]
                existing["adjusted_confidence"] = max(
                    existing.get("adjusted_confidence", 0),
                    entry.get("adjusted_confidence", 0)
                )
                log.info(f"[AI_Knowledge_v2] 更新知识: {cause[:40]}...")
            else:
                self._knowledge_entries.append(entry)
                existing_causes[cause] = entry
                counts["new"] += 1

                if entry["status"] == KnowledgeStatus.VALIDATING.value:
                    counts["validating"] += 1
                elif entry["status"] == KnowledgeStatus.QUALIFIED.value:
                    counts["qualified"] += 1

                new_store_entries.append(entry)

        if counts["new"] > 0:
            self._save_knowledge()
            log.info(f"[AI_Knowledge_v2] 注入统计: {counts}")

            try:
                from deva.naja.knowledge import get_knowledge_store, KnowledgeEntry
                import uuid

                store = get_knowledge_store()

                for entry in new_store_entries:
                    existing = store.get_by_cause(entry.get("cause", ""))
                    if existing:
                        continue

                    knowledge_entry = KnowledgeEntry(
                        id=str(uuid.uuid4())[:8],
                        cause=entry.get("cause", ""),
                        effect=entry.get("effect", ""),
                        base_confidence=entry.get("adjusted_confidence", 0.5),
                        source=entry.get("source", "article_learner"),
                        original_title=entry.get("original_title", ""),
                        extracted_at=entry.get("extracted_at", ""),
                        category=entry.get("category", "general"),
                        status=entry.get("status", "observing"),
                        adjusted_confidence=entry.get("adjusted_confidence", 0.5),
                        evidence_count=entry.get("evidence_count", 1),
                        quality_score=entry.get("quality_score", 0.5),
                        mechanism=entry.get("mechanism", ""),
                        timeframe=entry.get("timeframe", ""),
                    )
                    store.add(knowledge_entry)

                log.info(f"[AI_Knowledge_v2] 已同步到 knowledge_store: {len(new_store_entries)} 条")
            except Exception as e:
                log.warning(f"[AI_Knowledge_v2] 同步到 knowledge_store 失败: {e}")

        return counts

    def get_knowledge_for_trading(self) -> Dict[str, Any]:
        """
        获取可用于交易决策的知识
        """
        # 只返回验证通过的知识
        qualified = [
            {
                "cause": e["cause"],
                "effect": e["effect"],
                "confidence": e["adjusted_confidence"],
                "evidence_count": e.get("evidence_count", 1),
                "days_tracked": (datetime.now() - datetime.fromisoformat(e["extracted_at"])).days
            }
            for e in self._knowledge_entries
            if e.get("status") == KnowledgeStatus.QUALIFIED.value
        ]

        # 验证中的知识（低权重）
        validating = [
            {
                "cause": e["cause"],
                "effect": e["effect"],
                "confidence": e["adjusted_confidence"] * 0.3,  # 低权重
                "evidence_count": e.get("evidence_count", 1),
                "days_tracked": (datetime.now() - datetime.fromisoformat(e["extracted_at"])).days
            }
            for e in self._knowledge_entries
            if e.get("status") == KnowledgeStatus.VALIDATING.value
        ]

        return {
            "qualified_knowledge": qualified,
            "validating_knowledge": validating,
            "qualified_count": len(qualified),
            "validating_count": len(validating),
            "observing_count": len([e for e in self._knowledge_entries if e.get("status") == KnowledgeStatus.OBSERVING.value])
        }

    def generate_notification_text(self, evaluation_result: Dict[str, Any]) -> Optional[str]:
        """生成通知文本"""
        notifications = evaluation_result.get("notifications", [])
        if not notifications:
            return None

        lines = ["🧠 AI知识库更新通知\n━━━━━━━━━━━━━━━━━━━━━━\n"]

        for n in notifications[:5]:  # 最多5条
            reason = n.get("reason", "")
            k = n.get("knowledge", {})
            lines.append(f"{reason}")
            lines.append(f"  📰 {k.get('original_title', '')[:40]}...")
            lines.append(f"  📊 来源: {k.get('source', 'unknown')} | 状态: {k.get('status', 'unknown')}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 新知识进入观察期，不影响当前交易决策")

        return "\n".join(lines)


def send_notification(text: str, phone: str = "+8618626880688"):
    """发送通知"""
    try:
        import subprocess
        cmd = [
            'osascript', '-e',
            f'''tell application "Messages"
                send "{text.replace('"', '\\"')}" to buddy "{phone}"
            end tell'''
        ]
        subprocess.run(cmd, capture_output=True, timeout=10)
        return True
    except Exception as e:
        log.warning(f"通知发送失败: {e}")
        return False


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    injector = AIKnowledgeInjector()

    # 模拟新闻
    test_news = [
        {"title": "OpenAI 发布 GPT-5 新模型", "source": "TechCrunch"},
        {"title": "Anthropic 融资 20亿美元", "source": "TechCrunch"},
        {"title": "Meta 收购 AI 芯片公司", "source": "VentureBeat"},
    ]

    # 评估
    result = injector.extract_and_evaluate_knowledge(test_news)

    print(f"新知识: {len(result['new_knowledge'])}")
    print(f"验证中: {len(result['validating_knowledge'])}")
    print(f"正式: {len(result['qualified_knowledge'])}")

    for n in result.get("notifications", []):
        print(f"\n通知: {n['reason']}")
        print(f"  知识: {n['knowledge']['cause'][:50]}")

    # 生成通知
    notification = injector.generate_notification_text(result)
    if notification:
        print("\n" + notification)
