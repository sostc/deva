"""
实验模式反馈报告生成器

在历史行情回放等实验模式下，收集并报告：
1. 收到的所有热点信号
2. 执行的反馈调节
3. Bandit 学习更新结果
4. 观察样本统计
"""

import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from threading import Thread, Event, Lock
from collections import deque
from deva.naja.register import SR

log = logging.getLogger(__name__)


@dataclass
class SignalRecord:
    """信号记录"""
    timestamp: float
    symbol: str
    block_id: str
    strategy_id: str
    action: str
    attention_score: float
    prediction_score: float
    entry_price: float
    market_state: str


@dataclass
class FeedbackRecord:
    """反馈调节记录"""
    timestamp: float
    symbol: str
    attention_before: float
    attention_after: float
    price_at_record: float
    current_price: float
    pnl_pct: float
    holding_seconds: float
    reason: str


@dataclass
class BanditUpdateRecord:
    """Bandit 更新记录"""
    timestamp: float
    symbol: str
    context: Dict[str, float]
    reward: float
    adjustment: float
    exploration: bool


class FeedbackReportGenerator:
    """
    实验模式反馈报告生成器

    在实验模式运行期间收集数据，实验结束后生成详细报告
    """

    def __init__(
        self,
        output_dir: str = "~/.naja/feedback_reports",
        max_signal_history: int = 10000,
        max_feedback_history: int = 10000,
        max_bandit_history: int = 50000,
    ):
        self.output_dir = os.path.expanduser(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        self._signal_history: deque = deque(maxlen=max_signal_history)
        self._feedback_history: deque = deque(maxlen=max_feedback_history)
        self._bandit_history: deque = deque(maxlen=max_bandit_history)

        self._lock = Lock()
        self._is_collecting = False
        self._experiment_start_time: Optional[float] = None
        self._experiment_end_time: Optional[float] = None
        self._experiment_id: Optional[str] = None
        self._datasource_id: Optional[str] = None

        self._session_stats = {
            'total_signals': 0,
            'total_feedback_records': 0,
            'total_bandit_updates': 0,
            'symbols_tracked': set(),
            'strategies_triggered': set(),
            'actions_count': {'buy': 0, 'sell': 0},
        }

        log.info(f"FeedbackReportGenerator 初始化完成: {self.output_dir}")

    def start_collection(self, datasource_id: str = None) -> str:
        """开始收集实验数据"""
        with self._lock:
            if self._is_collecting:
                log.warning("已经在收集数据")
                return self._experiment_id

            self._experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self._datasource_id = datasource_id
            self._experiment_start_time = time.time()
            self._is_collecting = True

            self._session_stats = {
                'total_signals': 0,
                'total_feedback_records': 0,
                'total_bandit_updates': 0,
                'symbols_tracked': set(),
                'strategies_triggered': set(),
                'actions_count': {'buy': 0, 'sell': 0},
            }

            log.info(f"开始收集反馈数据: experiment_id={self._experiment_id}, datasource={datasource_id}")
            return self._experiment_id

    def stop_collection(self) -> Optional[str]:
        """停止收集并返回实验ID"""
        with self._lock:
            if not self._is_collecting:
                return None

            self._experiment_end_time = time.time()
            self._is_collecting = False
            experiment_id = self._experiment_id

            log.info(f"停止收集反馈数据: {experiment_id}")
            return experiment_id

    def record_signal(
        self,
        symbol: str,
        block_id: str,
        strategy_id: str,
        action: str,
        attention_score: float,
        prediction_score: float,
        entry_price: float,
        market_state: str = "unknown"
    ):
        """记录一个热点信号"""
        if not self._is_collecting:
            return

        record = SignalRecord(
            timestamp=time.time(),
            symbol=symbol,
            block_id=block_id,
            strategy_id=strategy_id,
            action=action,
            attention_score=attention_score,
            prediction_score=prediction_score,
            entry_price=entry_price,
            market_state=market_state,
        )

        with self._lock:
            self._signal_history.append(record)
            self._session_stats['total_signals'] += 1
            self._session_stats['symbols_tracked'].add(symbol)
            self._session_stats['strategies_triggered'].add(strategy_id)
            if action in self._session_stats['actions_count']:
                self._session_stats['actions_count'][action] += 1

    def record_feedback(
        self,
        symbol: str,
        attention_before: float,
        attention_after: float,
        price_at_record: float,
        current_price: float,
        pnl_pct: float,
        holding_seconds: float,
        reason: str = "price_update"
    ):
        """记录一次反馈调节"""
        if not self._is_collecting:
            return

        record = FeedbackRecord(
            timestamp=time.time(),
            symbol=symbol,
            attention_before=attention_before,
            attention_after=attention_after,
            price_at_record=price_at_record,
            current_price=current_price,
            pnl_pct=pnl_pct,
            holding_seconds=holding_seconds,
            reason=reason,
        )

        with self._lock:
            self._feedback_history.append(record)
            self._session_stats['total_feedback_records'] += 1

    def record_bandit_update(
        self,
        symbol: str,
        context: Dict[str, float],
        reward: float,
        adjustment: float,
        exploration: bool = False
    ):
        """记录一次 Bandit 更新"""
        if not self._is_collecting:
            return

        record = BanditUpdateRecord(
            timestamp=time.time(),
            symbol=symbol,
            context=context,
            reward=reward,
            adjustment=adjustment,
            exploration=exploration,
        )

        with self._lock:
            self._bandit_history.append(record)
            self._session_stats['total_bandit_updates'] += 1

    def generate_report(self, experiment_id: str = None) -> Dict[str, Any]:
        """生成实验报告"""
        with self._lock:
            if experiment_id and experiment_id != self._experiment_id:
                log.warning(f"实验ID不匹配: {experiment_id} != {self._experiment_id}")

            duration = 0
            if self._experiment_start_time:
                end = self._experiment_end_time or time.time()
                duration = end - self._experiment_start_time

            report = {
                'experiment_id': self._experiment_id,
                'datasource_id': self._datasource_id,
                'start_time': datetime.fromtimestamp(
                    self._experiment_start_time
                ).strftime('%Y-%m-%d %H:%M:%S') if self._experiment_start_time else None,
                'end_time': datetime.fromtimestamp(
                    self._experiment_end_time
                ).strftime('%Y-%m-%d %H:%M:%S') if self._experiment_end_time else None,
                'duration_seconds': duration,
                'statistics': {
                    'total_signals': self._session_stats['total_signals'],
                    'total_feedback_records': self._session_stats['total_feedback_records'],
                    'total_bandit_updates': self._session_stats['total_bandit_updates'],
                    'unique_symbols': len(self._session_stats['symbols_tracked']),
                    'unique_strategies': len(self._session_stats['strategies_triggered']),
                    'actions': dict(self._session_stats['actions_count']),
                },
                'signals': [asdict(s) for s in list(self._signal_history)],
                'feedback_records': [asdict(f) for f in list(self._feedback_history)],
                'bandit_updates': [asdict(b) for b in list(self._bandit_history)],
            }

            return report

    def generate_markdown_report(self, experiment_id: str = None) -> str:
        """生成 Markdown 格式的报告"""
        report = self.generate_report(experiment_id)

        lines = []
        lines.append(f"# 实验反馈报告")
        lines.append(f"")
        lines.append(f"**实验ID**: {report['experiment_id']}")
        lines.append(f"**数据源**: {report['datasource_id'] or '未知'}")
        lines.append(f"**开始时间**: {report['start_time']}")
        lines.append(f"**结束时间**: {report['end_time']}")
        lines.append(f"**持续时间**: {self._format_duration(report['duration_seconds'])}")
        lines.append(f"")

        stats = report['statistics']
        lines.append(f"## 📊 统计汇总")
        lines.append(f"")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 总信号数 | {stats['total_signals']:,} |")
        lines.append(f"| 反馈记录数 | {stats['total_feedback_records']:,} |")
        lines.append(f"| Bandit更新数 | {stats['total_bandit_updates']:,} |")
        lines.append(f"| 追踪股票数 | {stats['unique_symbols']} |")
        lines.append(f"| 触发策略数 | {stats['unique_strategies']} |")
        lines.append(f"| Buy信号 | {stats['actions'].get('buy', 0)} |")
        lines.append(f"| Sell信号 | {stats['actions'].get('sell', 0)} |")
        lines.append(f"")

        if stats['total_signals'] > 0:
            lines.append(f"## 📈 信号分析")
            lines.append(f"")

            signals_by_strategy = {}
            signals_by_symbol = {}
            for sig in report['signals']:
                sid = sig['strategy_id']
                signals_by_strategy[sid] = signals_by_strategy.get(sid, 0) + 1
                sym = sig['symbol']
                signals_by_symbol[sym] = signals_by_symbol.get(sym, 0) + 1

            lines.append(f"### 按策略统计")
            lines.append(f"")
            lines.append(f"| 策略ID | 信号数 |")
            lines.append(f"|------|------|")
            for sid, count in sorted(signals_by_strategy.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"| {sid} | {count} |")
            lines.append(f"")

            lines.append(f"### 按股票统计 (Top 10)")
            lines.append(f"")
            lines.append(f"| 股票 | 信号数 |")
            lines.append(f"|------|------|")
            for sym, count in sorted(signals_by_symbol.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"| {sym} | {count} |")
            lines.append(f"")

        if stats['total_feedback_records'] > 0:
            lines.append(f"## 🔄 反馈调节分析")
            lines.append(f"")

            pnl_values = [f['pnl_pct'] for f in report['feedback_records']]
            if pnl_values:
                avg_pnl = sum(pnl_values) / len(pnl_values)
                max_pnl = max(pnl_values)
                min_pnl = min(pnl_values)
                positive_count = len([p for p in pnl_values if p > 0])

                lines.append(f"| 指标 | 数值 |")
                lines.append(f"|------|------|")
                lines.append(f"| 平均收益 | {avg_pnl:+.2f}% |")
                lines.append(f"| 最大收益 | {max_pnl:+.2f}% |")
                lines.append(f"| 最大亏损 | {min_pnl:+.2f}% |")
                lines.append(f"| 正收益次数 | {positive_count}/{len(pnl_values)} |")
                lines.append(f"")

            feedback_by_reason = {}
            for f in report['feedback_records']:
                reason = f['reason']
                feedback_by_reason[reason] = feedback_by_reason.get(reason, 0) + 1

            lines.append(f"### 反馈原因分布")
            lines.append(f"")
            lines.append(f"| 原因 | 次数 |")
            lines.append(f"|------|------|")
            for reason, count in sorted(feedback_by_reason.items(), key=lambda x: -x[1]):
                lines.append(f"| {reason} | {count} |")
            lines.append(f"")

        if stats['total_bandit_updates'] > 0:
            lines.append(f"## 🎯 Bandit 学习分析")
            lines.append(f"")

            rewards = [b['reward'] for b in report['bandit_updates']]
            adjustments = [b['adjustment'] for b in report['bandit_updates']]
            exploration_count = len([b for b in report['bandit_updates'] if b['exploration']])

            lines.append(f"| 指标 | 数值 |")
            lines.append(f"|------|------|")
            lines.append(f"| 平均Reward | {sum(rewards)/len(rewards):+.4f} |")
            lines.append(f"| 平均Adjustment | {sum(adjustments)/len(adjustments):.4f} |")
            lines.append(f"| 探索次数 | {exploration_count} ({100*exploration_count/len(rewards):.1f}%) |")
            lines.append(f"")

            context_keys = ['attention', 'prediction_score', 'volatility']
            lines.append(f"### 上下文分布")
            for key in context_keys:
                values = [b['context'].get(key, 0) for b in report['bandit_updates'] if key in b['context']]
                if values:
                    lines.append(f"| {key} | 均值={sum(values)/len(values):.3f} |")
            lines.append(f"")

        lines.append(f"---")
        lines.append(f"*报告由反馈报告生成器自动生成*")

        return '\n'.join(lines)

    def save_report(self, experiment_id: str = None) -> str:
        """保存报告到文件"""
        report = self.generate_report(experiment_id)
        md_report = self.generate_markdown_report(experiment_id)

        exp_id = experiment_id or self._experiment_id or "unknown"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"feedback_report_{exp_id}_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_report)

        json_path = filepath.replace('.md', '.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        log.info(f"报告已保存: {filepath}")
        return filepath

    def get_summary(self) -> Dict[str, Any]:
        """获取当前收集状态的摘要"""
        with self._lock:
            return {
                'is_collecting': self._is_collecting,
                'experiment_id': self._experiment_id,
                'datasource_id': self._datasource_id,
                'signals_count': len(self._signal_history),
                'feedback_count': len(self._feedback_history),
                'bandit_count': len(self._bandit_history),
                'duration_seconds': (
                    time.time() - self._experiment_start_time
                    if self._is_collecting and self._experiment_start_time
                    else 0
                ),
            }

    def clear(self):
        """清除所有收集的数据"""
        with self._lock:
            self._signal_history.clear()
            self._feedback_history.clear()
            self._bandit_history.clear()
            self._experiment_id = None
            self._experiment_start_time = None
            self._experiment_end_time = None
            self._datasource_id = None
            self._is_collecting = False
            log.info("已清除所有收集数据")

    def _emit_to_insight(self) -> int:
        """将实验数据推送到认知系统的 InsightPool，供 LLM Reflection 使用"""
        try:

            pool = SR('insight_pool')
            insights_created = 0

            stats = self._session_stats
            if stats['total_signals'] == 0:
                return 0

            report = self.generate_report()

            insight_candidates = []

            summary_stats = report.get('statistics', {})
            if summary_stats.get('total_signals', 0) > 0:
                summary_theme = f"实验反馈总结: {stats['total_signals']}个信号"
                insight_candidates.append({
                    "theme": summary_theme,
                    "summary": self._build_summary_summary(report),
                    "symbols": list(stats['symbols_tracked'])[:10],
                    "blocks": [],
                    "confidence": min(0.9, 0.5 + stats['total_signals'] * 0.01),
                    "actionability": 0.6,
                    "system_attention": 0.7,
                    "source": "feedback_experiment",
                    "signal_type": "experiment_feedback_summary",
                    "payload": {
                        "experiment_id": self._experiment_id,
                        "statistics": summary_stats,
                    },
                })

            bandit_stats = self._analyze_bandit_performance()
            if bandit_stats:
                bandit_theme = f"Bandit学习分析"
                insight_candidates.append({
                    "theme": bandit_theme,
                    "summary": self._build_bandit_summary(bandit_stats),
                    "symbols": [],
                    "blocks": [],
                    "confidence": 0.7,
                    "actionability": 0.8,
                    "system_attention": 0.6,
                    "source": "feedback_experiment",
                    "signal_type": "bandit_learning_analysis",
                    "payload": {
                        "experiment_id": self._experiment_id,
                        "bandit_stats": bandit_stats,
                    },
                })

            for candidate in insight_candidates:
                try:
                    from deva.naja.events import get_event_bus, HotspotShiftEvent
                    event_bus = get_event_bus()
                    event = HotspotShiftEvent(
                        event_type=candidate.get("signal_type", "bandit_learning_analysis"),
                        timestamp=time.time(),
                        title=candidate.get("theme", ""),
                        content=candidate.get("summary", ""),
                        score=candidate.get("system_hotspot", 0.6),
                        payload=candidate.get("payload", {}),
                        old_value=None,
                        new_value=candidate.get("system_hotspot", 0.6),
                    )
                    event_bus.publish(event)
                    insights_created += 1
                except Exception as e:
                    log.warning(f"发布洞察事件失败: {e}")

            log.info(f"已推送 {insights_created} 个洞察到 InsightPool")
            return insights_created

        except Exception as e:
            log.warning(f"推送洞察到 InsightPool 失败: {e}")
            return 0

    def _analyze_bandit_performance(self) -> Optional[Dict[str, Any]]:
        """分析 Bandit 学习性能"""
        if len(self._bandit_history) < 10:
            return None

        rewards = [b.reward for b in self._bandit_history]
        adjustments = [b.adjustment for b in self._bandit_history]
        explorations = len([b for b in self._bandit_history if b.exploration])

        return {
            "total_updates": len(self._bandit_history),
            "avg_reward": sum(rewards) / len(rewards),
            "reward_std": (sum((r - sum(rewards)/len(rewards))**2 for r in rewards) / len(rewards)) ** 0.5 if len(rewards) > 1 else 0,
            "avg_adjustment": sum(adjustments) / len(adjustments),
            "exploration_rate": explorations / len(self._bandit_history),
            "positive_reward_rate": len([r for r in rewards if r > 0]) / len(rewards),
        }

    def _build_summary_summary(self, report: Dict[str, Any]) -> str:
        """构建总结摘要文本"""
        stats = report.get('statistics', {})
        duration = report.get('duration_seconds', 0)

        parts = []
        parts.append(f"实验持续{self._format_duration(duration)}")
        parts.append(f"共捕捉到{stats.get('total_signals', 0)}个信号")
        parts.append(f"追踪了{stats.get('unique_symbols', 0)}只股票")
        parts.append(f"触发{stats.get('unique_strategies', 0)}个策略")

        actions = stats.get('actions', {})
        if actions.get('buy', 0) > 0 or actions.get('sell', 0) > 0:
            parts.append(f"其中Buy信号{actions.get('buy', 0)}个,Sell信号{actions.get('sell', 0)}个")

        feedback_count = stats.get('total_feedback_records', 0)
        if feedback_count > 0:
            parts.append(f"产生{feedback_count}条价格反馈记录")

        return "，".join(parts) + "。"

    def _build_bandit_summary(self, bandit_stats: Dict[str, Any]) -> str:
        """构建 Bandit 学习摘要"""
        parts = []
        parts.append(f"Bandit共更新{bandit_stats['total_updates']}次")

        avg_reward = bandit_stats.get('avg_reward', 0)
        reward_status = "正" if avg_reward > 0 else "负"
        parts.append(f"平均Reward为{avg_reward:+.4f}({reward_status})")

        exp_rate = bandit_stats.get('exploration_rate', 0)
        parts.append(f"探索率{exp_rate:.1%}")

        pos_rate = bandit_stats.get('positive_reward_rate', 0)
        parts.append(f"正收益比例{pos_rate:.1%}")

        return "，".join(parts) + "。"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """格式化时长"""
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            return f"{seconds/60:.1f}分钟"
        else:
            return f"{seconds/3600:.1f}小时"


_feedback_report_generator: Optional[FeedbackReportGenerator] = None
_generator_lock = Lock()


def get_feedback_report_generator() -> FeedbackReportGenerator:
    """获取全局单例"""
    global _feedback_report_generator
    if _feedback_report_generator is None:
        with _generator_lock:
            if _feedback_report_generator is None:
                _feedback_report_generator = FeedbackReportGenerator()
    return _feedback_report_generator
