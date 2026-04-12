"""StrategyEntry - 策略条目，基于 RecoverableUnit 抽象"""

from __future__ import annotations

import asyncio
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB
from deva.core.namespace import NS

from ..infra.runtime.recoverable import RecoverableUnit, UnitStatus
from ..infra.runtime.thread_pool import get_thread_pool
from .output_controller import get_output_controller
from deva.naja.register import SR
from .models import (
    STRATEGY_TABLE,
    STRATEGY_RESULTS_TABLE,
    StrategyMetadata,
    StrategyState,
)

class StrategyEntry(RecoverableUnit):
    """策略条目"""
    
    def __init__(
        self,
        metadata: StrategyMetadata = None,
        state: StrategyState = None,
    ):
        super().__init__(
            metadata=metadata or StrategyMetadata(),
            state=state or StrategyState(),
        )
        
        self._input_stream: Optional[Any] = None
        self._input_streams: Dict[str, Any] = {}  # 多数据源支持：数据源ID -> 流
        self._datasource_names: Dict[str, str] = {}  # 数据源ID -> 名称
        self._output_stream: Optional[Any] = None
        self._processing_lock = threading.Lock()
        self._window_lock = threading.Lock()
        self._window_buffer: List[Any] = []
        self._last_window_trigger: float = 0  # 上次窗口触发时间
        self._runtime = None
        self._runtime_type = ""
        self._runtime_config_hash = ""

        self._ensure_runtime_stub_code()

    def _get_func_name(self) -> str:
        return "process"

    def _ensure_runtime_stub_code(self):
        if self._get_strategy_type() == "legacy":
            return
        if not self._func_code:
            self._func_code = "def process(data, context=None):\n    return None\n"

    def _get_strategy_type(self) -> str:
        return str(getattr(self._metadata, "strategy_type", "legacy") or "legacy").strip().lower()

    def _get_strategy_config(self) -> Dict[str, Any]:
        config = dict(getattr(self._metadata, "strategy_config", {}) or {})
        params = dict(getattr(self._metadata, "strategy_params", {}) or {})
        
        strategy_type = self._get_strategy_type()
        
        if strategy_type not in ("", "legacy"):
            func_code = getattr(self, "_func_code", None) or ""
            if not func_code:
                func_code = self._metadata.func_code if hasattr(self._metadata, "func_code") else ""
            
            if func_code and "logic" not in config:
                config["logic"] = {
                    "type": "python",
                    "code": func_code
                }
            elif func_code and "logic" in config and not config.get("logic", {}).get("code"):
                config["logic"]["code"] = func_code
        
        if params:
            merged = dict(config)
            merged.update(params)
            existing_params = dict(config.get("params", {}) or {})
            existing_params.update(params)
            merged["params"] = existing_params
            return merged
        return config

    def is_processing_data(self, timeout: float = 300) -> bool:
        """检测策略是否正在活跃处理数据
        
        Args:
            timeout: 超时时间(秒)，超过该时间没处理数据则视为不活跃
            
        Returns:
            bool: 策略是否在超时时间内处理过数据
        """
        if not self.is_running:
            return False
        if self._state.processed_count == 0:
            return False
        elapsed = time.time() - self._state.last_process_ts
        return elapsed < timeout

    def _get_runtime(self):
        strategy_type = self._get_strategy_type()
        if strategy_type in ("", "legacy"):
            return None

        config = self._get_strategy_config()
        try:
            import json
            config_hash = f"{strategy_type}:{hash(json.dumps(config, sort_keys=True, default=str))}"
        except Exception:
            config_hash = f"{strategy_type}:{hash(str(config))}"

        if self._runtime is not None and self._runtime_type == strategy_type and self._runtime_config_hash == config_hash:
            return self._runtime

        try:
            from .runtime import StrategyRegistry
            runtime = StrategyRegistry.create(strategy_type, config=config, entry=self)
        except Exception as e:
            self._log("ERROR", "Build runtime failed", error=str(e), strategy_type=strategy_type)
            return None

        self._runtime = runtime
        self._runtime_type = strategy_type
        self._runtime_config_hash = config_hash
        return runtime
    
    def _do_compile(self, code: str) -> Callable:
        if self._get_strategy_type() != "legacy":
            return lambda *_args, **_kwargs: None

        env = self._build_execution_env()
        exec(code, env)
        
        func = env.get(self._get_func_name())
        if not func or not callable(func):
            raise ValueError(f"函数 '{self._get_func_name()}' 未在代码中定义")
        
        return func
    
    def _do_start(self, func: Callable) -> dict:
        try:
            # 获取多数据源ID列表
            datasource_ids = getattr(self._metadata, "bound_datasource_ids", [])
            if not datasource_ids:
                datasource_id = getattr(self._metadata, "bound_datasource_id", "")
                if datasource_id:
                    datasource_ids = [datasource_id]

            if not datasource_ids:
                return {"success": True, "message": "No datasource bound"}

            from ..datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()

            bound_count = 0
            failed_datasources = []
            valid_datasource_ids = []

            for ds_id in datasource_ids:
                ds = ds_mgr.get(ds_id)
                if ds is None:
                    failed_datasources.append(ds_id)
                    continue

                valid_datasource_ids.append(ds_id)
                try:
                    self._bind_datasource(ds)
                    bound_count += 1
                except Exception as e:
                    self._log("ERROR", f"Bind datasource failed", datasource_id=ds_id, error=str(e))
                    failed_datasources.append(ds_id)

            if failed_datasources:
                self._log("INFO", f"Removing deleted datasources from bound list", removed=failed_datasources)
                if hasattr(self, '_metadata') and hasattr(self._metadata, 'bound_datasource_ids'):
                    self._metadata.bound_datasource_ids = valid_datasource_ids
                    self.save()

            if bound_count == 0:
                return {"success": True, "message": f"No datasources could be bound. Failed: {failed_datasources}"}

            runtime = self._get_runtime()
            if runtime is not None and hasattr(runtime, "on_start"):
                try:
                    runtime.on_start()
                except Exception as e:
                    self._log("ERROR", "Runtime on_start failed", error=str(e))

            return {
                "success": True,
                "message": f"Bound {bound_count} datasources, failed: {len(failed_datasources)}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _do_stop(self) -> dict:
        try:
            self._input_stream = None
            self._output_stream = None
            runtime = self._get_runtime()
            if runtime is not None:
                try:
                    runtime.close()
                except Exception:
                    pass
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _bind_datasource(self, datasource: Any):
        """绑定数据源"""
        try:
            ds_id = datasource.id
            ds_name = datasource.name
            stream = datasource.get_stream()
            
            if stream is None:
                self._log("ERROR", "Bind datasource failed: stream is None", datasource_id=ds_id)
                return
            
            # 保存流和名称（多数据源支持）
            self._input_streams[ds_id] = stream
            self._datasource_names[ds_id] = ds_name
            
            # 兼容单数据源模式
            if self._input_stream is None:
                self._input_stream = stream
            
            output_stream_name = f"strategy_output_{self.id}"
            self._output_stream = NS(
                output_stream_name,
                cache_max_len=10,
                cache_max_age_seconds=3600,
                description=f"Strategy {self.name} output",
            )
            
            # 创建数据源特定的数据处理函数
            def create_on_data(datasource_id: str, datasource_name: str):
                def on_data(data: Any):
                    # 添加数据源信息到数据
                    enriched_data = {
                        "_datasource_id": datasource_id,
                        "_datasource_name": datasource_name,
                        "_receive_time": time.time(),
                        "data": data,
                    }
                    self._process_data(enriched_data)
                return on_data
            
            on_data = create_on_data(ds_id, ds_name)
            
            if hasattr(stream, "sink"):
                stream.sink(on_data)
            elif hasattr(stream, "map"):
                mapped_stream = stream.map(on_data)
                mapped_stream.sink(lambda x: None)
            elif hasattr(stream, "subscribe"):
                stream.subscribe(on_data)
            else:
                self._log("ERROR", "No valid subscription method found on stream", datasource_id=ds_id)
            
            self._log("INFO", f"Datasource bound successfully", datasource_id=ds_id, name=ds_name)
                
        except Exception as e:
            self._log("ERROR", "Bind datasource failed", error=str(e))
    
    def _process_data(self, data: Any):
        """处理数据"""
        if not self.is_running:
            return

        runtime = self._get_runtime()
        if self._compiled_func is None and runtime is None:
            return

        # 检查解释器是否正在关闭
        import sys
        if sys.is_finalizing():
            return

        try:
            pool = get_thread_pool()
            pool.submit(self._process_data_async, data)
        except RuntimeError:
            # 线程池已关闭，忽略
            pass
    
    def _process_data_async(self, data: Any):
        """异步处理数据"""
        with self._processing_lock:
            start_time = time.time()
            success = False
            result = None
            error = ""
            skipped = False  # 是否跳过（如 timed 窗口未触发）
            duplicate = False  # 是否与上次结果相同
            
            try:
                data = self._enrich_data(data)
                
                compute_mode = getattr(self._metadata, "compute_mode", "record")
                
                if compute_mode == "window":
                    result = self._process_window(data)
                    # timed 窗口未触发时返回 None，标记为跳过
                    if result is None and getattr(self._metadata, "window_type", "sliding") == "timed":
                        skipped = True
                else:
                    result = self._process_record(data)
                
                if not skipped:
                    success = True
                    self._state.processed_count += 1
                    self._state.last_process_ts = time.time()
                    
                    if result is not None:
                        # 检查是否与上次结果相同
                        if self._is_duplicate_result(result):
                            duplicate = True
                        else:
                            self._emit_result(result)
                            self._state.output_count += 1
                
            except Exception as e:
                error = str(e)
                error_traceback = traceback.format_exc()
                self._state.record_error(error)
                self._log("ERROR", "Process data failed", error=str(e), traceback=error_traceback)
            
            # 计算执行时间
            process_time_ms = (time.time() - start_time) * 1000
            
            # 调试日志：只打印策略返回结果
            try:
                from ..config import get_strategy_debug
                if get_strategy_debug():
                    import json
                    if result is not None:
                        if isinstance(result, dict):
                            debug_result_summary = json.dumps(result, ensure_ascii=False, default=str)
                        else:
                            debug_result_summary = str(result)
                        print(f"[STRATEGY_RESULT] {self.name}: {debug_result_summary}")
            except Exception:
                pass
            
            # 记录性能指标
            try:
                from deva.naja.infra.observability.performance_monitor import record_component_execution, ComponentType
                record_component_execution(
                    component_id=self.id,
                    component_name=self.name,
                    component_type=ComponentType.STRATEGY,
                    execution_time_ms=process_time_ms,
                    success=success and not error,
                    error=error,
                )
            except Exception:
                pass  # 性能监控不应影响主流程
            
            # 保存结果（包括未命中的情况）
            if not skipped and not duplicate:
                # 只有命中策略（result 不为 None）才保存到结果存储
                if result is not None:
                    self._save_result_to_store(data, result, process_time_ms, success, error)
    
    def _is_duplicate_result(self, result: Any) -> bool:
        """检查结果是否与上次相同"""
        import json
        
        try:
            # 获取上次结果
            from .result_store import get_result_store
            store = get_result_store()
            recent = store.get_recent(self.id, limit=1)
            
            if not recent:
                return False
            
            last_result = recent[0].output_full
            
            # 比较结果
            if last_result is None and result is None:
                return True
            
            if last_result is None or result is None:
                return False
            
            # 排除时间戳等动态字段后比较
            exclude_keys = {'timestamp', 'ts', 'datetime', 'time', 'created_at', 'updated_at'}
            
            def filter_result(r):
                if isinstance(r, dict):
                    return {k: v for k, v in r.items() if k not in exclude_keys}
                return r
            
            last_filtered = filter_result(last_result)
            current_filtered = filter_result(result)
            
            # 序列化比较
            last_json = json.dumps(last_filtered, sort_keys=True, default=str)
            current_json = json.dumps(current_filtered, sort_keys=True, default=str)
            
            return last_json == current_json
            
        except Exception:
            return False
    
    def _process_record(self, data: Any) -> Any:
        runtime = self._get_runtime()

        # Create context object
        context = {
            'strategy_id': self.id,
            'strategy_name': self.name,
            'metadata': self._metadata.to_dict(),
            'state': self._state.to_dict()
        }
        
        # 提取实际数据（如果是 enriched_data 结构）
        actual_data = data.get('data', data) if isinstance(data, dict) else data

        if runtime is not None:
            runtime.on_data(actual_data)
            return runtime.get_signal()
        
        # Try calling with context first, then fallback to data only
        try:
            result = self._compiled_func(actual_data, context)
        except TypeError:
            # Fallback to data only for backward compatibility
            result = self._compiled_func(actual_data)
            
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, result)
                    result = future.result(timeout=30)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(result)
                finally:
                    loop.close()
        return result

    def _process_window(self, data: Any) -> Any:
        window_type = getattr(self._metadata, "window_type", "sliding") or "sliding"
        window_size = max(1, int(getattr(self._metadata, "window_size", 5) or 5))
        return_partial = bool(getattr(self._metadata, "window_return_partial", False))

        actual_data = data.get('data', data) if isinstance(data, dict) else data

        runtime = self._get_runtime()

        if window_type == "sliding":
            with self._window_lock:
                self._window_buffer.append(actual_data)
                if len(self._window_buffer) > window_size:
                    self._window_buffer = self._window_buffer[-window_size:]

                if not return_partial and len(self._window_buffer) < window_size:
                    return None

                context = {
                    'strategy_id': self.id,
                    'strategy_name': self.name,
                    'metadata': self._metadata.to_dict(),
                    'state': self._state.to_dict()
                }

                buffer_copy = list(self._window_buffer)

            if runtime is not None:
                runtime.on_data(buffer_copy)
                result = runtime.get_signal()
            else:
                try:
                    result = self._compiled_func(buffer_copy, context)
                except TypeError:
                    result = self._compiled_func(buffer_copy)

            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(asyncio.run, result)
                        result = future.result(timeout=30)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(result)
                    finally:
                        loop.close()
            return result

        elif window_type == "timed":
            window_interval_str = getattr(self._metadata, "window_interval", "10s") or "10s"
            interval_seconds = self._parse_interval(window_interval_str)

            now = time.time()

            with self._window_lock:
                if self._last_window_trigger == 0:
                    self._last_window_trigger = now
                    return None

                should_trigger = (now - self._last_window_trigger) >= interval_seconds

                if not should_trigger:
                    return None

                self._last_window_trigger = now

                if len(self._window_buffer) < 1:
                    return None

                context = {
                    'strategy_id': self.id,
                    'strategy_name': self.name,
                    'metadata': self._metadata.to_dict(),
                    'state': self._state.to_dict()
                }

                buffer_copy = list(self._window_buffer)
                self._window_buffer = []

            if runtime is not None:
                runtime.on_data(buffer_copy)
                result = runtime.get_signal()
            else:
                try:
                    result = self._compiled_func(buffer_copy, context)
                except TypeError:
                    result = self._compiled_func(buffer_copy)

            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(asyncio.run, result)
                        result = future.result(timeout=30)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(result)
                    finally:
                        loop.close()
            return result
        else:
            with self._window_lock:
                if len(self._window_buffer) > window_size:
                    self._window_buffer = self._window_buffer[-window_size:]

                if len(self._window_buffer) < window_size:
                    return None

                context = {
                    'strategy_id': self.id,
                    'strategy_name': self.name,
                    'metadata': self._metadata.to_dict(),
                    'state': self._state.to_dict()
                }

                buffer_copy = list(self._window_buffer)

            if runtime is not None:
                runtime.on_data(buffer_copy)
                result = runtime.get_signal()
            else:
                try:
                    result = self._compiled_func(buffer_copy, context)
                except TypeError:
                    result = self._compiled_func(buffer_copy)

            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(asyncio.run, result)
                        result = future.result(timeout=30)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(result)
                    finally:
                        loop.close()
            return result

    def _parse_interval(self, interval_str: str) -> float:
        """解析时间间隔字符串，返回秒数"""
        if not interval_str:
            return 10.0
        
        interval_str = str(interval_str).strip().lower()
        
        # 支持的格式: 10s, 5min, 1h, 30m, 2hour 等
        import re
        match = re.match(r'^(\d+(?:\.\d+)?)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hour|hours)?$', interval_str)
        
        if not match:
            try:
                return float(interval_str)
            except ValueError:
                return 10.0
        
        value = float(match.group(1))
        unit = match.group(2) or 's'
        
        if unit in ('s', 'sec', 'second', 'seconds'):
            return value
        elif unit in ('m', 'min', 'minute', 'minutes'):
            return value * 60
        elif unit in ('h', 'hour', 'hours'):
            return value * 3600
        
        return value
    
    def _enrich_data(self, data: Any) -> Any:
        """数据补齐"""
        import pandas as pd
        
        profile_ids = getattr(self._metadata, "dictionary_profile_ids", [])
        if not profile_ids:
            return data
        
        # 提取实际数据（如果是 enriched_data 结构）
        actual_data = data.get('data', data) if isinstance(data, dict) else data
        
        if not isinstance(actual_data, pd.DataFrame):
            return data
        
        result = actual_data
        for profile_id in profile_ids:
            result = self._enrich_dataframe(result, profile_id)
        
        # 如果是 enriched_data 结构，更新 data 中的实际数据
        if isinstance(data, dict) and 'data' in data:
            data['data'] = result
            return data
        else:
            return result
    
    def _enrich_dataframe(self, df: Any, profile_id: str) -> Any:
        """使用字典数据补齐 DataFrame"""
        try:
            dict_mgr = SR('dictionary_manager')
            entry = dict_mgr.get(profile_id)
            
            if entry is None:
                return df
            
            dim_data = entry.get_payload()
            if dim_data is None:
                return df
            
            import pandas as pd
            if not isinstance(dim_data, pd.DataFrame):
                dim_df = pd.DataFrame(dim_data) if isinstance(dim_data, (list, dict)) else None
            else:
                dim_df = dim_data
            
            if dim_df is None or dim_df.empty:
                return df
            
            join_key = self._infer_join_key(df, dim_df)
            if not join_key:
                return df
            
            left_df = df.copy()
            right_df = dim_df.copy()
            
            if join_key == "code":
                left_df[join_key] = left_df[join_key].astype(str)
                right_df[join_key] = right_df[join_key].astype(str)
            
            enrich_cols = [c for c in right_df.columns if c != join_key]
            if not enrich_cols:
                return left_df
            
            merged = left_df.merge(
                right_df[[join_key] + enrich_cols],
                on=join_key,
                how="left",
                suffixes=("", "__dict"),
            )
            
            for col in enrich_cols:
                dict_col = f"{col}__dict"
                if dict_col not in merged.columns:
                    continue
                if col in left_df.columns:
                    merged[col] = merged[col].where(merged[col].notna(), merged[dict_col])
                    merged.drop(columns=[dict_col], inplace=True)
                else:
                    merged.rename(columns={dict_col: col}, inplace=True)
            
            return merged
            
        except Exception:
            return df
    
    def _infer_join_key(self, left_df: Any, right_df: Any) -> Optional[str]:
        common_cols = set(left_df.columns).intersection(set(right_df.columns))
        for key in ("code", "ts_code", "symbol", "name"):
            if key in common_cols:
                return key
        return None
    
    def _emit_result(self, result: Any):
        if self._output_stream is None:
            return
        
        try:
            if hasattr(self._output_stream, "emit"):
                self._output_stream.emit(result)
            
            self._save_result(result)
            
        except Exception as e:
            self._log("ERROR", "Emit result failed", error=str(e))
    
    def _save_result(self, result: Any):
        try:
            timestamp = time.time()

            try:
                from ..infra.log.log_stream import log_strategy
                result_preview = str(result)[:500] if result else ""
                log_strategy(
                    "INFO",
                    self.id,
                    self.name,
                    f"策略执行完成: {result_preview}",
                    result_type="strategy_output"
                )
            except ImportError:
                pass

            db = NB(STRATEGY_RESULTS_TABLE)
            result_key = f"{self.id}_{int(timestamp * 1000)}"

            summary = None
            if isinstance(result, dict):
                summary = {
                    "keys": list(result.keys())[:20],
                    "size_bytes": len(str(result)),
                }
                if "signals" in result:
                    summary["signal_count"] = len(result.get("signals", []))
                if "stats" in result:
                    stats = result.get("stats", {})
                    summary["stats_preview"] = {k: stats.get(k) for k in list(stats.keys())[:5]}

            db[result_key] = {
                "strategy_id": self.id,
                "strategy_name": self.name,
                "timestamp": timestamp,
                "summary": summary,
            }
        except Exception:
            pass
    
    def _save_result_to_store(self, input_data: Any, output_data: Any, process_time_ms: float, success: bool, error: str = ""):
        """保存执行结果到 ResultStore。

        注意：
        - 无论是否持久化到数据库，结果都会发送到 SignalStream / Radar / Memory 等下游组件，
          并缓存在内存中用于 UI 展示和统计。
        - 是否持久化到 DB 由策略配置中的 persist_mode 决定，避免结果过多占用磁盘。
        """
        from .result_store import get_result_store
        from ..config import get_strategy_total_history_count, get_strategy_persist_mode

        store = get_result_store()

        persist_mode = get_strategy_persist_mode()
        # 默认策略：
        # - summary: 持久化摘要（DB 中仅保存精简信息）
        # - errors_only: 仅在失败时持久化
        # - none: 完全不持久化到 DB（仅内存/流）
        if persist_mode == "none":
            persist_flag = False
        elif persist_mode == "errors_only":
            persist_flag = not success
        else:  # "summary" 及其他未知值均视为 summary
            persist_flag = True

        store.save(
            strategy_id=self.id,
            strategy_name=self.name,
            success=success,
            input_data=input_data,
            output_data=output_data,
            process_time_ms=process_time_ms,
            error=error,
            persist=persist_flag,
        )

        try:
            from .registry import record_performance_snapshot
            record_performance_snapshot(
                strategy_id=self.id,
                strategy_name=self.name,
                version=getattr(self._metadata, "version", 1),
                process_time_ms=process_time_ms,
                success=success,
            )
        except Exception:
            pass
        
        # 清理单个策略的历史记录
        max_count = getattr(self._metadata, "max_history_count", 100)
        if max_count > 0:
            store.cleanup(strategy_id=self.id, max_count=max_count)
        
        # 清理总历史记录
        total_max_count = get_strategy_total_history_count()
        if total_max_count > 0:
            store.cleanup_total(max_count=total_max_count)
    
    def get_recent_results(self, limit: int = 10) -> List[dict]:
        """获取最近执行结果"""
        from .result_store import get_result_store
        store = get_result_store()
        results = store.get_recent(self.id, limit=limit)
        return [r.to_dict() for r in results]
    
    def get_result_stats(self) -> dict:
        """获取执行统计"""
        from .result_store import get_result_store
        store = get_result_store()
        return store.get_stats(self.id)
    
    def get_result_trend(self, interval_minutes: int = 5, limit: int = 20) -> dict:
        """获取执行趋势"""
        from .result_store import get_result_store
        store = get_result_store()
        return store.get_trend_data(self.id, interval_minutes=interval_minutes, limit=limit)
    
    def bind_datasource(self, datasource_id: str):
        self._metadata.bound_datasource_id = datasource_id
        self.save()
        
        from ..datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds = ds_mgr.get(datasource_id)
        
        if ds is not None:
            self._bind_datasource(ds)

    def _bump_version(self) -> int:
        current = int(getattr(self._metadata, "version", 1) or 1)
        current += 1
        self._metadata.version = current
        return current

    def _record_registry_event(
        self,
        event_type: str,
        before: Dict[str, Any] = None,
        after: Dict[str, Any] = None,
        extra: Dict[str, Any] = None,
    ) -> None:
        try:
            from .registry import record_event
            record_event(
                strategy_id=self.id,
                strategy_name=self.name,
                version=getattr(self._metadata, "version", 1),
                event_type=event_type,
                before=before,
                after=after,
                extra=extra,
            )
        except Exception:
            return
    
    def update_config(
        self,
        name: str = None,
        description: str = None,
        func_code: str = None,
        bound_datasource_id: str = None,
        bound_datasource_ids: List[str] = None,
        compute_mode: str = None,
        window_size: int = None,
        window_type: str = None,
        window_interval: str = None,
        window_return_partial: bool = None,
        max_history_count: int = None,
        dictionary_profile_ids: List[str] = None,
        category: str = None,
        strategy_type: str = None,
        strategy_params: Dict[str, Any] = None,
        strategy_config: Dict[str, Any] = None,
        pipeline: List[Dict[str, Any]] = None,
        model: Dict[str, Any] = None,
        logic: Dict[str, Any] = None,
        plugin: str = None,
        handler_type: str = None,
    ) -> dict:
        # 记录是否正在运行
        was_running = self.is_running
        before_params = dict(getattr(self._metadata, "strategy_params", {}) or {})
        before_config = dict(getattr(self._metadata, "strategy_config", {}) or {})
        before_type = self._get_strategy_type()
        before_code = self._func_code

        if name is not None:
            self._metadata.name = name
        if description is not None:
            self._metadata.description = description
        if compute_mode is not None:
            self._metadata.compute_mode = compute_mode
        if window_size is not None:
            self._metadata.window_size = max(1, int(window_size))
        if window_type is not None:
            self._metadata.window_type = window_type
        if window_interval is not None:
            self._metadata.window_interval = window_interval
        if window_return_partial is not None:
            self._metadata.window_return_partial = window_return_partial
        if max_history_count is not None:
            self._metadata.max_history_count = max(1, int(max_history_count))
        if dictionary_profile_ids is not None:
            self._metadata.dictionary_profile_ids = dictionary_profile_ids
        if category is not None:
            self._metadata.category = category
        if strategy_type is not None:
            self._metadata.strategy_type = str(strategy_type or "legacy")
            self._ensure_runtime_stub_code()
        if strategy_params is not None:
            self._metadata.strategy_params = strategy_params or {}
        if strategy_config is not None:
            self._metadata.strategy_config = strategy_config or {}
        if pipeline is not None or model is not None or logic is not None or plugin is not None:
            merged = dict(getattr(self._metadata, "strategy_config", {}) or {})
            if pipeline is not None:
                merged["pipeline"] = pipeline
            if model is not None:
                merged["model"] = model
            if logic is not None:
                merged["logic"] = logic
            if plugin is not None:
                merged["plugin"] = plugin
            self._metadata.strategy_config = merged
        
        if handler_type is not None:
            self._metadata.handler_type = str(handler_type)

        # 处理多数据源绑定
        if bound_datasource_ids is not None:
            self._metadata.bound_datasource_ids = bound_datasource_ids
            # 同步更新单数据源字段（取第一个）
            self._metadata.bound_datasource_id = bound_datasource_ids[0] if bound_datasource_ids else ""
        elif bound_datasource_id is not None:
            self._metadata.bound_datasource_id = bound_datasource_id
            # 同步更新多数据源列表
            if bound_datasource_id:
                if bound_datasource_id not in self._metadata.bound_datasource_ids:
                    self._metadata.bound_datasource_ids = [bound_datasource_id]
            else:
                self._metadata.bound_datasource_ids = []
        
        if func_code is not None:
            # 对于非 legacy 类型，如果 func_code 为空，设置 stub 代码
            if self._get_strategy_type() != "legacy" and not func_code:
                func_code = "def process(data, context=None):\n    return None\n"
            
            if self._get_strategy_type() == "legacy" and self._get_func_name() not in func_code:
                return {"success": False, "error": f"代码必须包含 {self._get_func_name()} 函数"}
            
            self._func_code = func_code
            self._compiled_func = None
            
            if self._get_strategy_type() == "legacy":
                result = self.compile_code()
                if not result["success"]:
                    return result
        
        # 重置窗口状态（配置变更后需要重新开始）
        with self._window_lock:
            self._window_buffer = []
        self._last_window_trigger = 0
        self._runtime = None
        self._runtime_type = ""
        self._runtime_config_hash = ""

        changed_params = before_params != getattr(self._metadata, "strategy_params", {})
        changed_config = before_config != getattr(self._metadata, "strategy_config", {})
        changed_type = before_type != self._get_strategy_type()
        changed_code = before_code != self._func_code
        if changed_params or changed_config or changed_type or changed_code:
            self._bump_version()
            self._record_registry_event(
                "strategy_update",
                before={
                    "strategy_type": before_type,
                    "strategy_params": before_params,
                    "strategy_config": before_config,
                    "func_code": before_code,
                },
                after={
                    "strategy_type": self._get_strategy_type(),
                    "strategy_params": getattr(self._metadata, "strategy_params", {}),
                    "strategy_config": getattr(self._metadata, "strategy_config", {}),
                    "func_code": self._func_code,
                },
                extra={"restarted": bool(was_running)},
            )
        
        self.save()
        
        # 如果之前在运行，重启以应用新配置
        if was_running:
            self.stop()
            start_result = self.start()
            if not start_result.get("success"):
                return {"success": False, "error": f"重启失败: {start_result.get('error')}"}
        
        return {"success": True, "was_running": was_running, "restarted": was_running}
    
    def save(self) -> dict:
        try:
            db = NB(STRATEGY_TABLE)
            db[self.id] = self.to_dict()
            return {"success": True, "id": self.id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def supports_action(self, action: str) -> bool:
        action = str(action or "").strip().lower()
        strategy_type = self._get_strategy_type()
        if strategy_type == "legacy":
            return action in ("start", "stop", "restart", "reset")
        return action in ("start", "stop", "restart", "reset", "update_params", "update_strategy")

    def update_params(self, params: Dict[str, Any]) -> dict:
        before = dict(getattr(self._metadata, "strategy_params", {}) or {})
        self._metadata.strategy_params = params or {}
        runtime = self._get_runtime()
        if runtime is not None:
            try:
                runtime.update_params(self._metadata.strategy_params)
            except Exception as e:
                self._log("ERROR", "Update params failed", error=str(e))
                return {"success": False, "error": str(e)}
        if before != self._metadata.strategy_params:
            self._bump_version()
            self._record_registry_event(
                "params_update",
                before=before,
                after=dict(self._metadata.strategy_params),
            )
        self.save()
        return {"success": True}

    def update_strategy(self, config: Dict[str, Any]) -> dict:
        before = dict(getattr(self._metadata, "strategy_config", {}) or {})
        merged = dict(before)
        merged.update(config or {})
        self._metadata.strategy_config = merged
        self._runtime = None
        self._runtime_type = ""
        self._runtime_config_hash = ""
        if before != merged:
            self._bump_version()
            self._record_registry_event(
                "config_update",
                before=before,
                after=merged,
            )
        self.save()
        return {"success": True}

    def reset(self) -> dict:
        runtime = self._get_runtime()
        if runtime is not None:
            try:
                runtime.reset()
            except Exception as e:
                self._log("ERROR", "Reset runtime failed", error=str(e))
                return {"success": False, "error": str(e)}

        # 重置窗口状态
        with self._window_lock:
            self._window_buffer = []
        self._last_window_trigger = 0

        # 运行中则重启
        if self.is_running:
            self.stop()
            return self.start()
        return {"success": True}
    
    def to_dict(self) -> dict:
        # 优化：直接访问属性，避免使用getattr
        metadata = self._metadata
        return {
            "metadata": {
                "id": metadata.id,
                "name": metadata.name,
                "description": metadata.description,
                "tags": metadata.tags,
                "bound_datasource_id": getattr(metadata, "bound_datasource_id", ""),
                "bound_datasource_ids": getattr(metadata, "bound_datasource_ids", []),  # 多数据源支持
                "compute_mode": getattr(metadata, "compute_mode", "record"),
                "window_size": getattr(metadata, "window_size", 5),
                "window_type": getattr(metadata, "window_type", "sliding"),
                "window_interval": getattr(metadata, "window_interval", "10s"),
                "window_return_partial": getattr(metadata, "window_return_partial", False),
                "dictionary_profile_ids": getattr(metadata, "dictionary_profile_ids", []),
                "max_history_count": getattr(metadata, "max_history_count", 100),
                "diagram_info": getattr(metadata, "diagram_info", {}),
                "category": getattr(metadata, "category", "默认"),
                "strategy_type": getattr(metadata, "strategy_type", "legacy"),
                "strategy_params": getattr(metadata, "strategy_params", {}),
                "strategy_config": getattr(metadata, "strategy_config", {}),
                "version": getattr(metadata, "version", 1),
                "handler_type": getattr(metadata, "handler_type", "unknown"),
                "created_at": metadata.created_at,
                "updated_at": metadata.updated_at,
            },
            "state": self._state.to_dict(),
            "func_code": self._func_code,
            "was_running": self._was_running,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyEntry":
        metadata_data = data.get("metadata", {})
        metadata = StrategyMetadata(
            id=metadata_data.get("id", ""),
            name=metadata_data.get("name", "unnamed"),
            description=metadata_data.get("description", ""),
            tags=metadata_data.get("tags", []),
            bound_datasource_id=metadata_data.get("bound_datasource_id", ""),
            bound_datasource_ids=metadata_data.get("bound_datasource_ids", []),  # 多数据源支持
            compute_mode=metadata_data.get("compute_mode", "record"),
            window_size=metadata_data.get("window_size", 5),
            window_type=metadata_data.get("window_type", "sliding"),
            window_interval=metadata_data.get("window_interval", "10s"),
            window_return_partial=metadata_data.get("window_return_partial", False),
            dictionary_profile_ids=metadata_data.get("dictionary_profile_ids", []),
            max_history_count=metadata_data.get("max_history_count", 100),
            diagram_info=metadata_data.get("diagram_info", {}),
            category=metadata_data.get("category", "默认"),
            strategy_type=metadata_data.get("strategy_type", "legacy"),
            strategy_params=metadata_data.get("strategy_params", {}),
            strategy_config=metadata_data.get("strategy_config", {}),
            version=metadata_data.get("version", 1),
            handler_type=metadata_data.get("handler_type", "unknown"),
            created_at=metadata_data.get("created_at", time.time()),
            updated_at=metadata_data.get("updated_at", time.time()),
        )
        
        state_data = data.get("state", {})
        state = StrategyState.from_dict(state_data)
        
        entry = cls(metadata=metadata, state=state)
        
        func_code = data.get("func_code", "")
        if func_code:
            entry._func_code = func_code
            try:
                entry.compile_code()
            except Exception:
                pass
        else:
            if entry._get_strategy_type() != "legacy":
                entry._func_code = "def process(data, context=None):\n    return None\n"
                try:
                    entry.compile_code()
                except Exception:
                    pass
        
        entry._was_running = data.get("was_running", False)
        entry._state.status = UnitStatus.STOPPED.value
        
        return entry
