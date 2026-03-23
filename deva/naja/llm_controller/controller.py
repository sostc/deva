"""LLM controller for strategy adjustments."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from deva import NB

from ..radar import get_radar_engine
from ..cognition.insight import get_insight_engine
from ..cognition.engine import get_cognition_engine
from ..strategy import get_strategy_manager
from ..strategy.result_store import get_result_store
from ..config import get_llm_config


LLM_DECISIONS_TABLE = "naja_llm_decisions"
STRATEGY_METRICS_TABLE = "naja_strategy_metrics"


@dataclass
class LLMDecision:
    id: str
    ts: float
    summary: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "decision_id": self.id,
            "timestamp": self.ts,
            "summary": self.summary,
            "actions": self.actions,
            "reason": self.reason,
        }


class LLMController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._db = NB(LLM_DECISIONS_TABLE)
        self._last_run_ts = 0.0
        cfg = get_llm_config()
        self._min_interval_seconds = float(cfg.get("min_interval_seconds", 300))
        self._initialized = True

    def _ensure_strategies_loaded(self):
        mgr = get_strategy_manager()
        strategies = mgr.list_all()
        if not strategies:
            mgr.reload_all()
        return mgr.list_all()

    async def review_and_adjust(
        self,
        *,
        window_seconds: int = 600,
        strategy_ids: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> dict:
        cfg = get_llm_config()
        now = time.time()
        if now - self._last_run_ts < self._min_interval_seconds:
            return {
                "success": False,
                "error": "LLM 调节过于频繁，请稍后再试",
                "next_available_in": self._min_interval_seconds - (now - self._last_run_ts),
            }

        mgr = get_strategy_manager()
        all_strategies = self._ensure_strategies_loaded()
        strategy_list = [{"id": s.id, "name": s.name} for s in all_strategies]

        radar_summary = get_radar_engine().summarize(window_seconds=window_seconds)
        memory_summary = get_cognition_engine().summarize_for_llm()
        metrics = self._collect_strategy_metrics(strategy_ids)
        metrics_index = {m.get("strategy_id"): m for m in metrics if isinstance(m, dict)}

        try:
            decision = await self._request_llm(radar_summary, memory_summary, metrics, strategy_list, cfg)
        except Exception as e:
            return {"success": False, "error": str(e)}

        actions = decision.actions
        apply_result = self._apply_actions(actions, metrics_index, cfg, dry_run=dry_run)

        self._record_decision(decision)
        self._last_run_ts = now

        return {
            "success": True,
            "decision": decision.to_dict(),
            "apply_result": apply_result,
            "dry_run": dry_run,
        }

    def _collect_strategy_metrics(self, strategy_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
        mgr = get_strategy_manager()
        store = get_result_store()
        metrics: List[Dict[str, Any]] = []
        target_entries = mgr.list_all()
        if strategy_ids:
            ids = set(strategy_ids)
            target_entries = [e for e in target_entries if e.id in ids]

        db = NB(STRATEGY_METRICS_TABLE)
        ts = time.time()

        for entry in target_entries:
            stats = store.get_stats(entry.id)
            item = {
                "strategy_id": entry.id,
                "strategy_name": entry.name,
                "strategy_type": getattr(entry._metadata, "strategy_type", "legacy"),
                "strategy_params": getattr(entry._metadata, "strategy_params", {}),
                "success_rate": stats.get("success_rate", 0),
                "results_count": stats.get("results_count", 0),
                "avg_process_time_ms": stats.get("avg_process_time_ms", 0),
                "timestamp": ts,
            }
            metrics.append(item)
            try:
                key = f"{entry.id}:{int(ts)}"
                db[key] = item
            except Exception:
                pass
        return metrics

    async def _request_llm(
        self,
        radar_summary: dict,
        memory_summary: dict,
        metrics: List[Dict[str, Any]],
        strategy_list: List[Dict[str, str]],
        cfg: Dict[str, Any],
    ) -> LLMDecision:
        prompt = self._build_prompt(radar_summary, memory_summary, metrics, strategy_list, cfg)

        try:
            from deva.llm import GPT
            model_type = cfg.get("model_type", "deepseek")
            gpt = GPT(model_type=model_type)
            response = await gpt.async_query(prompt)
        except Exception as e:
            raise RuntimeError(f"LLM 调节失败: {e}") from e

        data = self._safe_parse_json(response)
        actions = data.get("actions", [])
        summary = data.get("summary", "") or "LLM 决策"
        reason = data.get("reason", "") or ""

        return LLMDecision(
            id=f"llm_{int(time.time())}",
            ts=time.time(),
            summary=summary,
            actions=actions,
            reason=reason,
        )

    def _build_prompt(
        self,
        radar_summary: dict,
        memory_summary: dict,
        metrics: List[Dict[str, Any]],
        strategy_list: List[Dict[str, str]],
        cfg: Dict[str, Any],
    ) -> str:
        allow_actions = cfg.get("allowed_actions", [])
        allowlist = cfg.get("strategy_allowlist", [])
        denylist = cfg.get("strategy_denylist", [])
        return (
            "你是策略系统的元认知调节器。请基于雷达摘要和策略性能给出可执行调整建议。"
            "只返回 JSON：{\"summary\":\"...\",\"reason\":\"...\",\"actions\":[...]}\n\n"
            f"已注册策略列表:\n{json.dumps(strategy_list, ensure_ascii=False)}\n\n"
            f"雷达摘要:\n{json.dumps(radar_summary, ensure_ascii=False)}\n\n"
            f"洞察摘要:\n{json.dumps(memory_summary, ensure_ascii=False)}\n\n"
            f"策略指标:\n{json.dumps(metrics, ensure_ascii=False)}\n\n"
            f"允许动作: {json.dumps(allow_actions, ensure_ascii=False)}\n"
            f"策略白名单(如非空仅允许这些): {json.dumps(allowlist, ensure_ascii=False)}\n"
            f"策略黑名单(禁止): {json.dumps(denylist, ensure_ascii=False)}\n\n"
            "actions 每项格式:\n"
            "{\"strategy\":\"<策略名或ID>\",\"action\":\"update_params|update_strategy|reset|start|stop|restart\",\"params\":{...}}\n"
            "重要：strategy 必须从上面的已注册策略列表中选择，不能随意编造！"
        )

    def _safe_parse_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
        return {"summary": text, "actions": []}

    def _apply_actions(
        self,
        actions: List[Dict[str, Any]],
        metrics_index: Dict[str, Dict[str, Any]],
        cfg: Dict[str, Any],
        dry_run: bool = False,
    ) -> dict:
        mgr = get_strategy_manager()
        results = []
        allow_actions = {str(a).strip().lower() for a in cfg.get("allowed_actions", [])}
        max_actions = int(cfg.get("max_actions_per_run", 5))
        allowlist = {str(s).strip() for s in cfg.get("strategy_allowlist", []) if str(s).strip()}
        denylist = {str(s).strip() for s in cfg.get("strategy_denylist", []) if str(s).strip()}
        min_results = int(cfg.get("min_results_count_for_adjust", 0))
        max_success = cfg.get("max_success_rate_to_adjust", 1.0)
        allowed_param_keys = {str(s).strip() for s in cfg.get("allowed_param_keys", []) if str(s).strip()}
        blocked_param_keys = {str(s).strip() for s in cfg.get("blocked_param_keys", []) if str(s).strip()}

        for idx, action in enumerate(actions or []):
            if idx >= max_actions:
                results.append({"strategy": "*", "success": False, "error": "超过单次最大动作数限制"})
                break
            strategy_ref = str(action.get("strategy", "") or "").strip()
            op = str(action.get("action", "") or "").strip().lower()
            params = action.get("params") or {}

            entry = mgr.get(strategy_ref) or mgr.get_by_name(strategy_ref)
            if entry is None:
                results.append({"strategy": strategy_ref, "success": False, "error": "策略不存在"})
                continue

            if allowlist and entry.id not in allowlist and entry.name not in allowlist:
                results.append({"strategy": entry.name, "success": False, "error": "不在策略白名单"})
                continue
            if entry.id in denylist or entry.name in denylist:
                results.append({"strategy": entry.name, "success": False, "error": "在策略黑名单"})
                continue
            if allow_actions and op not in allow_actions:
                results.append({"strategy": entry.name, "success": False, "error": f"动作被风控禁止: {op}"})
                continue

            if not entry.supports_action(op):
                results.append({"strategy": entry.name, "success": False, "error": f"不支持动作: {op}"})
                continue

            metric = metrics_index.get(entry.id, {})
            if op in {"update_params", "update_strategy", "reset"}:
                results_count = int(metric.get("results_count", 0) or 0)
                success_rate = float(metric.get("success_rate", 0) or 0)
                if results_count < min_results:
                    results.append({"strategy": entry.name, "success": False, "error": "策略样本不足，禁止调节"})
                    continue
                if max_success is not None and success_rate > float(max_success):
                    results.append({"strategy": entry.name, "success": False, "error": "策略表现良好，禁止调节"})
                    continue

            if op == "update_params" and isinstance(params, dict):
                if allowed_param_keys:
                    params = {k: v for k, v in params.items() if k in allowed_param_keys}
                if blocked_param_keys:
                    params = {k: v for k, v in params.items() if k not in blocked_param_keys}
                if not params:
                    results.append({"strategy": entry.name, "success": False, "error": "参数变更被风控过滤"})
                    continue

            if dry_run:
                results.append({"strategy": entry.name, "success": True, "dry_run": True, "action": op})
                continue

            try:
                if op == "update_params":
                    result = entry.update_params(params)
                elif op == "update_strategy":
                    result = entry.update_strategy(params)
                elif op == "reset":
                    result = entry.reset()
                elif op == "start":
                    result = entry.start()
                elif op == "stop":
                    result = entry.stop()
                elif op == "restart":
                    entry.stop()
                    result = entry.start()
                else:
                    result = {"success": False, "error": "未知动作"}
                results.append({"strategy": entry.name, **result})
            except Exception as e:
                results.append({"strategy": entry.name, "success": False, "error": str(e)})

        return {"results": results}

    def _record_decision(self, decision: LLMDecision) -> None:
        try:
            key = f"{int(decision.ts * 1000)}_{decision.id}"
            self._db[key] = decision.to_dict()
        except Exception:
            return


_llm_controller: Optional[LLMController] = None
_llm_controller_lock = threading.Lock()


def get_llm_controller() -> LLMController:
    global _llm_controller
    if _llm_controller is None:
        with _llm_controller_lock:
            if _llm_controller is None:
                _llm_controller = LLMController()
    return _llm_controller


def _build_auto_adjust_task_code() -> str:
    return (
        "from deva.naja.config import get_llm_config\n"
        "from deva.naja.llm_controller import get_llm_controller\n"
        "from deva.naja.radar import get_radar_engine\n"
        "from deva.llm.worker_runtime import run_ai_in_worker\n\n"
        "def execute():\n"
        "    cfg = get_llm_config()\n"
        "    if not cfg.get('auto_adjust_enabled', True):\n"
        "        return {'success': False, 'error': 'auto_adjust_disabled'}\n"
        "    window_seconds = int(cfg.get('auto_adjust_window_seconds', 600))\n"
        "    min_events = int(cfg.get('auto_adjust_min_events', 3))\n"
        "    dry_run = bool(cfg.get('auto_adjust_dry_run', False))\n"
        "    summary = get_radar_engine().summarize(window_seconds=window_seconds)\n"
        "    if summary.get('event_count', 0) < min_events:\n"
        "        return {'success': False, 'error': 'not_enough_events', 'event_count': summary.get('event_count', 0)}\n"
        "    return run_ai_in_worker(\n"
        "        get_llm_controller().review_and_adjust(window_seconds=window_seconds, dry_run=dry_run)\n"
        "    )\n"
    )


def ensure_llm_auto_adjust_task() -> dict:
    from ..tasks import get_task_manager

    cfg = get_llm_config()
    if not cfg.get("auto_adjust_enabled", True):
        return {"success": False, "disabled": True}

    interval_seconds = float(cfg.get("auto_adjust_interval_seconds", 900))
    task_name = "llm_auto_adjust"
    task_mgr = get_task_manager()
    task = task_mgr.get_by_name(task_name)
    func_code = _build_auto_adjust_task_code()

    if task:
        update_result = task.update_config(
            name=task_name,
            description="LLM 自动调节策略任务",
            task_type="interval",
            execution_mode="timer",
            interval_seconds=interval_seconds,
            scheduler_trigger="interval",
            func_code=func_code,
        )
        return update_result

    create_result = task_mgr.create(
        name=task_name,
        func_code=func_code,
        task_type="interval",
        execution_mode="timer",
        interval_seconds=interval_seconds,
        scheduler_trigger="interval",
        description="LLM 自动调节策略任务",
        tags=["llm", "auto", "strategy"],
    )
    return create_result
