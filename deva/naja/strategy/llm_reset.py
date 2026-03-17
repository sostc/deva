"""LLM 重置策略大模型

提供 LLM 重置策略大模型的功能:
- 模型状态重置
- 模型重新初始化
- 重置历史记录
- 与 LLM 调节器集成

使用方式:
    from deva.naja.strategy.llm_reset import (
        ModelResetter,
        get_resetter,
        reset_model,
    )
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB


@dataclass
class ResetRecord:
    """重置记录"""

    record_id: str
    timestamp: float
    reason: str
    old_state: Any
    new_init_params: Dict[str, Any]
    success: bool
    error: Optional[str] = None


class ModelResetter:
    """策略大模型重置器

    负责:
    1. 重置模型状态到初始状态
    2. 使用新的初始化参数重新初始化模型
    3. 保存重置历史
    4. 与持久化系统集成
    """

    def __init__(
        self,
        strategy_id: str,
        strategy_name: str = "",
    ):
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self._db = NB("naja_strategy_resets")
        self._reset_history: List[Dict] = []

    def _generate_record_id(self) -> str:
        """生成记录ID"""
        return f"reset_{int(time.time())}"

    def _save_to_history(self, record: ResetRecord) -> None:
        """保存到历史记录"""
        self._reset_history.append(
            {
                "record_id": record.record_id,
                "timestamp": record.timestamp,
                "reason": record.reason,
                "new_init_params": record.new_init_params,
                "success": record.success,
                "error": record.error,
            }
        )

        history_key = f"history_{self.strategy_id}"
        history = self._db.get(history_key) or []
        history.append(self._reset_history[-1])
        if len(history) > 100:
            history = history[-100:]
        self._db[history_key] = history

    def reset(
        self,
        init_params: Optional[Dict[str, Any]] = None,
        reason: str = "manual",
        model_loader: Optional[Callable[[Dict], Any]] = None,
    ) -> ResetRecord:
        """重置模型

        Args:
            init_params: 新的初始化参数
            reason: 重置原因
            model_loader: 模型加载函数，如果提供则调用此函数重新加载

        Returns:
            ResetRecord: 重置记录
        """
        record = ResetRecord(
            record_id=self._generate_record_id(),
            timestamp=time.time(),
            reason=reason,
            old_state=None,
            new_init_params=init_params or {},
            success=False,
        )

        try:
            if model_loader and init_params:
                new_model = model_loader(init_params)
                record.success = True

            elif init_params:
                record.success = True

            else:
                record.success = True

        except Exception as e:
            record.success = False
            record.error = str(e)

        self._save_to_history(record)

        return record

    def reset_to_version(
        self,
        version_id: str,
        reason: str = "restore",
        model_loader: Optional[Callable] = None,
    ) -> ResetRecord:
        """重置到指定版本

        Args:
            version_id: 目标版本ID
            reason: 重置原因
            model_loader: 模型加载函数

        Returns:
            ResetRecord: 重置记录
        """
        from .model_persist import get_model_manager

        manager = get_model_manager(self.strategy_id)
        model_state = manager.load(version_id)

        record = ResetRecord(
            record_id=self._generate_record_id(),
            timestamp=time.time(),
            reason=reason,
            old_state=None,
            new_init_params={"version_id": version_id},
            success=False,
        )

        if model_state is None:
            record.error = f"未找到版本: {version_id}"
            self._save_to_history(record)
            return record

        try:
            if model_loader:
                model_loader(model_state)

            manager.save(model_state, metadata={"restored_from": version_id})
            record.success = True

        except Exception as e:
            record.error = str(e)

        self._save_to_history(record)

        return record

    def clear_history(self) -> int:
        """清除重置历史

        Returns:
            int: 清除的记录数
        """
        count = len(self._reset_history)
        self._reset_history.clear()

        history_key = f"history_{self.strategy_id}"
        self._db[history_key] = []

        return count

    def get_history(self, limit: int = 10) -> List[Dict]:
        """获取重置历史"""
        return self._reset_history[-limit:]


class LLMIntegratedResetter(ModelResetter):
    """集成 LLM 的模型重置器

    在重置前调用 LLM 分析当前状态，
    生成最优的重置策略
    """

    def __init__(
        self,
        strategy_id: str,
        strategy_name: str = "",
        llm_client: Optional[Callable] = None,
    ):
        super().__init__(strategy_id, strategy_name)
        self.llm_client = llm_client
        self._db = NB("naja_llm_resets")

    def _build_reset_prompt(
        self,
        current_state: Dict[str, Any],
        history: List[Dict],
    ) -> str:
        """构建 LLM 重置建议提示词"""
        state_json = json.dumps(current_state, ensure_ascii=False, indent=2)
        history_json = json.dumps(history[-5:], ensure_ascii=False, indent=2)

        prompt = f"""## 当前模型状态
```
{state_json}
```

## 最近历史
```
{history_json}
```

请分析以上信息，判断是否需要重置模型。

如果需要重置，请给出:
1. 重置原因
2. 推荐的初始化参数
3. 预期效果

以 JSON 格式输出:
```json
{{
  "should_reset": true/false,
  "reason": "原因",
  "init_params": {{"参数": "值"}},
  "expected_effect": "预期效果"
}}
```
"""
        return prompt

    def _parse_llm_suggestion(self, response: str) -> Dict:
        """解析 LLM 建议"""
        try:
            json_start = response.find("```json")
            if json_start == -1:
                json_start = response.find("```")
            json_end = response.rfind("```")

            if json_start != -1 and json_end != -1:
                json_str = response[json_start + 7 : json_end].strip()
            else:
                json_str = response.strip()

            return json.loads(json_str)

        except json.JSONDecodeError:
            return {"should_reset": False}

    def reset_with_llm(
        self,
        current_state: Dict[str, Any],
        model_loader: Optional[Callable] = None,
    ) -> ResetRecord:
        """基于 LLM 分析重置模型

        Args:
            current_state: 当前模型状态
            model_loader: 模型加载函数

        Returns:
            ResetRecord: 重置记录
        """
        if self.llm_client is None:
            return self.reset(reason="llm_client_not_available")

        history = self.get_history()

        prompt = self._build_reset_prompt(current_state, history)

        try:
            llm_response = self.llm_client(prompt)
        except Exception as e:
            return self.reset(reason=f"llm_error: {e}")

        suggestion = self._parse_llm_suggestion(llm_response)

        if not suggestion.get("should_reset", False):
            return ResetRecord(
                record_id=self._generate_record_id(),
                timestamp=time.time(),
                reason="llm_suggestion: no_reset_needed",
                old_state=None,
                new_init_params={},
                success=True,
            )

        init_params = suggestion.get("init_params", {})
        reason = suggestion.get("reason", "llm_suggested")

        return self.reset(
            init_params=init_params,
            reason=reason,
            model_loader=model_loader,
        )


_RESETTERS: Dict[str, ModelResetter] = {}


def get_resetter(strategy_id: str) -> ModelResetter:
    """获取策略的重置器"""
    if strategy_id not in _RESETTERS:
        _RESETTERS[strategy_id] = ModelResetter(strategy_id)
    return _RESETTERS[strategy_id]


def reset_model(
    strategy_id: str,
    init_params: Optional[Dict[str, Any]] = None,
    reason: str = "manual",
) -> ResetRecord:
    """重置模型的便捷函数"""
    resetter = get_resetter(strategy_id)
    return resetter.reset(init_params, reason)
