#!/usr/bin/env python
"""
实时选股策略 Skill - 注意力感知版本

在原有基础上增加：
1. 注意力系统对接 - 只关注高注意力股票
2. 全局市场状态感知 - 根据市场热度调整策略
3. 板块轮动感知 - 优先选择活跃板块股票
4. 动态参数调节 - 根据注意力自动调整阈值
"""

import asyncio
import time
import random
from typing import AsyncIterator, Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

import pandas as pd
import numpy as np

# River 在线学习库
from river import linear_model
from river import preprocessing
from river import optim
from river import metrics
from river import compose

from deva.naja.stream_skill import (
    StreamSkill,
    SkillContext,
    SkillEvent,
    get_execution_engine,
    AgentSkillInterface,
)
from deva import NB

# 导入注意力感知混入
from deva.naja.strategy.attention_aware_strategies import AttentionAwareMixin


@dataclass
class StockPosition:
    """股票持仓"""
    code: str
    name: str
    buy_price: float
    buy_time: float
    volume: int = 100
    current_price: float = 0.0
    attention_weight: float = 1.0  # 买入时的注意力权重
    
    @property
    def profit_pct(self) -> float:
        """收益率"""
        if self.buy_price == 0:
            return 0.0
        return (self.current_price - self.buy_price) / self.buy_price * 100
    
    @property
    def profit_amount(self) -> float:
        """收益金额"""
        return (self.current_price - self.buy_price) * self.volume


@dataclass
class StrategyResult:
    """策略执行结果"""
    strategy_name: str
    params: Dict[str, Any]
    total_return: float = 0.0
    trades: List[Dict] = field(default_factory=list)
    positions: List[StockPosition] = field(default_factory=list)
    equity_curve: List[Tuple[float, float]] = field(default_factory=list)
    attention_stats: Dict = field(default_factory=dict)  # 注意力统计
    
    @property
    def win_rate(self) -> float:
        """胜率"""
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.get('profit', 0) > 0)
        return wins / len(self.trades) * 100
    
    @property
    def max_drawdown(self) -> float:
        """最大回撤"""
        if not self.equity_curve:
            return 0.0
        
        max_dd = 0.0
        peak = self.equity_curve[0][1]
        
        for _, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)
        
        return max_dd


