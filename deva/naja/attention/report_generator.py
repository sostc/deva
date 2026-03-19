"""
注意力系统报告生成器

定时汇总注意力系统的重要信息并写入文件
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from threading import Thread, Event
import threading

log = logging.getLogger(__name__)


class AttentionReportGenerator:
    """
    注意力系统报告生成器
    
    功能：
    1. 定时收集注意力系统的关键指标
    2. 生成结构化的报告数据
    3. 按时间命名写入文件
    4. 支持自动清理过期文件
    """
    
    def __init__(
        self,
        output_dir: str = "~/.naja/attention_reports",
        interval_minutes: int = 5,  # 默认每5分钟生成一次报告
        max_history_days: int = 7,   # 保留7天的历史报告
        max_file_size_mb: int = 10   # 单个文件最大10MB
    ):
        self.output_dir = os.path.expanduser(output_dir)
        self.interval_seconds = interval_minutes * 60
        self.max_history_days = max_history_days
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 定时器控制
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        
        # 当前报告数据缓存
        self._current_report: Dict[str, Any] = {}
        self._report_lock = threading.Lock()
        
        log.info(f"报告生成器初始化完成: 输出目录={self.output_dir}, 间隔={interval_minutes}分钟")
    
    def start(self):
        """启动报告生成线程"""
        if self._thread is not None and self._thread.is_alive():
            log.warning("报告生成器已经在运行")
            return
        
        self._stop_event.clear()
        self._thread = Thread(target=self._generate_loop, name="AttentionReportGenerator", daemon=True)
        self._thread.start()
        log.info("报告生成器已启动")
    
    def stop(self):
        """停止报告生成线程"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        log.info("报告生成器已停止")
    
    def _generate_loop(self):
        """报告生成循环"""
        while not self._stop_event.is_set():
            try:
                # 生成报告
                self._generate_report()
                
                # 清理过期文件
                self._cleanup_old_files()
                
            except Exception as e:
                log.error(f"生成报告失败: {e}", exc_info=True)
            
            # 等待下一次生成
            self._stop_event.wait(self.interval_seconds)
    
    def _generate_report(self):
        """生成注意力系统报告"""
        try:
            from ..attention_integration import get_attention_integration
            from naja_attention_strategies import get_strategy_manager
            from .history_tracker import get_history_tracker
            
            integration = get_attention_integration()
            if not integration or not integration.attention_system:
                log.debug("注意力系统未初始化，跳过报告生成")
                return
            
            # 收集数据
            report = {
                'timestamp': time.time(),
                'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'summary': self._collect_summary(integration),
                'global_attention': self._collect_global_attention(integration),
                'sector_attention': self._collect_sector_attention(integration),
                'symbol_weights': self._collect_symbol_weights(integration),
                'dual_engine': self._collect_dual_engine_stats(integration),
                'strategies': self._collect_strategy_stats(),
                'changes': self._collect_recent_changes(),
                'hotspots': self._collect_sector_hotspots()
            }
            
            # 更新缓存
            with self._report_lock:
                self._current_report = report
            
            # 写入文件
            self._write_report_to_file(report)
            
            log.info(f"报告已生成: {report['datetime']}")
            
        except Exception as e:
            log.error(f"生成报告失败: {e}", exc_info=True)
    
    def _collect_summary(self, integration) -> Dict[str, Any]:
        """收集汇总信息"""
        try:
            status = integration.get_system_status()
            return {
                'global_attention': status.get('global_attention', 0),
                'active_sectors': len(status.get('active_sectors', [])),
                'high_attention_symbols': len(status.get('high_attention_symbols', [])),
                'total_snapshots': status.get('total_snapshots', 0),
                'avg_latency_ms': status.get('avg_latency_ms', 0)
            }
        except:
            return {}
    
    def _collect_global_attention(self, integration) -> Dict[str, Any]:
        """收集全局注意力信息"""
        try:
            attention_system = integration.attention_system
            if not attention_system:
                return {}
            
            return {
                'current': attention_system._last_global_attention,
                'market_state': attention_system.global_attention.get_market_state()
            }
        except:
            return {}
    
    def _collect_sector_attention(self, integration) -> List[Dict[str, Any]]:
        """收集板块注意力信息（Top 10）"""
        try:
            attention_system = integration.attention_system
            if not attention_system:
                return []
            
            weights = attention_system._last_sector_attention
            sorted_sectors = sorted(
                weights.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
            
            return [
                {
                    'sector_id': sector_id,
                    'weight': float(weight)
                }
                for sector_id, weight in sorted_sectors
            ]
        except:
            return []
    
    def _collect_symbol_weights(self, integration) -> List[Dict[str, Any]]:
        """收集个股权重信息（Top 20）"""
        try:
            attention_system = integration.attention_system
            if not attention_system:
                return []
            
            weights = attention_system._last_symbol_weights
            sorted_symbols = sorted(
                weights.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]
            
            return [
                {
                    'symbol': symbol,
                    'weight': float(weight)
                }
                for symbol, weight in sorted_symbols
            ]
        except:
            return []
    
    def _collect_dual_engine_stats(self, integration) -> Dict[str, Any]:
        """收集双引擎统计信息"""
        try:
            attention_system = integration.attention_system
            if not attention_system:
                return {}
            
            summary = attention_system.dual_engine.get_trigger_summary()
            return {
                'trigger_count': summary.get('trigger_count', 0),
                'river_processed': summary.get('river_stats', {}).get('processed_count', 0),
                'river_anomaly': summary.get('river_stats', {}).get('anomaly_count', 0),
                'pytorch_inference': summary.get('pytorch_stats', {}).get('inference_count', 0),
                'pytorch_pending': summary.get('pytorch_stats', {}).get('pending_queue_size', 0)
            }
        except:
            return {}
    
    def _collect_strategy_stats(self) -> Dict[str, Any]:
        """收集策略统计信息"""
        try:
            from naja_attention_strategies import get_strategy_manager
            manager = get_strategy_manager()
            if not manager:
                return {}
            
            configs = manager.get_strategy_configs()
            return {
                'total': len(configs),
                'active': sum(1 for c in configs.values() if c.enabled),
                'running': sum(1 for c in configs.values() if c.is_running),
                'recent_signals': len(manager.get_recent_signals(n=100))
            }
        except:
            return {}
    
    def _collect_recent_changes(self) -> List[Dict[str, Any]]:
        """收集最近的注意力变化"""
        try:
            from .history_tracker import get_history_tracker
            tracker = get_history_tracker()
            if not tracker:
                return []
            
            changes = tracker.get_recent_changes(n=10)
            return [
                {
                    'timestamp': c.timestamp,
                    'type': c.change_type,
                    'item_type': c.item_type,
                    'item_id': c.item_id,
                    'item_name': c.item_name,
                    'old_weight': c.old_weight,
                    'new_weight': c.new_weight,
                    'change_percent': c.change_percent
                }
                for c in changes
            ]
        except:
            return []
    
    def _collect_sector_hotspots(self) -> List[Dict[str, Any]]:
        """收集板块热点事件"""
        try:
            from .history_tracker import get_history_tracker
            tracker = get_history_tracker()
            if not tracker:
                return []
            
            events = list(tracker.sector_hotspot_events)[-10:]
            return [
                {
                    'timestamp': e.timestamp,
                    'market_time': e.market_time,
                    'sector_id': e.sector_id,
                    'sector_name': e.sector_name,
                    'event_type': e.event_type,
                    'weight_change': e.weight_change,
                    'change_percent': e.change_percent,
                    'description': e.description
                }
                for e in events
            ]
        except:
            return []
    
    def _write_report_to_file(self, report: Dict[str, Any]):
        """将报告写入文件"""
        try:
            # 生成文件名: attention_report_YYYY-MM-DD_HH-MM-SS.json
            filename = f"attention_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
            filepath = os.path.join(self.output_dir, filename)
            
            # 写入JSON文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            log.debug(f"报告已写入: {filepath}")
            
        except Exception as e:
            log.error(f"写入报告文件失败: {e}")
    
    def _cleanup_old_files(self):
        """清理过期的报告文件"""
        try:
            cutoff_time = time.time() - (self.max_history_days * 24 * 3600)
            
            for filename in os.listdir(self.output_dir):
                if not filename.startswith('attention_report_') or not filename.endswith('.json'):
                    continue
                
                filepath = os.path.join(self.output_dir, filename)
                
                # 检查文件修改时间
                try:
                    mtime = os.path.getmtime(filepath)
                    if mtime < cutoff_time:
                        os.remove(filepath)
                        log.debug(f"删除过期报告: {filename}")
                except OSError:
                    pass
                
                # 检查文件大小
                try:
                    size = os.path.getsize(filepath)
                    if size > self.max_file_size_bytes:
                        os.remove(filepath)
                        log.warning(f"删除超大报告: {filename} ({size / 1024 / 1024:.1f}MB)")
                except OSError:
                    pass
                    
        except Exception as e:
            log.error(f"清理过期文件失败: {e}")
    
    def get_current_report(self) -> Dict[str, Any]:
        """获取当前报告缓存"""
        with self._report_lock:
            return self._current_report.copy()
    
    def get_report_files(self, limit: int = 10) -> List[str]:
        """获取最近的报告文件列表"""
        try:
            files = [
                f for f in os.listdir(self.output_dir)
                if f.startswith('attention_report_') and f.endswith('.json')
            ]
            files.sort(reverse=True)
            return files[:limit]
        except:
            return []
    
    def read_report(self, filename: str) -> Optional[Dict[str, Any]]:
        """读取指定报告文件"""
        try:
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None


# 全局实例
_report_generator: Optional[AttentionReportGenerator] = None


def get_report_generator(
    output_dir: str = "~/.naja/attention_reports",
    interval_minutes: int = 5
) -> AttentionReportGenerator:
    """获取报告生成器单例"""
    global _report_generator
    if _report_generator is None:
        _report_generator = AttentionReportGenerator(
            output_dir=output_dir,
            interval_minutes=interval_minutes
        )
    return _report_generator


def start_report_generator():
    """启动报告生成器"""
    generator = get_report_generator()
    generator.start()
    return generator


def stop_report_generator():
    """停止报告生成器"""
    global _report_generator
    if _report_generator:
        _report_generator.stop()
        _report_generator = None
