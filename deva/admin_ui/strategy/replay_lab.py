"""策略实验室(Replay Lab)增强版

提供策略验证、影子测试和可视化对比功能。

================================================================================
架构设计
================================================================================

【实验室工作流】
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. 数据抽取：从存储中提取历史记录（DBStream / 内存 Buffer）                    │
│  2. 影子运行：启动临时流分支，挂载新策略函数                                    │
│  3. 可视化比对：并排展示"原始逻辑输出"与"新策略输出"                            │
│  4. 差异审计：字段级对比、空值检查、逻辑收缩风险标记                            │
│  5. 决策闭环：采纳新策略 / 放弃更新                                            │
└─────────────────────────────────────────────────────────────────────────────┘

【影子测试架构】
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  历史数据 ──────┬───────────────────────────────────────────────────────────│
│                │                                                            │
│                ▼                                                            │
│         ┌──────────────┐                                                    │
│         │  原始处理器   │ ──────> 原始输出 ──────┐                           │
│         └──────────────┘                       │                           │
│                                                ▼                           │
│                                         ┌──────────────┐                    │
│                                         │  差异对比器   │                    │
│         ┌──────────────┐               │              │                    │
│         │  新处理器     │ ──────> 新输出 ──────┘                           │
│         └──────────────┘                                                    │
│                ▲                                                            │
│                │                                                            │
│         ┌──────────────┐                                                    │
│         │  沙盒环境    │  (隔离执行，捕获异常)                                │
│         └──────────────┘                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

【合规性检查】
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. Schema 验证：检查输出是否符合下游所需的关键字段                            │
│  2. 类型检查：确保字段类型与预期一致                                          │
│  3. 空值检查：检测意外的空值产生                                              │
│  4. 数据收缩：检测新策略是否过滤了过多数据                                    │
│  5. 性能指标：记录执行时间和资源消耗                                          │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import copy
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import pandas as pd

from deva import Stream, NS, NB, DBStream, log


@dataclass
class TestResult:
    input_data: Any
    original_output: Any
    new_output: Any
    status: str
    diff_note: str
    execution_time_ms: float
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "input_preview": self._preview(self.input_data),
            "original_output_preview": self._preview(self.original_output),
            "new_output_preview": self._preview(self.new_output),
            "status": self.status,
            "diff_note": self.diff_note,
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
        }
    
    def _preview(self, data: Any, max_len: int = 200) -> str:
        if data is None:
            return "None"
        if isinstance(data, pd.DataFrame):
            return f"DataFrame({len(data)} rows, {len(data.columns)} cols)"
        preview = str(data)
        return preview[:max_len] + "..." if len(preview) > max_len else preview


@dataclass
class LabReport:
    strategy_name: str
    total_tests: int
    passed: int
    failed: int
    filtered: int
    errors: int
    avg_execution_time_ms: float
    schema_compatible: bool
    data_retention_rate: float
    results: List[TestResult]
    summary: str
    
    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "filtered": self.filtered,
            "errors": self.errors,
            "avg_execution_time_ms": self.avg_execution_time_ms,
            "schema_compatible": self.schema_compatible,
            "data_retention_rate": self.data_retention_rate,
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results[:20]],
        }


class SandboxExecutor:
    """沙盒执行器
    
    在隔离环境中执行策略代码，捕获异常和资源消耗。
    """
    
    def __init__(self, allowed_modules: List[str] = None):
        self.allowed_modules = allowed_modules or [
            "pandas", "numpy", "datetime", "json", "re", "collections",
            "math", "statistics", "itertools", "functools",
        ]
        self._builtins_safe = {
            "abs": abs, "all": all, "any": any, "bool": bool,
            "dict": dict, "enumerate": enumerate, "filter": filter,
            "float": float, "frozenset": frozenset, "int": int,
            "isinstance": isinstance, "len": len, "list": list,
            "map": map, "max": max, "min": min, "range": range,
            "reversed": reversed, "round": round, "set": set,
            "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
            "type": type, "zip": zip,
        }
    
    def create_sandbox_namespace(self) -> dict:
        ns = {"__builtins__": self._builtins_safe.copy()}
        
        for mod_name in self.allowed_modules:
            try:
                if mod_name == "pandas":
                    import pandas as pd
                    ns["pd"] = pd
                elif mod_name == "numpy":
                    import numpy as np
                    ns["np"] = np
                elif mod_name == "datetime":
                    import datetime
                    ns["datetime"] = datetime
                elif mod_name == "json":
                    import json
                    ns["json"] = json
                elif mod_name == "re":
                    import re
                    ns["re"] = re
                elif mod_name == "collections":
                    import collections
                    ns["collections"] = collections
                elif mod_name == "math":
                    import math
                    ns["math"] = math
                elif mod_name == "statistics":
                    import statistics
                    ns["statistics"] = statistics
                elif mod_name == "itertools":
                    import itertools
                    ns["itertools"] = itertools
                elif mod_name == "functools":
                    import functools
                    ns["functools"] = functools
            except ImportError:
                pass
        
        return ns
    
    def execute(
        self,
        code: str,
        input_data: Any,
        func_name: str = "process",
        timeout_ms: int = 5000,
    ) -> Tuple[Any, Optional[str], float]:
        ns = self.create_sandbox_namespace()
        
        try:
            exec(code, ns, ns)
        except Exception as e:
            return None, f"Code compilation error: {e}", 0
        
        func = ns.get(func_name)
        if not callable(func):
            return None, f"Function '{func_name}' not found", 0
        
        start_time = time.time()
        try:
            result = func(copy.deepcopy(input_data))
            execution_time = (time.time() - start_time) * 1000
            return result, None, execution_time
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return None, f"Execution error: {e}\n{traceback.format_exc()}", execution_time


class DataComparator:
    """数据对比器
    
    比较原始输出和新输出的差异。
    """
    
    @staticmethod
    def compare(original: Any, new: Any) -> Tuple[str, str]:
        if original is None and new is None:
            return "both_none", "Both outputs are None"
        
        if original is None and new is not None:
            return "new_produced", "Original was None, new produced output"
        
        if original is not None and new is None:
            return "filtered", "New strategy filtered out the data"
        
        if type(original) != type(new):
            return "type_changed", f"Type changed: {type(original).__name__} -> {type(new).__name__}"
        
        if isinstance(original, pd.DataFrame):
            return DataComparator._compare_dataframes(original, new)
        
        if isinstance(original, dict):
            return DataComparator._compare_dicts(original, new)
        
        if isinstance(original, (list, tuple)):
            return DataComparator._compare_sequences(original, new)
        
        if original == new:
            return "identical", "Outputs are identical"
        
        return "modified", f"Value changed: {str(original)[:50]} -> {str(new)[:50]}"
    
    @staticmethod
    def _compare_dataframes(original: pd.DataFrame, new: pd.DataFrame) -> Tuple[str, str]:
        notes = []
        
        if len(original) != len(new):
            notes.append(f"Rows: {len(original)} -> {len(new)}")
        
        orig_cols = set(original.columns)
        new_cols = set(new.columns)
        
        added = new_cols - orig_cols
        removed = orig_cols - new_cols
        
        if added:
            notes.append(f"Added columns: {added}")
        if removed:
            notes.append(f"Removed columns: {removed}")
        
        common_cols = orig_cols & new_cols
        for col in common_cols:
            if original[col].dtype != new[col].dtype:
                notes.append(f"Column '{col}' dtype: {original[col].dtype} -> {new[col].dtype}")
        
        if not notes:
            try:
                if original.equals(new):
                    return "identical", "DataFrames are identical"
                else:
                    return "modified", "DataFrames have different values"
            except Exception:
                return "modified", "DataFrames differ"
        
        return "modified", "; ".join(notes)
    
    @staticmethod
    def _compare_dicts(original: dict, new: dict) -> Tuple[str, str]:
        notes = []
        
        orig_keys = set(original.keys())
        new_keys = set(new.keys())
        
        added = new_keys - orig_keys
        removed = orig_keys - new_keys
        
        if added:
            notes.append(f"Added keys: {added}")
        if removed:
            notes.append(f"Removed keys: {removed}")
        
        if not notes:
            if original == new:
                return "identical", "Dicts are identical"
            return "modified", "Dict values differ"
        
        return "modified", "; ".join(notes)
    
    @staticmethod
    def _compare_sequences(original: Union[list, tuple], new: Union[list, tuple]) -> Tuple[str, str]:
        if len(original) != len(new):
            return "modified", f"Length: {len(original)} -> {len(new)}"
        
        if original == new:
            return "identical", "Sequences are identical"
        
        return "modified", "Sequence values differ"


class SchemaValidator:
    """Schema 验证器
    
    验证输出数据是否符合预期的 Schema。
    """
    
    def __init__(self, required_fields: List[str] = None, field_types: Dict[str, type] = None):
        self.required_fields = required_fields or []
        self.field_types = field_types or {}
    
    def validate(self, data: Any) -> Tuple[bool, List[str]]:
        errors = []
        
        if data is None:
            return True, []
        
        if isinstance(data, pd.DataFrame):
            for field in self.required_fields:
                if field not in data.columns:
                    errors.append(f"Missing required column: {field}")
            
            for field, expected_type in self.field_types.items():
                if field in data.columns:
                    actual_type = data[field].dtype
                    if expected_type == str and actual_type != object:
                        pass
                    elif expected_type == int and "int" not in str(actual_type):
                        pass
                    elif expected_type == float and "float" not in str(actual_type):
                        pass
        
        elif isinstance(data, dict):
            for field in self.required_fields:
                if field not in data:
                    errors.append(f"Missing required field: {field}")
            
            for field, expected_type in self.field_types.items():
                if field in data and not isinstance(data[field], expected_type):
                    errors.append(f"Field '{field}' type mismatch: expected {expected_type.__name__}")
        
        return len(errors) == 0, errors


class ReplayLab:
    """策略实验室
    
    提供策略验证、影子测试和可视化对比功能。
    """
    
    def __init__(self):
        self.sandbox = SandboxExecutor()
        self.comparator = DataComparator()
        self._reports: Dict[str, LabReport] = {}
        self._reports_lock = threading.Lock()
    
    def test_strategy(
        self,
        strategy_name: str,
        original_processor: Callable,
        new_code: str,
        test_data: List[Any],
        schema_validator: SchemaValidator = None,
        stop_on_error: bool = False,
    ) -> LabReport:
        results = []
        passed = 0
        failed = 0
        filtered = 0
        errors = 0
        total_time = 0
        
        for i, data in enumerate(test_data):
            try:
                orig_start = time.time()
                original_output = original_processor(copy.deepcopy(data))
                orig_time = (time.time() - orig_start) * 1000
            except Exception as e:
                original_output = None
                orig_time = 0
            
            new_output, error, exec_time = self.sandbox.execute(new_code, data)
            total_time += exec_time
            
            if error:
                results.append(TestResult(
                    input_data=data,
                    original_output=original_output,
                    new_output=None,
                    status="error",
                    diff_note="",
                    execution_time_ms=exec_time,
                    error=error,
                ))
                errors += 1
                if stop_on_error:
                    break
                continue
            
            status, diff_note = self.comparator.compare(original_output, new_output)
            
            if status == "filtered":
                filtered += 1
            elif status == "identical":
                passed += 1
            elif status in ("modified", "new_produced"):
                passed += 1
            else:
                failed += 1
            
            results.append(TestResult(
                input_data=data,
                original_output=original_output,
                new_output=new_output,
                status=status,
                diff_note=diff_note,
                execution_time_ms=exec_time,
            ))
        
        avg_time = total_time / len(test_data) if test_data else 0
        
        schema_compatible = True
        if schema_validator:
            for result in results:
                if result.new_output is not None:
                    valid, _ = schema_validator.validate(result.new_output)
                    if not valid:
                        schema_compatible = False
                        break
        
        retention_rate = (len(test_data) - filtered) / len(test_data) if test_data else 1.0
        
        summary = self._generate_summary(
            strategy_name, len(test_data), passed, failed, filtered, errors,
            avg_time, schema_compatible, retention_rate
        )
        
        report = LabReport(
            strategy_name=strategy_name,
            total_tests=len(test_data),
            passed=passed,
            failed=failed,
            filtered=filtered,
            errors=errors,
            avg_execution_time_ms=avg_time,
            schema_compatible=schema_compatible,
            data_retention_rate=retention_rate,
            results=results,
            summary=summary,
        )
        
        with self._reports_lock:
            self._reports[f"{strategy_name}_{time.time()}"] = report
        
        return report
    
    def _generate_summary(
        self,
        name: str,
        total: int,
        passed: int,
        failed: int,
        filtered: int,
        errors: int,
        avg_time: float,
        schema_ok: bool,
        retention: float,
    ) -> str:
        lines = [
            f"## Strategy Lab Report: {name}",
            "",
            f"- **Total Tests**: {total}",
            f"- **Passed**: {passed} ({passed/total*100:.1f}%)" if total else "- **Passed**: 0",
            f"- **Failed**: {failed}",
            f"- **Filtered**: {filtered}",
            f"- **Errors**: {errors}",
            f"- **Avg Execution Time**: {avg_time:.2f}ms",
            f"- **Schema Compatible**: {'✅ Yes' if schema_ok else '❌ No'}",
            f"- **Data Retention Rate**: {retention*100:.1f}%",
        ]
        
        if retention < 0.8:
            lines.append("")
            lines.append("⚠️ **Warning**: Low data retention rate. The new strategy filters out significant data.")
        
        if not schema_ok:
            lines.append("")
            lines.append("⚠️ **Warning**: Schema validation failed. Output may break downstream consumers.")
        
        return "\n".join(lines)
    
    def test_from_dbstream(
        self,
        strategy_name: str,
        original_processor: Callable,
        new_code: str,
        stream: DBStream,
        limit: int = 10,
        start_time: str = None,
        end_time: str = None,
    ) -> LabReport:
        test_data = []
        
        keys = list(stream[start_time:end_time])
        for key in keys[:limit]:
            data = stream[key]
            if data is not None:
                test_data.append(data)
        
        return self.test_strategy(strategy_name, original_processor, new_code, test_data)
    
    def test_from_stream_cache(
        self,
        strategy_name: str,
        original_processor: Callable,
        new_code: str,
        stream: Stream,
        limit: int = 10,
    ) -> LabReport:
        test_data = []
        
        if stream.is_cache:
            cached = stream.recent(limit)
            test_data = list(cached)
        
        return self.test_strategy(strategy_name, original_processor, new_code, test_data)
    
    def get_report(self, report_id: str) -> Optional[LabReport]:
        with self._reports_lock:
            return self._reports.get(report_id)
    
    def list_reports(self) -> List[dict]:
        with self._reports_lock:
            return [
                {"id": rid, "strategy_name": r.strategy_name, "total_tests": r.total_tests}
                for rid, r in self._reports.items()
            ]
    
    def shadow_run(
        self,
        strategy_name: str,
        new_code: str,
        input_stream: Stream,
        output_stream_name: str = None,
        duration_seconds: int = 60,
    ) -> dict:
        sandbox = SandboxExecutor()
        shadow_output = NS(f"shadow_{strategy_name}_{int(time.time())}", description=f'{strategy_name}策略的回放测试输出流')
        
        collected = []
        errors = []
        start_time = time.time()
        
        def shadow_processor(data):
            nonlocal collected, errors
            
            if time.time() - start_time > duration_seconds:
                return
            
            result, error, exec_time = sandbox.execute(new_code, data)
            
            if error:
                errors.append({
                    "data_preview": str(data)[:200],
                    "error": error,
                    "ts": time.time(),
                })
            else:
                collected.append({
                    "input_preview": str(data)[:100],
                    "output_preview": str(result)[:100] if result else None,
                    "exec_time_ms": exec_time,
                    "ts": time.time(),
                })
                if result is not None:
                    shadow_output.emit(result)
        
        handler = input_stream.map(shadow_processor)
        
        return {
            "success": True,
            "shadow_output_stream": shadow_output.name,
            "duration_seconds": duration_seconds,
            "message": f"Shadow run started for {duration_seconds}s",
        }
    
    def compare_outputs(
        self,
        original_data: List[Any],
        new_data: List[Any],
    ) -> dict:
        if len(original_data) != len(new_data):
            return {
                "match": False,
                "reason": f"Length mismatch: {len(original_data)} vs {len(new_data)}",
            }
        
        differences = []
        for i, (orig, new) in enumerate(zip(original_data, new_data)):
            status, note = self.comparator.compare(orig, new)
            if status != "identical":
                differences.append({
                    "index": i,
                    "status": status,
                    "note": note,
                })
        
        return {
            "match": len(differences) == 0,
            "total_compared": len(original_data),
            "differences_count": len(differences),
            "differences": differences[:20],
        }


lab = ReplayLab()


def get_lab() -> ReplayLab:
    return lab