class RealtimeStockPickerSkillWithAttention(StreamSkill, AttentionAwareMixin):
    """
    实时选股策略 Skill - 注意力感知版本
    
    新增功能:
    1. 只处理高注意力股票（节省计算资源）
    2. 根据全局注意力调整买入阈值
    3. 优先选择活跃板块的股票
    4. 根据个股权重动态调整仓位
    """
    
    def __init__(self, skill_id: str = "realtime_stock_picker_attention"):
        StreamSkill.__init__(self, skill_id)
        AttentionAwareMixin.__init__(self)
        
        # 策略配置
        self.strategy_name = ""
        self.strategy_params = {}
        
        # River 模型
        self.model = None
        self.scaler = preprocessing.StandardScaler()
        
        # 持仓和交易
        self.positions: Dict[str, StockPosition] = {}
        self.initial_capital = 100000.0
        self.current_capital = 100000.0
        
        # 特征工程
        self.feature_window = 5
        self.stock_history: Dict[str, List[Dict]] = defaultdict(list)
        
        # 基础阈值（会根据注意力动态调整）
        self.base_buy_threshold = 0.6
        self.base_sell_threshold = -0.1
        
        # 注意力统计
        self.attention_processed_frames = 0
        self.attention_filtered_stocks = 0
        self.attention_total_stocks = 0
        
    def init_model(self, model_type: str = "logistic", learning_rate: float = 0.01):
        """初始化 River 模型"""
        if model_type == "logistic":
            self.model = linear_model.LogisticRegression(
                optimizer=optim.SGD(learning_rate)
            )
        elif model_type == "linear":
            self.model = linear_model.LinearRegression(
                optimizer=optim.SGD(learning_rate)
            )
        else:
            self.model = linear_model.PARegressor()
    
    def extract_features(self, stock_code: str, current_data: pd.DataFrame) -> Dict[str, float]:
        """提取股票特征（增加注意力相关特征）"""
        history = self.stock_history.get(stock_code, [])
        
        if len(history) < self.feature_window:
            return {}
        
        recent = history[-self.feature_window:]
        
        prices = [h['price'] for h in recent]
        volumes = [h['volume'] for h in recent]
        
        features = {
            'price_change_pct': (prices[-1] - prices[0]) / prices[0] * 100,
            'volatility': np.std(prices) / np.mean(prices) * 100,
            'volume_ratio': volumes[-1] / np.mean(volumes) if np.mean(volumes) > 0 else 1.0,
            'price_momentum': (prices[-1] - prices[-2]) / prices[-2] * 100 if len(prices) >= 2 else 0,
            'high_low_range': (max(prices) - min(prices)) / np.mean(prices) * 100,
        }
        
        # 增加注意力特征
        if self._use_attention:
            weight = self.get_symbol_attention_weight(stock_code)
            sector_attention = self._get_sector_attention_for_stock(stock_code)
            global_attention = self.get_global_attention()
            
            features['attention_weight'] = weight
            features['sector_attention'] = sector_attention
            features['global_attention'] = global_attention
        
        return features
    
    def _get_sector_attention_for_stock(self, stock_code: str) -> float:
        """获取股票所属板块的平均注意力"""
        if not self._use_attention:
            return 0.5
        
        # 这里简化处理，实际应该查询股票所属板块
        # 返回全局注意力作为近似
        return self.get_global_attention()
    
    def predict_profit(self, features: Dict[str, float]) -> float:
        """预测收益概率"""
        if self.model is None or not features:
            return 0.5
        
        try:
            scaled_features = self.scaler.learn_one(features).transform_one(features)
            prediction = self.model.predict_one(scaled_features)
            
            if hasattr(self.model, 'predict_proba_one'):
                proba = self.model.predict_proba_one(scaled_features)
                return proba.get(True, 0.5) if isinstance(proba, dict) else 0.5
            
            return min(max(prediction / 10.0 + 0.5, 0), 1)
            
        except Exception as e:
            return 0.5
    
    def update_model(self, features: Dict[str, float], actual_return: float):
        """在线更新模型"""
        if self.model is None or not features:
            return
        
        try:
            scaled_features = self.scaler.learn_one(features).transform_one(features)
            label = actual_return > 0
            self.model.learn_one(scaled_features, label)
            
        except Exception as e:
            pass
    
    def get_dynamic_thresholds(self) -> tuple:
        """
        根据注意力动态调整阈值
        
        全局注意力高 -> 降低买入阈值（更容易买入），放宽止损
        全局注意力低 -> 提高买入阈值（更严格），收紧止损
        """
        if not self._use_attention:
            return self.base_buy_threshold, self.base_sell_threshold
        
        global_attention = self.get_global_attention()
        
        # 买入阈值调整：注意力高时降低阈值（更容易触发）
        # 范围：0.5 - 0.7
        buy_threshold = self.base_buy_threshold * (1.2 - global_attention * 0.4)
        
        # 卖出阈值调整：注意力高时放宽止损（容忍更大回撤）
        # 范围：-0.15 - -0.05
        sell_threshold = self.base_sell_threshold * (0.5 + global_attention)
        
        return buy_threshold, sell_threshold
    
    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行策略"""
        # 解析输入参数
        self.strategy_name = input_data.get('strategy_name', 'default')
        self.strategy_params = input_data.get('strategy_params', {})
        max_positions = input_data.get('max_positions', 5)
        replay_rounds = input_data.get('replay_rounds', 1)
        
        # 是否启用注意力
        use_attention = input_data.get('use_attention', True)
        attention_min_weight = input_data.get('attention_min_weight', 1.0)
        
        if not use_attention:
            self.disable_attention()
        
        # 初始化模型
        model_type = self.strategy_params.get('model_type', 'logistic')
        learning_rate = self.strategy_params.get('learning_rate', 0.01)
        self.init_model(model_type, learning_rate)
        
        # 初始化结果
        result = StrategyResult(
            strategy_name=self.strategy_name,
            params=self.strategy_params
        )
        
        # 阶段 1: 初始化
        context.current_stage = "initialization"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "stage": "initialization",
                "strategy": self.strategy_name,
                "use_attention": use_attention,
                "global_attention": self.get_global_attention() if use_attention else 0.5
            },
            stage="initialization"
        )
        
        # 连接数据源
        db = NB("quant_snapshot_5min_window")
        replay_data = list(db.items())
        
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 5,
                "message": f"初始化完成，数据源有 {len(replay_data)} 条记录，注意力系统: {'启用' if use_attention else '禁用'}"
            },
            stage="initialization"
        )
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "initialization"},
            stage="initialization"
        )
        
        # 阶段 2: 多轮回放训练
        for round_num in range(replay_rounds):
            context.current_stage = f"training_round_{round_num + 1}"
            
            yield SkillEvent(
                event_type="stage_started",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"stage": f"training_round_{round_num + 1}", "round": round_num + 1},
                stage=f"training_round_{round_num + 1}"
            )
            
            # 重置
            self.current_capital = self.initial_capital
            self.positions.clear()
            self.stock_history.clear()
            self.attention_processed_frames = 0
            self.attention_filtered_stocks = 0
            self.attention_total_stocks = 0
            
            # 处理每一帧数据
            total_frames = len(replay_data)
            for i, (timestamp, df) in enumerate(replay_data):
                if not self._pause_event.is_set():
                    await self._pause_event.wait()
                
                if self._state.value in ("cancelled", "failed"):
                    return
                
                progress = 10 + int((round_num * total_frames + i) / (replay_rounds * total_frames) * 70)
                
                if i % 10 == 0:
                    global_attention = self.get_global_attention() if use_attention else 0.5
                    yield SkillEvent(
                        event_type="progress",
                        timestamp=time.time(),
                        execution_id=context.execution_id,
                        data={
                            "progress": progress,
                            "message": f"第 {round_num + 1}/{replay_rounds} 轮，处理 {i}/{total_frames} 帧，"
                                      f"全局注意力: {global_attention:.2f}",
                            "round": round_num + 1,
                            "frame": i,
                            "capital": self.current_capital,
                            "positions": len(self.positions),
                            "global_attention": global_attention
                        },
                        stage=f"training_round_{round_num + 1}"
                    )
                
                # 处理这一帧（传入注意力最小权重）
                await self._process_frame(df, timestamp, max_positions, i, attention_min_weight)
                
                # 记录权益曲线
                total_value = self.current_capital + sum(
                    pos.current_price * pos.volume for pos in self.positions.values()
                )
                result.equity_curve.append((timestamp, total_value))
            
            # 计算本轮收益
            final_value = self.current_capital + sum(
                pos.current_price * pos.volume for pos in self.positions.values()
            )
            round_return = (final_value - self.initial_capital) / self.initial_capital * 100
            
            # 保存注意力统计
            result.attention_stats = {
                'processed_frames': self.attention_processed_frames,
                'filtered_stocks': self.attention_filtered_stocks,
                'total_stocks': self.attention_total_stocks,
                'filter_ratio': self.attention_filtered_stocks / max(self.attention_total_stocks, 1),
                'global_attention_avg': self.get_global_attention()
            }
            
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "progress": 10 + int((round_num + 1) / replay_rounds * 70),
                    "message": f"第 {round_num + 1} 轮完成，收益率: {round_return:.2f}%，"
                              f"过滤率: {result.attention_stats['filter_ratio']:.1%}",
                    "round": round_num + 1,
                    "round_return": round_return,
                    "attention_stats": result.attention_stats
                },
                stage=f"training_round_{round_num + 1}"
            )
            
            yield SkillEvent(
                event_type="stage_completed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "stage": f"training_round_{round_num + 1}",
                    "round": round_num + 1,
                    "round_return": round_return
                },
                stage=f"training_round_{round_num + 1}"
            )
            
            result.total_return = round_return
        
        # 阶段 3: 生成报告
        context.current_stage = "report"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report"},
            stage="report"
        )
        
        report = {
            "strategy_name": self.strategy_name,
            "params": self.strategy_params,
            "total_return": result.total_return,
            "win_rate": result.win_rate,
            "max_drawdown": result.max_drawdown,
            "trade_count": len(result.trades),
            "final_capital": self.current_capital + sum(
                pos.current_price * pos.volume for pos in self.positions.values()
            ),
            "equity_curve": result.equity_curve[-50:] if len(result.equity_curve) > 50 else result.equity_curve,
            "attention_stats": result.attention_stats,
            "use_attention": use_attention
        }
        
        context.metadata["strategy_result"] = report
        
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "报告生成完成", "report": report},
            stage="report"
        )
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report", "report": report},
            stage="report"
        )
        
        print(f"\n✨ [Skill] 策略 '{self.strategy_name}' 执行完成，"
              f"收益率: {result.total_return:.2f}%，"
              f"注意力过滤率: {result.attention_stats.get('filter_ratio', 0):.1%}")
    
    async def _process_frame(self, df: pd.DataFrame, timestamp: float, 
                            max_positions: int, frame_idx: int = 0,
                            attention_min_weight: float = 1.0):
        """处理一帧行情数据（注意力感知版本）"""
        if not isinstance(df, pd.DataFrame):
            return
        
        self.attention_processed_frames += 1
        
        # ========== 关键修改1：使用注意力系统筛选股票 ==========
        if self._use_attention:
            original_count = len(df)
            df = self.filter_by_attention(df, min_weight=attention_min_weight)
            filtered_count = len(df)
            
            self.attention_total_stocks += original_count
            self.attention_filtered_stocks += (original_count - filtered_count)
            
            if frame_idx % 20 == 0:
                print(f"  [注意力过滤] 帧{frame_idx}: {original_count} -> {filtered_count} "
                      f"({(original_count - filtered_count) / original_count:.1%} 被过滤)")
        
        if df is None or df.empty:
            return
        
        # ========== 关键修改2：动态调整阈值 ==========
        buy_threshold, sell_threshold = self.get_dynamic_thresholds()
        
        # 更新持仓价格
        for code, pos in self.positions.items():
            stock_data = df[df['code'] == code]
            if not stock_data.empty:
                pos.current_price = float(stock_data.iloc[0].get('now', stock_data.iloc[0].get('close', pos.buy_price)))
        
        # 检查止损
        codes_to_sell = []
        for code, pos in self.positions.items():
            if pos.profit_pct < sell_threshold * 100:
                codes_to_sell.append(code)
        
        for code in codes_to_sell:
            await self._sell_stock(code, timestamp, f"stop_loss (threshold: {sell_threshold:.2f})")
        
        # 选股买入
        if len(self.positions) < max_positions:
            stock_scores = []
            
            for _, row in df.iterrows():
                code = row.get('code')
                if not code or code in self.positions:
                    continue
                
                # 更新历史
                self.stock_history[code].append({
                    'price': float(row.get('now', row.get('close', 0))),
                    'volume': float(row.get('volume', 0)),
                    'timestamp': timestamp
                })
                
                if len(self.stock_history[code]) > 20:
                    self.stock_history[code] = self.stock_history[code][-20:]
                
                # 提取特征（包含注意力特征）
                features = self.extract_features(code, df)
                if features:
                    score = self.predict_profit(features)
                    
                    # ========== 关键修改3：根据注意力权重调整分数 ==========
                    if self._use_attention:
                        weight = self.get_symbol_attention_weight(code)
                        # 高权重股票获得分数加成
                        score *= (0.8 + weight * 0.2)
                    
                    stock_scores.append((code, score, row))
            
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            
            for code, score, row in stock_scores[:max_positions - len(self.positions)]:
                if score > buy_threshold:
                    # ========== 关键修改4：传入注意力权重 ==========
                    weight = self.get_symbol_attention_weight(code) if self._use_attention else 1.0
                    await self._buy_stock(code, row, timestamp, weight)
        
        # 打印持仓情况
        if frame_idx % 5 == 0 and self.positions:
            print(f"\n  [持仓情况] 帧{frame_idx}, 持仓{len(self.positions)}只, "
                  f"买入阈值: {buy_threshold:.2f}, 止损阈值: {sell_threshold:.2f}")
            total_profit = 0
            for code, pos in sorted(self.positions.items(), key=lambda x: x[1].profit_pct, reverse=True):
                profit_str = f"+{pos.profit_pct:.2f}%" if pos.profit_pct >= 0 else f"{pos.profit_pct:.2f}%"
                attention_info = f"[权重:{pos.attention_weight:.1f}]" if pos.attention_weight > 1.5 else ""
                print(f"    {pos.name}({code}): 成本{pos.buy_price:.2f} 现价{pos.current_price:.2f} "
                      f"{profit_str} {attention_info}")
                total_profit += pos.profit_amount
            print(f"    持仓总盈亏: {total_profit:+.2f}")
    
    async def _buy_stock(self, code: str, row: pd.Series, timestamp: float, attention_weight: float = 1.0):
        """买入股票（增加注意力权重参数）"""
        price = float(row.get('now', row.get('close', 0)))
        name = row.get('name', code)
        
        if price <= 0:
            return
        
        # ========== 关键修改5：根据注意力权重调整仓位 ==========
        # 高注意力股票可以投入更多资金
        position_factor = min(attention_weight, 2.0)  # 最大2倍
        max_investment = self.current_capital * 0.2 * position_factor
        volume = int(max_investment / price / 100) * 100
        
        if volume < 100:
            return
        
        cost = price * volume
        if cost > self.current_capital:
            return
        
        position = StockPosition(
            code=code,
            name=name,
            buy_price=price,
            buy_time=timestamp,
            volume=volume,
            current_price=price,
            attention_weight=attention_weight
        )
        
        self.positions[code] = position
        self.current_capital -= cost
        
        weight_info = f"[权重:{attention_weight:.1f}]" if attention_weight > 1.5 else ""
        print(f"  [买入] {name}({code}) @ {price:.2f} x {volume}股，成本: {cost:.2f} {weight_info}")
    
    async def _sell_stock(self, code: str, timestamp: float, reason: str):
        """卖出股票"""
        if code not in self.positions:
            return
        
        pos = self.positions[code]
        sell_value = pos.current_price * pos.volume
        profit = pos.profit_amount
        profit_pct = pos.profit_pct
        
        self.current_capital += sell_value
        
        trade = {
            'code': code,
            'name': pos.name,
            'buy_price': pos.buy_price,
            'sell_price': pos.current_price,
            'volume': pos.volume,
            'profit': profit,
            'profit_pct': profit_pct,
            'reason': reason,
            'hold_time': timestamp - pos.buy_time,
            'attention_weight': pos.attention_weight
        }
        
        features = self.extract_features(code, pd.DataFrame())
        if features:
            self.update_model(features, profit_pct)
        
        del self.positions[code]
        
        weight_info = f"[权重:{pos.attention_weight:.1f}]" if pos.attention_weight > 1.5 else ""
        print(f"  [卖出] {pos.name}({code}) @ {pos.current_price:.2f}，"
              f"收益: {profit:.2f} ({profit_pct:.2f}%) [{reason}] {weight_info}")


# =============================================================================
# 主程序 - 对比测试
# =============================================================================

async def main():
    """主函数 - 对比有/无注意力的策略效果"""
    
    print("\n" + "="*80)
    print("🚀 实时选股策略 - 注意力系统对比测试")
    print("="*80)
    
    # 测试配置
    test_configs = [
        {
            'name': 'Without_Attention',
            'use_attention': False,
            'description': '不使用注意力系统（基准）'
        },
        {
            'name': 'With_Attention_Low',
            'use_attention': True,
            'attention_min_weight': 1.0,
            'description': '使用注意力系统（最小权重1.0）'
        },
        {
            'name': 'With_Attention_High',
            'use_attention': True,
            'attention_min_weight': 2.0,
            'description': '使用注意力系统（最小权重2.0，更严格）'
        }
    ]
    
    results = []
    
    for config in test_configs:
        print(f"\n{'='*80}")
        print(f"📊 测试: {config['description']}")
        print(f"{'='*80}")
        
        # 创建 Skill
        skill = RealtimeStockPickerSkillWithAttention(f"picker_{config['name']}")
        
        # 模拟执行
        class MockContext:
            def __init__(self):
                self.execution_id = f"test_{config['name']}"
                self.current_stage = ""
                self.metadata = {}
        
        context = MockContext()
        
        input_data = {
            'strategy_name': config['name'],
            'strategy_params': {
                'model_type': 'logistic',
                'learning_rate': 0.01
            },
            'max_positions': 5,
            'replay_rounds': 1,
            'use_attention': config['use_attention'],
            'attention_min_weight': config.get('attention_min_weight', 1.0)
        }
        
        # 收集事件
        events = []
        async for event in skill.execute(input_data, context):
            events.append(event)
            if event.event_type == 'progress':
                print(f"  {event.data.get('message', '')}")
        
        # 提取结果
        for event in reversed(events):
            if event.event_type == 'stage_completed' and event.data.get('report'):
                report = event.data['report']
                results.append({
                    'name': config['name'],
                    'description': config['description'],
                    'return': report.get('total_return', 0),
                    'win_rate': report.get('win_rate', 0),
                    'trades': report.get('trade_count', 0),
                    'attention_stats': report.get('attention_stats', {}),
                    'use_attention': report.get('use_attention', False)
                })
                break
    
    # 显示对比结果
    print("\n" + "="*80)
    print("📈 对比结果")
    print("="*80)
    
    for res in results:
        print(f"\n{res['description']}:")
        print(f"  收益率: {res['return']:.2f}%")
        print(f"  胜率: {res['win_rate']:.1f}%")
        print(f"  交易次数: {res['trades']}")
        
        if res['use_attention']:
            stats = res['attention_stats']
            print(f"  注意力过滤率: {stats.get('filter_ratio', 0):.1%}")
            print(f"  处理帧数: {stats.get('processed_frames', 0)}")
    
    print("\n" + "="*80)
    print("✨ 对比测试完成!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
