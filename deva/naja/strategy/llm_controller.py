"""LLM 调节策略参数接口

提供 LLM 调节策略参数的标准机制:
- LLM 分析信号并生成参数调整建议
- 策略参数更新接口
- 参数调节历史记录
- 参数校验和回滚

使用方式:
    from deva.naja.strategy.llm_controller import (
        LLMTuner,
        get_tuner,
    )

    tuner = get_tuner(strategy_id)
    result = tuner.tune_params(signal, current_params)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB


@dataclass
class ParamChange:
    """参数变更"""

    param_name: str
    old_value: Any
    new_value: Any
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class TuneResult:
    """调参结果"""

    success: bool
    applied_changes: List[ParamChange] = field(default_factory=list)
    rejected_changes: List[ParamChange] = field(default_factory=list)
    llm_response: str = ""
    error: Optional[str] = None


class LLMTuner:
    """LLM 策略参数调节器

    负责:
    1. 收集信号和策略状态
    2. 调用 LLM 生成参数调整建议
    3. 验证和应用参数变更
    4. 记录参数调整历史
    """

    def __init__(
        self,
        strategy_id: str,
        strategy_name: str = "",
        strategy_type: str = "legacy",
    ):
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.strategy_type = strategy_type
        self._param_history: List[Dict] = []
        self._change_validators: Dict[str, Callable] = {}

    def register_validator(
        self,
        param_name: str,
        validator: Callable[[Any], bool],
    ) -> None:
        """注册参数验证器

        Args:
            param_name: 参数名称
            validator: 验证函数，返回 True 表示有效
        """
        self._change_validators[param_name] = validator

    def set_validators(self, validators: Dict[str, Callable]) -> None:
        """批量设置验证器"""
        self._change_validators.update(validators)

    def _build_prompt(
        self,
        signal: Dict[str, Any],
        current_params: Dict[str, Any],
    ) -> str:
        """构建 LLM 提示词"""
        signal_json = json.dumps(signal, ensure_ascii=False, indent=2)
        params_json = json.dumps(current_params, ensure_ascii=False, indent=2)

        prompt = f"""## 当前信号
```
{signal_json}
```

## 当前策略参数
```
{params_json}
```

## 策略类型: {self.strategy_type}
策略名称: {self.strategy_name}

请分析以上信号和参数，给出参数调整建议。

要求:
1. 只调整必要的参数
2. 参数值必须在合理范围内
3. 给出调整原因
4. 以 JSON 格式输出，格式如下:
```json
{{
  "changes": [
    {{"param": "参数名", "value": 新值, "reason": "调整原因"}}
  ],
  "summary": "总结说明"
}}
```
"""
        return prompt

    def _parse_llm_response(self, response: str) -> Dict:
        """解析 LLM 响应"""
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
            return {"changes": [], "summary": "解析失败"}

    def _validate_change(self, change: Dict) -> bool:
        """验证参数变更"""
        param_name = change.get("param")
        if not param_name:
            return False

        validator = self._change_validators.get(param_name)
        if validator:
            return validator(change.get("value"))

        return True

    def tune_params(
        self,
        signal: Dict[str, Any],
        current_params: Dict[str, Any],
        llm_client: Optional[Callable] = None,
    ) -> TuneResult:
        """调节参数

        Args:
            signal: 当前信号
            current_params: 当前参数
            llm_client: LLM 调用函数

        Returns:
            TuneResult: 调参结果
        """
        result = TuneResult(success=False)

        prompt = self._build_prompt(signal, current_params)

        if llm_client is None:
            result.error = "未提供 LLM 客户端"
            return result

        try:
            llm_response = llm_client(prompt)
            result.llm_response = llm_response
        except Exception as e:
            result.error = f"LLM 调用失败: {e}"
            return result

        parsed = self._parse_llm_response(llm_response)

        changes_data = parsed.get("changes", [])

        for change_data in changes_data:
            param_name = change_data.get("param")
            new_value = change_data.get("value")
            reason = change_data.get("reason", "")

            old_value = current_params.get(param_name)

            change = ParamChange(
                param_name=param_name,
                old_value=old_value,
                new_value=new_value,
                reason=reason,
            )

            if self._validate_change(change):
                result.applied_changes.append(change)
            else:
                result.rejected_changes.append(change)

        if result.applied_changes:
            result.success = True
            self._save_history(result)

        return result

    def apply_changes(
        self,
        changes: List[Dict[str, Any]],
        current_params: Dict[str, Any],
    ) -> TuneResult:
        """直接应用参数变更（不经过 LLM）

        Args:
            changes: 变更列表 [{"param": "name", "value": value, "reason": "..."}]
            current_params: 当前参数

        Returns:
            TuneResult: 应用结果
        """
        result = TuneResult(success=False)

        for change_data in changes:
            param_name = change_data.get("param")
            new_value = change_data.get("value")
            reason = change_data.get("reason", "手动调整")

            old_value = current_params.get(param_name)

            change = ParamChange(
                param_name=param_name,
                old_value=old_value,
                new_value=new_value,
                reason=reason,
            )

            if self._validate_change(change):
                result.applied_changes.append(change)
            else:
                result.rejected_changes.append(change)

        if result.applied_changes:
            result.success = True

        return result

    def _save_history(self, result: TuneResult) -> None:
        """保存调参历史"""
        self._param_history.append(
            {
                "timestamp": time.time(),
                "applied": [
                    {
                        "param": c.param_name,
                        "old": c.old_value,
                        "new": c.new_value,
                        "reason": c.reason,
                    }
                    for c in result.applied_changes
                ],
                "rejected": [
                    {
                        "param": c.param_name,
                        "value": c.new_value,
                        "reason": c.reason,
                    }
                    for c in result.rejected_changes
                ],
                "llm_response": result.llm_response,
            }
        )

        db = NB("naja_llm_tuning")
        key = f"history_{self.strategy_id}"
        history = db.get(key) or []
        history.append(self._param_history[-1])
        if len(history) > 100:
            history = history[-100:]
        db[key] = history

    def get_history(self, limit: int = 10) -> List[Dict]:
        """获取调参历史"""
        return self._param_history[-limit:]

    def rollback(self, steps: int = 1) -> Optional[Dict]:
        """回滚参数变更

        Args:
            steps: 回滚步数

        Returns:
            Dict: 回滚后的参数，None 表示无法回滚
        """
        if len(self._param_history) < steps:
            return None

        last_change = self._param_history[-steps]
        rollback_params = {}

        for change in last_change.get("applied", []):
            rollback_params[change["param"]] = change["old"]

        return rollback_params


_TUNER_REGISTRY: Dict[str, LLMTuner] = {}


def get_tuner(strategy_id: str) -> LLMTuner:
    """获取策略的 LLM 调节器"""
    if strategy_id not in _TUNER_REGISTRY:
        _TUNER_REGISTRY[strategy_id] = LLMTuner(strategy_id)
    return _TUNER_REGISTRY[strategy_id]


def create_tuner(
    strategy_id: str,
    strategy_name: str = "",
    strategy_type: str = "legacy",
) -> LLMTuner:
    """创建策略的 LLM 调节器"""
    tuner = LLMTuner(strategy_id, strategy_name, strategy_type)
    _TUNER_REGISTRY[strategy_id] = tuner
    return tuner
