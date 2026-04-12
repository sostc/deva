"""
多数据源策略支持

扩展naja策略系统，支持一个策略绑定多个数据源
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import threading
import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from deva import NS
from deva.naja.strategy import StrategyEntry, StrategyMetadata, StrategyState
from deva.naja.infra.runtime.recoverable import UnitStatus


@dataclass
class MultiDatasourceStrategyMetadata(StrategyMetadata):
    """扩展策略元数据，支持多个数据源"""
    # 保留单数据源字段用于兼容
    bound_datasource_id: str = ""
    # 新增多数据源字段
    bound_datasource_ids: List[str] = field(default_factory=list)


class MultiDatasourceStrategyEntry(StrategyEntry):
    """
    支持多数据源的策略条目
    
    可以同时绑定多个数据源，所有数据源的数据都会流入同一个策略处理
    """
    
    def __init__(
        self,
        metadata: MultiDatasourceStrategyMetadata = None,
        state: StrategyState = None,
    ):
        # 使用父类初始化，但替换metadata类型
        super().__init__(
            metadata=metadata or MultiDatasourceStrategyMetadata(),
            state=state or StrategyState(),
        )
        
        # 多数据源支持
        self._input_streams: Dict[str, Any] = {}  # 数据源ID -> 流
        self._datasource_names: Dict[str, str] = {}  # 数据源ID -> 名称
    
    def _do_start(self, func: Callable) -> dict:
        """启动策略，绑定多个数据源"""
        try:
            # 获取数据源ID列表
            datasource_ids = self._get_datasource_ids()
            
            if not datasource_ids:
                return {"success": True, "message": "No datasource bound"}
            
            from ..datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            
            bound_count = 0
            failed_datasources = []
            
            for ds_id in datasource_ids:
                ds = ds_mgr.get(ds_id)
                if ds is None:
                    failed_datasources.append(ds_id)
                    continue
                
                try:
                    self._bind_datasource(ds)
                    bound_count += 1
                except Exception as e:
                    self._log("ERROR", f"Bind datasource failed", datasource_id=ds_id, error=str(e))
                    failed_datasources.append(ds_id)
            
            if bound_count == 0:
                return {"success": True, "message": f"No datasources could be bound. Failed: {failed_datasources}"}
            
            return {
                "success": True, 
                "message": f"Bound {bound_count} datasources, failed: {len(failed_datasources)}"
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _do_stop(self) -> dict:
        """停止策略，清理所有数据源绑定"""
        try:
            self._input_streams.clear()
            self._datasource_names.clear()
            self._output_stream = None
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _get_datasource_ids(self) -> List[str]:
        """获取要绑定的数据源ID列表"""
        metadata = self._metadata
        
        # 优先使用新的多数据源字段
        if hasattr(metadata, 'bound_datasource_ids') and metadata.bound_datasource_ids:
            return metadata.bound_datasource_ids
        
        # 兼容旧版本单数据源字段
        if metadata.bound_datasource_id:
            return [metadata.bound_datasource_id]
        
        return []
    
    def _bind_datasource(self, datasource: Any):
        """绑定单个数据源"""
        try:
            ds_id = datasource.id
            ds_name = datasource.name
            
            # 获取数据流
            stream = datasource.get_stream()
            if stream is None:
                self._log("ERROR", "Bind datasource failed: stream is None", datasource_id=ds_id)
                return
            
            # 保存流和名称
            self._input_streams[ds_id] = stream
            self._datasource_names[ds_id] = ds_name
            
            # 创建输出流（如果还没有）
            if self._output_stream is None:
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
            
            # 订阅数据流
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
        """处理数据（包含数据源信息）"""
        if not self.is_running:
            return
        
        if self._compiled_func is None:
            return
        
        with self._processing_lock:
            start_time = time.time()
            success = False
            result = None
            error = ""
            
            try:
                # 提取原始数据（用于策略处理）
                original_data = data.get("data", data) if isinstance(data, dict) else data
                
                # 数据补齐
                enriched_data = self._enrich_data(original_data)
                
                # 添加数据源上下文
                if isinstance(data, dict):
                    enriched_data["_context"] = {
                        "datasource_id": data.get("_datasource_id"),
                        "datasource_name": data.get("_datasource_name"),
                        "receive_time": data.get("_receive_time"),
                    }
                
                compute_mode = getattr(self._metadata, "compute_mode", "record")
                
                if compute_mode == "window":
                    result = self._process_window(enriched_data)
                else:
                    result = self._process_record(enriched_data)
                
                if result is not None:
                    success = True
                    self._state.processed_count += 1
                    self._state.last_process_ts = time.time()
                    
                    # 检查是否与上次结果相同
                    if not self._is_duplicate_result(result):
                        self._emit_result(result)
                        self._state.output_count += 1
                
            except Exception as e:
                error = str(e)
                self._state.record_error(error)
                self._log("ERROR", "Process data failed", error=str(e))
            
            # 保存结果
            if result is not None:
                process_time_ms = (time.time() - start_time) * 1000
                self._save_result_to_store(data, result, process_time_ms, success, error)
    
    def add_datasource(self, datasource_id: str) -> dict:
        """动态添加数据源"""
        try:
            from ..datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds = ds_mgr.get(datasource_id)
            
            if ds is None:
                return {"success": False, "error": f"Datasource not found: {datasource_id}"}
            
            # 添加到元数据
            if not hasattr(self._metadata, 'bound_datasource_ids'):
                self._metadata.bound_datasource_ids = []
            
            if datasource_id not in self._metadata.bound_datasource_ids:
                self._metadata.bound_datasource_ids.append(datasource_id)
            
            # 更新单数据源字段（兼容）
            self._metadata.bound_datasource_id = datasource_id
            
            self.save()
            
            # 如果策略正在运行，立即绑定
            if self.is_running:
                self._bind_datasource(ds)
            
            return {"success": True, "message": f"Datasource {datasource_id} added"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def remove_datasource(self, datasource_id: str) -> dict:
        """移除数据源"""
        try:
            # 从元数据中移除
            if hasattr(self._metadata, 'bound_datasource_ids'):
                if datasource_id in self._metadata.bound_datasource_ids:
                    self._metadata.bound_datasource_ids.remove(datasource_id)
            
            # 从流中移除
            if datasource_id in self._input_streams:
                del self._input_streams[datasource_id]
            
            if datasource_id in self._datasource_names:
                del self._datasource_names[datasource_id]
            
            self.save()
            
            return {"success": True, "message": f"Datasource {datasource_id} removed"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_bound_datasources(self) -> List[Dict]:
        """获取已绑定的数据源列表"""
        result = []
        for ds_id, ds_name in self._datasource_names.items():
            result.append({
                "id": ds_id,
                "name": ds_name,
                "active": ds_id in self._input_streams,
            })
        return result
    
    def to_dict(self) -> dict:
        """转换为字典（扩展版本）"""
        base_dict = super().to_dict()
        
        # 添加多数据源信息
        base_dict["bound_datasources"] = self.get_bound_datasources()
        base_dict["bound_datasource_ids"] = self._get_datasource_ids()
        
        return base_dict


# 使用示例和测试代码
def example_usage():
    """使用示例"""
    print("# 创建多数据源策略示例")
    print("")
    print("from deva.naja.strategy.multi_datasource import MultiDatasourceStrategyEntry, MultiDatasourceStrategyMetadata")
    print("")
    print("# 创建元数据")
    print('metadata = MultiDatasourceStrategyMetadata(')
    print('    name="多数据源思想雷达",')
    print('    description="同时处理tick和新闻数据",')
    print('    bound_datasource_ids=["tick_ds_id", "news_ds_id", "text_ds_id"],  # 多个数据源')
    print('    category="记忆系统",')
    print(')')
    print("")
    print("# 创建策略")
    print("entry = MultiDatasourceStrategyEntry(metadata=metadata)")
    print("")
    print("# 编译策略代码")
    print('entry.compile_code("""')
    print("def process(record):")
    print('    # record 包含 _context 字段，可以知道数据来源')
    print('    datasource_id = record.get("_context", {}).get("datasource_id")')
    print('    datasource_name = record.get("_context", {}).get("datasource_name")')
    print("")
    print('    print(f"收到来自 {datasource_name} 的数据")')
    print("")
    print("    # 处理数据...")
    print("    return result")
    print('""")')
    print("")
    print("# 启动策略（会自动绑定所有数据源）")
    print("entry.start()")
    print("")
    print('# 动态添加数据源')
    print('entry.add_datasource("another_ds_id")')
    print("")
    print('# 移除数据源')
    print('entry.remove_datasource("news_ds_id")')
    print("")
    print('# 查看已绑定的数据源')
    print("print(entry.get_bound_datasources())")


if __name__ == "__main__":
    example_usage()
