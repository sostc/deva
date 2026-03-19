#!/usr/bin/env python
"""
实时选股策略 Skill - 基于 River 在线学习的多轮回放优化系统

架构:
1. 实时接收行情回放数据
2. 使用 River 在线学习模型实时选股
3. 模拟买入并跟踪收益
4. 多轮回放切换不同策略和参数
5. 对比分析选出最优策略
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


@dataclass
class StockPosition:
    """股票持仓"""
    code: str
    name: str
    buy_price: float
    buy_time: float
    volume: int = 100  # 默认买入100股
    current_price: float = 0.0
    
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
    equity_curve: List[Tuple[float, float]] = field(default_factory=list)  # (timestamp, equity)
    
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


class RealtimeStockPickerSkill(StreamSkill):
    """
    实时选股策略 Skill
    
    功能:
    1. 实时接收行情数据流
    2. 使用 River 在线学习模型选股
    3. 模拟交易并计算收益
    4. 支持多策略切换和参数优化
    """
    
    def __init__(self, skill_id: str = "realtime_stock_picker"):
        super().__init__(skill_id)
        
        # 策略配置
        self.strategy_name = ""
        self.strategy_params = {}
        
        # River 模型
        self.model = None
        self.scaler = preprocessing.StandardScaler()
        
        # 持仓和交易
        self.positions: Dict[str, StockPosition] = {}
        self.initial_capital = 100000.0  # 初始资金10万
        self.current_capital = 100000.0
        
        # 特征工程
        self.feature_window = 5  # 特征窗口
        self.stock_history: Dict[str, List[Dict]] = defaultdict(list)
        
        # 选股阈值
        self.buy_threshold = 0.6  # 买入信号阈值
        self.sell_threshold = -0.1  # 卖出信号阈值（亏损10%止损）
        
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
        """提取股票特征"""
        history = self.stock_history.get(stock_code, [])
        
        if len(history) < self.feature_window:
            return {}
        
        # 获取最近 N 条数据
        recent = history[-self.feature_window:]
        
        prices = [h['price'] for h in recent]
        volumes = [h['volume'] for h in recent]
        
        # 计算技术指标
        features = {
            'price_change_pct': (prices[-1] - prices[0]) / prices[0] * 100,
            'volatility': np.std(prices) / np.mean(prices) * 100,
            'volume_ratio': volumes[-1] / np.mean(volumes) if np.mean(volumes) > 0 else 1.0,
            'price_momentum': (prices[-1] - prices[-2]) / prices[-2] * 100 if len(prices) >= 2 else 0,
            'high_low_range': (max(prices) - min(prices)) / np.mean(prices) * 100,
        }
        
        return features
    
    def predict_profit(self, features: Dict[str, float]) -> float:
        """预测收益概率"""
        if self.model is None or not features:
            return 0.5
        
        try:
            # 标准化特征
            scaled_features = self.scaler.learn_one(features).transform_one(features)
            
            # 预测
            prediction = self.model.predict_one(scaled_features)
            
            # 对于分类模型，返回概率
            if hasattr(self.model, 'predict_proba_one'):
                proba = self.model.predict_proba_one(scaled_features)
                return proba.get(True, 0.5) if isinstance(proba, dict) else 0.5
            
            # 对于回归模型，将预测值映射到 0-1
            return min(max(prediction / 10.0 + 0.5, 0), 1)  # 假设预测值范围 -10 到 10
            
        except Exception as e:
            return 0.5
    
    def update_model(self, features: Dict[str, float], actual_return: float):
        """在线更新模型"""
        if self.model is None or not features:
            return
        
        try:
            # 标准化特征
            scaled_features = self.scaler.learn_one(features).transform_one(features)
            
            # 标签：收益 > 0 为 True
            label = actual_return > 0
            
            # 在线学习
            self.model.learn_one(scaled_features, label)
            
        except Exception as e:
            pass
    
    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """
        执行实时选股策略
        
        input_data: {
            'strategy_name': '策略名称',
            'strategy_params': {'param1': value1, ...},
            'max_positions': 5,  # 最大持仓数
            'replay_rounds': 3,  # 回放轮数
        }
        """
        # 解析输入参数
        self.strategy_name = input_data.get('strategy_name', 'default')
        self.strategy_params = input_data.get('strategy_params', {})
        max_positions = input_data.get('max_positions', 5)
        replay_rounds = input_data.get('replay_rounds', 1)
        
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
            data={"stage": "initialization", "strategy": self.strategy_name},
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
                "message": f"初始化完成，数据源有 {len(replay_data)} 条记录"
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
            
            # 重置资金（每轮重新开始）
            self.current_capital = self.initial_capital
            self.positions.clear()
            self.stock_history.clear()
            
            # 处理每一帧数据
            total_frames = len(replay_data)
            for i, (timestamp, df) in enumerate(replay_data):
                # 检查控制消息
                if not self._pause_event.is_set():
                    await self._pause_event.wait()
                
                if self._state.value in ("cancelled", "failed"):
                    return
                
                # 更新进度
                progress = 10 + int((round_num * total_frames + i) / (replay_rounds * total_frames) * 70)
                
                if i % 10 == 0:  # 每10帧报告一次
                    yield SkillEvent(
                        event_type="progress",
                        timestamp=time.time(),
                        execution_id=context.execution_id,
                        data={
                            "progress": progress,
                            "message": f"第 {round_num + 1}/{replay_rounds} 轮，处理 {i}/{total_frames} 帧",
                            "round": round_num + 1,
                            "frame": i,
                            "capital": self.current_capital,
                            "positions": len(self.positions)
                        },
                        stage=f"training_round_{round_num + 1}"
                    )
                
                # 处理这一帧数据（按顺序处理，传入帧索引）
                await self._process_frame(df, timestamp, max_positions, i)
                
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
            
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "progress": 10 + int((round_num + 1) / replay_rounds * 70),
                    "message": f"第 {round_num + 1} 轮完成，收益率: {round_return:.2f}%",
                    "round": round_num + 1,
                    "round_return": round_return
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
            
            # 保存本轮结果
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
        
        # 生成最终报告
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
            "equity_curve": result.equity_curve[-50:] if len(result.equity_curve) > 50 else result.equity_curve
        }
        
        # 保存到 metadata
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
        
        print(f"\n✨ [Skill] 策略 '{self.strategy_name}' 执行完成，收益率: {result.total_return:.2f}%")
    
    async def _process_frame(self, df: pd.DataFrame, timestamp: float, max_positions: int, frame_idx: int = 0):
        """处理一帧行情数据"""
        if not isinstance(df, pd.DataFrame):
            return
        
        # 更新持仓价格
        for code, pos in self.positions.items():
            stock_data = df[df['code'] == code]
            if not stock_data.empty:
                pos.current_price = float(stock_data.iloc[0].get('now', stock_data.iloc[0].get('close', pos.buy_price)))
        
        # 检查止损
        codes_to_sell = []
        for code, pos in self.positions.items():
            if pos.profit_pct < self.sell_threshold * 100:  # 止损
                codes_to_sell.append(code)
        
        # 执行卖出
        for code in codes_to_sell:
            await self._sell_stock(code, timestamp, "stop_loss")
        
        # 选股买入
        if len(self.positions) < max_positions:
            # 计算每只股票得分
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
                
                # 限制历史长度
                if len(self.stock_history[code]) > 20:
                    self.stock_history[code] = self.stock_history[code][-20:]
                
                # 提取特征并预测
                features = self.extract_features(code, df)
                if features:
                    score = self.predict_profit(features)
                    stock_scores.append((code, score, row))
            
            # 买入得分最高的股票
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            
            for code, score, row in stock_scores[:max_positions - len(self.positions)]:
                if score > self.buy_threshold:
                    await self._buy_stock(code, row, timestamp)
        
        # 每5帧打印持仓情况
        if frame_idx % 5 == 0 and self.positions:
            print(f"\n  [持仓情况] 帧{frame_idx}, 持仓{len(self.positions)}只:")
            total_profit = 0
            for code, pos in sorted(self.positions.items(), key=lambda x: x[1].profit_pct, reverse=True):
                profit_str = f"+{pos.profit_pct:.2f}%" if pos.profit_pct >= 0 else f"{pos.profit_pct:.2f}%"
                print(f"    {pos.name}({code}): 成本{pos.buy_price:.2f} 现价{pos.current_price:.2f} {profit_str}")
                total_profit += pos.profit_amount
            print(f"    持仓总盈亏: {total_profit:+.2f}")
    
    async def _buy_stock(self, code: str, row: pd.Series, timestamp: float):
        """买入股票"""
        price = float(row.get('now', row.get('close', 0)))
        name = row.get('name', code)
        
        if price <= 0:
            return
        
        # 计算买入数量（每只股票最多投入 20% 资金）
        max_investment = self.current_capital * 0.2
        volume = int(max_investment / price / 100) * 100  # 整手买入
        
        if volume < 100:
            return
        
        cost = price * volume
        if cost > self.current_capital:
            return
        
        # 创建持仓
        position = StockPosition(
            code=code,
            name=name,
            buy_price=price,
            buy_time=timestamp,
            volume=volume,
            current_price=price
        )
        
        self.positions[code] = position
        self.current_capital -= cost
        
        print(f"  [买入] {name}({code}) @ {price:.2f} x {volume}股，成本: {cost:.2f}")
    
    async def _sell_stock(self, code: str, timestamp: float, reason: str):
        """卖出股票"""
        if code not in self.positions:
            return
        
        pos = self.positions[code]
        sell_value = pos.current_price * pos.volume
        profit = pos.profit_amount
        profit_pct = pos.profit_pct
        
        # 更新资金
        self.current_capital += sell_value
        
        # 记录交易
        trade = {
            'code': code,
            'name': pos.name,
            'buy_price': pos.buy_price,
            'sell_price': pos.current_price,
            'volume': pos.volume,
            'profit': profit,
            'profit_pct': profit_pct,
            'reason': reason,
            'hold_time': timestamp - pos.buy_time
        }
        
        # 更新模型（用实际收益作为标签）
        features = self.extract_features(code, pd.DataFrame())
        if features:
            self.update_model(features, profit_pct)
        
        del self.positions[code]
        
        print(f"  [卖出] {pos.name}({code}) @ {pos.current_price:.2f}，收益: {profit:.2f} ({profit_pct:.2f}%) [{reason}]")


# =============================================================================
# 策略优化器 - 多策略对比
# =============================================================================

class StrategyOptimizer:
    """策略优化器 - 运行多个策略并选出最优"""
    
    def __init__(self):
        self.results: List[Dict] = []
    
    async def run_optimization(
        self,
        strategy_configs: List[Dict],
        replay_rounds: int = 2
    ) -> Dict:
        """
        运行多策略优化
        
        strategy_configs: [
            {'name': '策略1', 'params': {...}},
            {'name': '策略2', 'params': {...}},
            ...
        ]
        """
        engine = get_execution_engine()
        interface = AgentSkillInterface("optimizer")
        
        print("\n" + "="*70)
        print("🚀 开始多策略优化")
        print("="*70)
        
        for config in strategy_configs:
            skill_id = f"picker_{config['name']}"
            
            # 注册 Skill
            engine.register_skill(skill_id, RealtimeStockPickerSkill)
            
            print(f"\n📊 测试策略: {config['name']}")
            print(f"   参数: {config['params']}")
            
            # 运行策略
            result = await interface.invoke_skill(
                skill_id=skill_id,
                input_data={
                    'strategy_name': config['name'],
                    'strategy_params': config['params'],
                    'max_positions': 5,
                    'replay_rounds': replay_rounds
                }
            )
            
            # 提取结果
            if result.get('success'):
                events = result.get('events', [])
                for event in reversed(events):
                    if event.event_type == 'progress' and event.data.get('report'):
                        report = event.data['report']
                        self.results.append({
                            'name': config['name'],
                            'params': config['params'],
                            'return': report.get('total_return', 0),
                            'win_rate': report.get('win_rate', 0),
                            'max_drawdown': report.get('max_drawdown', 0),
                            'trades': report.get('trade_count', 0)
                        })
                        break
        
        # 排序并选出最优
        self.results.sort(key=lambda x: x['return'], reverse=True)
        
        return {
            'best_strategy': self.results[0] if self.results else None,
            'all_results': self.results
        }


# =============================================================================
# 主程序
# =============================================================================

async def main():
    """主函数 - 运行策略优化"""
    
    # 定义要测试的策略配置
    strategy_configs = [
        {
            'name': 'Momentum_Learning',
            'params': {
                'model_type': 'logistic',
                'learning_rate': 0.01,
                'buy_threshold': 0.6,
                'sell_threshold': -0.05
            }
        },
        {
            'name': 'Aggressive_Picker',
            'params': {
                'model_type': 'linear',
                'learning_rate': 0.05,
                'buy_threshold': 0.5,
                'sell_threshold': -0.08
            }
        },
        {
            'name': 'Conservative_Picker',
            'params': {
                'model_type': 'logistic',
                'learning_rate': 0.005,
                'buy_threshold': 0.7,
                'sell_threshold': -0.03
            }
        },
        {
            'name': 'Passive_Aggressive',
            'params': {
                'model_type': 'pa',
                'learning_rate': 0.01,
                'buy_threshold': 0.55,
                'sell_threshold': -0.05
            }
        }
    ]
    
    # 运行优化
    optimizer = StrategyOptimizer()
    optimization_result = await optimizer.run_optimization(
        strategy_configs=strategy_configs,
        replay_rounds=2  # 每策略回放2轮
    )
    
    # 显示结果
    print("\n" + "="*70)
    print("📊 策略优化结果")
    print("="*70)
    
    print("\n【所有策略排名】")
    for i, res in enumerate(optimization_result['all_results'], 1):
        print(f"\n  {i}. {res['name']}")
        print(f"     收益率: {res['return']:.2f}%")
        print(f"     胜率: {res['win_rate']:.1f}%")
        print(f"     最大回撤: {res['max_drawdown']:.2f}%")
        print(f"     交易次数: {res['trades']}")
    
    best = optimization_result['best_strategy']
    if best:
        print("\n" + "="*70)
        print("🏆 最优策略")
        print("="*70)
        print(f"\n  策略名称: {best['name']}")
        print(f"  收益率: {best['return']:.2f}%")
        print(f"  参数配置: {best['params']}")
    
    print("\n" + "="*70)
    print("✨ 优化完成!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
