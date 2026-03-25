"""
注意力系统报告生成器 - 优化版

定时汇总注意力系统的重要信息并写入文件
- 生成易读的 Markdown 格式报告
- 只在交易时间生成（9:30-11:30, 13:00-15:00）
- 只在有内容时生成
- 每5分钟生成一次
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from threading import Thread, Event
import threading

from deva.naja.radar.trading_clock import (
    get_trading_clock,
    TRADING_CLOCK_STREAM,
    is_trading_time as is_trading_time_clock,
)

log = logging.getLogger(__name__)


class AttentionReportGenerator:
    """
    注意力系统报告生成器

    功能：
    1. 定时收集注意力系统的关键指标
    2. 生成易读的 Markdown 报告
    3. 只在交易时间生成（A股：9:30-11:30, 13:00-15:00）
    4. 只在有内容时生成
    5. 按时间命名写入文件
    6. 支持自动清理过期文件

    事件驱动：
    - 订阅 TRADING_CLOCK_STREAM 信号
    - 只在 trading/pre_market 时段生成
    - 支持实验模式和强制模式
    """

    def __init__(
        self,
        output_dir: str = "~/.naja/attention_reports",
        interval_minutes: int = 5,
        max_history_days: int = 7,
    ):
        self.output_dir = os.path.expanduser(output_dir)
        self.interval_seconds = interval_minutes * 60
        self.max_history_days = max_history_days

        os.makedirs(self.output_dir, exist_ok=True)

        self._stop_event = Event()
        self._thread: Optional[Thread] = None

        self._current_report: Dict[str, Any] = {}
        self._report_lock = threading.Lock()

        self._last_report_time: Optional[datetime] = None

        self._current_phase: str = 'closed'
        self._force_mode: bool = False
        self._experiment_mode: bool = False

        log.info(f"报告生成器初始化完成: 输出目录={self.output_dir}, 间隔={interval_minutes}分钟")
    
    def start(self):
        """启动报告生成线程"""
        if self._thread is not None and self._thread.is_alive():
            log.warning("报告生成器已经在运行")
            return

        self._stop_event.clear()

        TRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
        log.info("报告生成器已订阅交易时钟信号")

        self._thread = Thread(target=self._generate_loop, name="AttentionReportGenerator", daemon=True)
        self._thread.start()
        log.info("报告生成器已启动")

    def _on_trading_clock_signal(self, signal: Dict[str, Any]):
        """处理交易时钟信号"""
        signal_type = signal.get('type')
        phase = signal.get('phase')

        if signal_type == 'current_state':
            self._current_phase = phase
        elif signal_type == 'phase_change':
            old_phase = self._current_phase
            self._current_phase = phase
            if phase in ('trading', 'pre_market'):
                log.info(f"[AttentionReport] 进入交易时段，允许生成报告")
            elif old_phase in ('trading', 'pre_market'):
                log.info(f"[AttentionReport] 退出交易时段，暂停生成报告")

    def _is_experiment_mode(self) -> bool:
        """检查是否处于实验模式"""
        try:
            from deva.naja.strategy import get_strategy_manager
            mgr = get_strategy_manager()
            experiment_info = mgr.get_experiment_info()
            return experiment_info.get("active", False)
        except Exception:
            return False

    def _is_allowed_to_generate(self) -> bool:
        """检查是否允许生成报告"""
        if self._force_mode:
            return True
        if self._is_experiment_mode():
            return True
        if self._current_phase in ('trading', 'pre_market'):
            return True
        return False
    
    def stop(self):
        """停止报告生成线程"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        log.info("报告生成器已停止")
    
    def _is_trading_time(self) -> bool:
        """检查当前是否是A股交易时间"""
        return is_trading_time_clock()
    
    def _should_generate_report(self) -> bool:
        """检查是否应该生成报告"""
        if not self._is_allowed_to_generate():
            return False

        now = datetime.now()
        if self._last_report_time:
            current_window_start = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
            last_window_start = self._last_report_time.replace(minute=(self._last_report_time.minute // 5) * 5, second=0, microsecond=0)

            if current_window_start == last_window_start:
                return False

        return True
    
    def _has_content(self, report: Dict[str, Any]) -> bool:
        """检查报告是否有实质内容"""
        # 检查关键指标
        if report.get('summary', {}).get('total_snapshots', 0) == 0:
            return False
        
        # 检查是否有热点事件
        if not report.get('hotspots'):
            return False
        
        # 检查是否有热门板块或个股
        sector_attention = report.get('sector_attention', [])
        symbol_weights = report.get('symbol_weights', [])
        
        if not sector_attention and not symbol_weights:
            return False
        
        return True
    
    def _generate_loop(self):
        """报告生成循环"""
        while not self._stop_event.is_set():
            try:
                # 检查是否应该生成报告
                if self._should_generate_report():
                    # 生成报告
                    report = self._generate_report()
                    
                    # 检查是否有内容
                    if report and self._has_content(report):
                        # 写入文件
                        self._write_report_to_file(report)
                        self._last_report_time = datetime.now()
                        log.info(f"报告已生成: {report['datetime']}")
                    else:
                        log.debug("报告内容为空，跳过生成")
                else:
                    if not self._is_trading_time():
                        log.debug("当前非交易时间，跳过报告生成")
                    else:
                        log.debug("已在当前时间窗口生成过报告，跳过")
                
                # 清理过期文件
                self._cleanup_old_files()
                
            except Exception as e:
                log.error(f"生成报告失败: {e}", exc_info=True)
            
            # 等待下一次检查
            self._stop_event.wait(self.interval_seconds)
    
    def _generate_report(self) -> Optional[Dict[str, Any]]:
        """生成注意力系统报告"""
        try:
            from ..attention.integration import get_attention_integration
            from deva.naja.attention.strategies import get_strategy_manager
            from deva.naja.cognition.history_tracker import get_history_tracker
            
            integration = get_attention_integration()
            if not integration or not integration.attention_system:
                log.debug("注意力系统未初始化，跳过报告生成")
                return None
            
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
            
            return report
            
        except Exception as e:
            log.error(f"生成报告失败: {e}", exc_info=True)
            return None
    
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
            from deva.naja.attention.strategies import get_strategy_manager
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
            from deva.naja.cognition.history_tracker import get_history_tracker
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
            from deva.naja.cognition.history_tracker import get_history_tracker
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
        """将报告写入文件（Markdown格式）"""
        try:
            # 生成文件名: attention_report_YYYY-MM-DD_HH-MM-SS.md
            filename = f"attention_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.md"
            filepath = os.path.join(self.output_dir, filename)
            
            # 生成易读的Markdown内容
            markdown_content = self._generate_markdown(report)
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            log.debug(f"报告已写入: {filepath}")
            
        except Exception as e:
            log.error(f"写入报告文件失败: {e}")
    
    def _generate_markdown(self, report: Dict[str, Any]) -> str:
        """生成易读的Markdown格式报告"""
        lines = []
        
        # 标题
        lines.append(f"# 注意力系统报告")
        lines.append(f"")
        lines.append(f"**生成时间**: {report['datetime']}")
        lines.append(f"")
        
        # 全局摘要
        summary = report.get('summary', {})
        lines.append(f"## 📊 全局摘要")
        lines.append(f"")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 全局注意力 | {summary.get('global_attention', 0):.3f} |")
        lines.append(f"| 活跃板块数 | {summary.get('active_sectors', 0)} |")
        lines.append(f"| 高关注个股数 | {summary.get('high_attention_symbols', 0)} |")
        lines.append(f"| 总快照数 | {summary.get('total_snapshots', 0):,} |")
        lines.append(f"| 平均延迟 | {summary.get('avg_latency_ms', 0):.2f} ms |")
        lines.append(f"")
        
        # 热门板块
        sectors = report.get('sector_attention', [])
        if sectors:
            lines.append(f"## 🔥 热门板块 Top {len(sectors)}")
            lines.append(f"")
            lines.append(f"| 排名 | 板块 | 权重 |")
            lines.append(f"|------|------|------|")
            for i, sector in enumerate(sectors, 1):
                sector_id = sector.get('sector_id', '未知')
                weight = sector.get('weight', 0)
                lines.append(f"| {i} | {sector_id} | {weight:.3f} |")
            lines.append(f"")
        
        # 热门个股
        symbols = report.get('symbol_weights', [])
        if symbols:
            lines.append(f"## 📈 热门个股 Top {min(len(symbols), 10)}")
            lines.append(f"")
            lines.append(f"| 排名 | 股票 | 权重 |")
            lines.append(f"|------|------|------|")
            for i, symbol in enumerate(symbols[:10], 1):
                symbol_code = symbol.get('symbol', '未知')
                weight = symbol.get('weight', 0)
                lines.append(f"| {i} | {symbol_code} | {weight:.2f} |")
            lines.append(f"")
        
        # 板块热点事件
        hotspots = report.get('hotspots', [])
        if hotspots:
            lines.append(f"## ⚡ 板块热点事件")
            lines.append(f"")
            lines.append(f"| 时间 | 板块 | 事件 | 变化 |")
            lines.append(f"|------|------|------|------|")
            for event in reversed(hotspots[-5:]):  # 只显示最近5个
                market_time = event.get('market_time', '--:--')
                sector_name = event.get('sector_name', '未知')
                event_type = event.get('event_type', '')
                change_pct = event.get('change_percent', 0)
                
                # 事件类型中文映射
                type_map = {
                    'new_hot': '🔥 新热点',
                    'cooled': '❄️ 消退',
                    'rise': '📈 拉升',
                    'fall': '📉 回调'
                }
                event_desc = type_map.get(event_type, event_type)
                change_str = f"{change_pct:+.1f}%"
                
                lines.append(f"| {market_time} | {sector_name} | {event_desc} | {change_str} |")
            lines.append(f"")
        
        # 双引擎统计
        dual = report.get('dual_engine', {})
        lines.append(f"## ⚙️ 双引擎统计")
        lines.append(f"")
        lines.append(f"| 引擎 | 统计项 | 数值 |")
        lines.append(f"|------|--------|------|")
        lines.append(f"| River | 处理数据 | {dual.get('river_processed', 0):,} |")
        lines.append(f"| River | 异常检测 | {dual.get('river_anomaly', 0):,} |")
        lines.append(f"| PyTorch | 深度推理 | {dual.get('pytorch_inference', 0):,} |")
        lines.append(f"| PyTorch | 待处理队列 | {dual.get('pytorch_pending', 0):,} |")
        lines.append(f"| - | 触发次数 | {dual.get('trigger_count', 0):,} |")
        lines.append(f"")
        
        # 策略统计
        strategies = report.get('strategies', {})
        lines.append(f"## 🎯 策略统计")
        lines.append(f"")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 总策略数 | {strategies.get('total', 0)} |")
        lines.append(f"| 活跃策略 | {strategies.get('active', 0)} |")
        lines.append(f"| 运行中 | {strategies.get('running', 0)} |")
        lines.append(f"| 最近信号 | {strategies.get('recent_signals', 0)} |")
        lines.append(f"")
        
        # 页脚
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"*报告由注意力系统自动生成*")
        
        return '\n'.join(lines)
    
    def _cleanup_old_files(self):
        """清理过期的报告文件"""
        try:
            cutoff_time = time.time() - (self.max_history_days * 24 * 3600)
            
            for filename in os.listdir(self.output_dir):
                if not filename.startswith('attention_report_') or not filename.endswith('.md'):
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
                if f.startswith('attention_report_') and f.endswith('.md')
            ]
            files.sort(reverse=True)
            return files[:limit]
        except:
            return []
    
    def read_report(self, filename: str) -> Optional[str]:
        """读取指定报告文件内容"""
        try:
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
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
