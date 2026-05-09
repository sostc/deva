"""Naja agent interface.

This is the dialogue-first application layer. It exposes Naja as an agent with
skills/tools, while web handlers and local skill scripts stay thin adapters.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AgentTool:
    name: str
    description: str
    external_effect: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NajaAgent:
    """Dialogue and skill facade for Naja."""

    def __init__(self):
        self.name = "Naja"
        self.role = "持续学习的市场认知与策略协同 agent"
        self._dialogue_history: List[Dict[str, Any]] = []
        self._tools = {
            "ask": AgentTool("ask", "回答市场、叙事、热点、策略影响相关问题"),
            "digest": AgentTool("digest", "生成市场学习汇报"),
            "api_catalog": AgentTool("api_catalog", "查看 Naja 全系统 API 端点能力目录"),
            "send_digest": AgentTool("send_digest", "发送市场学习汇报到钉钉/手机", external_effect=True),
            "capabilities": AgentTool("capabilities", "查看 Naja Agent 可用能力"),
        }

    def capabilities(self) -> Dict[str, Any]:
        from deva.naja.application.api_catalog import get_api_catalog

        catalog = get_api_catalog()
        return {
            "name": self.name,
            "role": self.role,
            "primary_interface": "skill/dialogue",
            "web_role": "status_mirror",
            "tools": [tool.to_dict() for tool in self._tools.values()],
            "api_groups": catalog.get("group_names", []),
            "api_endpoint_count": catalog.get("total", 0),
            "dialogue_turns": len(self._dialogue_history),
        }

    def ask(
        self,
        question: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from deva.naja.application.market_copilot import get_market_copilot

        question = (question or "").strip()
        result = get_market_copilot().answer(question)
        intent = self._infer_intent(question)
        agent_answer = self._shape_agent_answer(result.get("answer", ""), intent)

        turn = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "intent": intent,
            "question": question,
            "answer": agent_answer,
        }
        self._dialogue_history.append(turn)
        self._dialogue_history = self._dialogue_history[-50:]

        return {
            "agent": self.capabilities(),
            "session_id": session_id,
            "intent": intent,
            "answer": agent_answer,
            "raw": result,
            "recent_dialogue": self._dialogue_history[-5:],
            "context": context or {},
        }

    def run_skill(
        self,
        skill: str,
        payload: Optional[Dict[str, Any]] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        payload = payload or {}
        skill = (skill or "").strip().lower()

        if skill in {"ask", "question", "chat"}:
            return self.ask(
                payload.get("question") or payload.get("q") or "",
                session_id=payload.get("session_id", "default"),
                context=payload.get("context") or {},
            )
        if skill in {"digest", "report"}:
            from deva.naja.application.market_copilot import get_market_copilot

            digest = get_market_copilot().build_digest()
            return {
                "agent": self.capabilities(),
                "skill": "digest",
                "digest": digest.to_dict(),
                "markdown": get_market_copilot().format_digest_markdown(digest),
            }
        if skill in {"api_catalog", "endpoints", "apis", "api"}:
            from deva.naja.application.api_catalog import get_api_catalog

            group = payload.get("group") or payload.get("category")
            catalog = get_api_catalog(group=group)
            return {
                "agent": self.capabilities(),
                "skill": "api_catalog",
                "group": group,
                "catalog": catalog,
                "markdown": self._format_api_catalog(catalog),
            }
        if skill in {"send_digest", "send", "notify"}:
            if not confirm:
                return {
                    "agent": self.capabilities(),
                    "skill": "send_digest",
                    "success": False,
                    "error": "external_effect_requires_confirm",
                }
            from deva.naja.application.market_copilot import get_market_copilot

            return {
                "agent": self.capabilities(),
                "skill": "send_digest",
                "success": True,
                "result": get_market_copilot().send_digest(
                    channels=payload.get("channels") or ["dingtalk", "phone"],
                    force=bool(payload.get("force", False)),
                ),
            }
        if skill in {"capabilities", "tools"}:
            return self.capabilities()

        return {
            "agent": self.capabilities(),
            "success": False,
            "error": f"unknown_skill:{skill}",
        }

    def _infer_intent(self, question: str) -> str:
        q = question.lower()
        if any(word in q for word in ["策略", "strategy", "调参", "买", "卖"]):
            return "strategy"
        if any(word in q for word in ["新闻", "叙事", "热点", "narrative"]):
            return "narrative"
        if any(word in q for word in ["天时", "地利", "人和"]):
            return "situation"
        if any(word in q for word in ["发送", "钉钉", "手机", "通知"]):
            return "notification"
        return "market_brief"

    def _shape_agent_answer(self, base_answer: str, intent: str) -> str:
        prefix = {
            "strategy": "我按策略影响来回答。\n",
            "narrative": "我按叙事和热点来回答。\n",
            "situation": "我按天时、地利、人和来回答。\n",
            "notification": "发送属于外部动作，需要明确确认。\n",
            "market_brief": "我先给综合判断。\n",
        }.get(intent, "")
        return f"{prefix}{base_answer}".strip()

    def _format_api_catalog(self, catalog: Dict[str, Any]) -> str:
        lines = [f"Naja API 能力目录（{catalog.get('total', 0)} 个端点）"]
        groups = catalog.get("groups", {})
        for group_name in sorted(groups.keys()):
            lines.append(f"\n## {group_name}")
            for endpoint in groups[group_name]:
                methods = ",".join(endpoint.get("methods", []))
                effect = " 外部动作" if endpoint.get("external_effect") else ""
                lines.append(
                    f"- {methods} {endpoint.get('path')} - {endpoint.get('description')}；"
                    f"skill: {endpoint.get('skill_hint')}{effect}"
                )
        return "\n".join(lines)


_agent: Optional[NajaAgent] = None


def get_naja_agent() -> NajaAgent:
    global _agent
    if _agent is None:
        _agent = NajaAgent()
    return _agent
