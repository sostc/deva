#!/usr/bin/env python
"""
智能选股策略系统 v2.0 - 完整集成版
整合所有改进模块：特征工程、模型预热、集成学习、风险管理、多策略
"""

import asyncio
import time
from typing import AsyncIterator, Any, Dict, List
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd
import numpy as np

from deva.naja.stream_skill import (
    StreamSkill,
    SkillContext,
    SkillEvent,
    get_execution_engine,
    AgentSkillInterface,
)
from deva import NB

# 导入自定义模块
from feature_engineering import FeatureExtractor, MarketSentimentCalculator
from model_warmup import ModelWarmUpStrategy, AdaptiveThresholdManager
from ensemble_model import AdaptiveEnsembleModel
from risk_manager import RiskManager, Position
from strategy_pool import StrategyPool, MarketStateDetector


@dataclass
class StockPosition:
    """股票持仓"""
    code: str
    name: str
    buy_price: float
    buy_time: float
    volume: int = 100
    current_price: float = 0.0
    blocks: List[str] = field(default_factory=list)
    
    @property
    def profit_pct(self) -> float:
        if self.buy_price == 0:
            return 0.0
        return (self.current_price - self.buy_price) / self.buy_price * 100
    
    @property
    def profit_amount(self) -> float:
        return (self.current_price - self.buy_price) * self.volume


class IntegratedStrategyV2(StreamSkill):
    """
    智能选股策略 v2.0 - 完整版
    
    功能：
    1. 丰富的特征工程（技术指标+板块特征+市场情绪）
    2. 模型预热策略（解决初始预测得分低的问题）
    3. 集成学习模型（Logistic+决策树+随机森林）
    4. 完整风险管理（Kelly仓位+止盈止损+回撤控制）
    5. 多策略动态切换（趋势+均值回归+动量+板块轮动）
    """
    
    def __init__(self, skill_id: str = "integrated_v2"):
        super().__init__(skill_id)
        
        # 初始化所有模块
        self.feature_extractor = FeatureExtractor()
        self.sentiment_calculator = MarketSentimentCalculator()
        self.warmup_strategy = ModelWarmUpStrategy()
        self.ensemble_model = AdaptiveEnsembleModel()
        self.risk_manager = RiskManager()
        self.strategy_pool = StrategyPool()
        self.market_detector = MarketStateDetector()
        
        # 资金和持仓
        self.initial_capital = 100000.0
        self.current_capital = 100000.0
        self.positions: Dict[str, StockPosition] = {}
        
        # 统计
        self.trades: List[Dict] = []
        self.signals_generated = 0
        
    def initialize(self, params: Dict[str, Any]):
        """初始化策略参数"""
        # 配置模型预热
        warmup_periods = params.get('warmup_periods', 50)
        self.warmup_strategy = ModelWarmUpStrategy(
            warm_up_periods=warmup_periods
        )
        
        # 配置风险管理
        max_position = params.get('max_position_pct', 0.15)
        stop_loss = params.get('stop_loss', -0.08)
        self.risk_manager = RiskManager(
            max_position_pct=max_position,
            initial_stop=stop_loss
        )
    
    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行策略"""
        strategy_name = input_data.get('strategy_name', 'IntegratedV2')
        params = input_data.get('strategy_params', {})
        
        # 初始化
        self.initialize(params)
        self.current_capital = self.initial_capital
        self.positions.clear()
        self.trades.clear()
        
        print(f"\n{'='*70}")
        print(f"🚀 启动智能选股策略 v2.0: {strategy_name}")
        print(f"{'='*70}\n")
        
        # 加载板块数据
        print("[初始化] 加载板块数据...")
        self.feature_extractor.load_block_data(
            "/Users/spark/pycharmproject/deva/deva/naja/dictionary/infoharbor_block.dat"
        )
        
        # 获取行情数据
        db = NB("quant_snapshot_5min_window")
        replay_data = list(db.items())
        print(f"[初始化] 行情数据: {len(replay_data)} 帧\n")
        
        buy_count = 0
        sell_count = 0
        
        # 按时间顺序处理
        for frame_idx, (timestamp, df) in enumerate(replay_data):
            if not isinstance(df, pd.DataFrame):
                continue
            
            # 1. 更新市场情绪
            self.sentiment_calculator.update_market_data(df)
            sentiment_features = self.sentiment_calculator.get_sentiment_features()
            
            # 2. 检测市场状态并选择策略
            self.market_detector.update(sentiment_features)
            market_state = self.market_detector.detect_state()
            current_strategy = self.strategy_pool.select_strategy(market_state)
            
            # 3. 更新持仓价格
            for code, pos in self.positions.items():
                stock_data = df[df['code'] == code]
                if not stock_data.empty:
                    pos.current_price = float(stock_data.iloc[0].get('now', pos.buy_price))
            
            # 4. 检查风险（止损、止盈、回撤）
            total_value = self.current_capital + sum(
                pos.current_price * pos.volume for pos in self.positions.values()
            )
            
            for code in list(self.positions.keys()):
                pos = self.positions[code]
                
                # 创建风险管理的Position对象
                risk_position = Position(
                    code=pos.code,
                    name=pos.name,
                    buy_price=pos.buy_price,
                    volume=pos.volume,
                    current_price=pos.current_price
                )
                
                # 检查风险
                risk_signals = self.risk_manager.check_risk(risk_position, total_value)
                
                for signal in risk_signals:
                    if signal['action'] in ['SELL', 'PARTIAL_SELL']:
                        # 执行卖出
                        sell_value = pos.current_price * pos.volume
                        profit = pos.profit_amount
                        profit_pct = pos.profit_pct
                        
                        self.current_capital += sell_value
                        
                        # 记录交易
                        self.trades.append({
                            'code': code,
                            'profit': profit,
                            'type': 'sell'
                        })
                        
                        # 在线学习
                        features = self.feature_extractor.extract_all_features(
                            code, pos.current_price, 0, df
                        )
                        if features:
                            self.ensemble_model.learn(features, profit > 0)
                            self.ensemble_model.update_weights(profit > 0)
                        
                        # 更新模型预热
                        self.warmup_strategy.update(profit)
                        
                        # 记录策略表现
                        self.strategy_pool.record_performance(
                            self.strategy_pool.current_strategy, profit
                        )
                        
                        del self.positions[code]
                        sell_count += 1
                        
                        print(f"  [卖出] {pos.name}({code}) @ {pos.current_price:.2f} "
                              f"盈亏: {profit:+.2f} ({profit_pct:+.2f}%) [{signal['reason']}]")
            
            # 5. 选股买入
            # 获取当前动态阈值
            buy_threshold = self.warmup_strategy.get_buy_threshold()
            max_positions = params.get('max_positions', 8)
            
            if len(self.positions) < max_positions:
                candidates = []
                
                for _, row in df.iterrows():
                    code = row.get('code')
                    name = row.get('name', code)
                    
                    if not code or code in self.positions:
                        continue
                    
                    price = float(row.get('now', row.get('close', 0)))
                    volume = float(row.get('volume', 0))
                    
                    if price <= 0:
                        continue
                    
                    # 更新历史数据
                    self.feature_extractor.update_history(
                        code, price, volume, 
                        row.get('high', price), row.get('low', price)
                    )
                    
                    # 提取特征
                    features = self.feature_extractor.extract_all_features(
                        code, price, volume, df
                    )
                    
                    if features:
                        # 使用集成模型预测
                        score = self.ensemble_model.predict_proba(features)
                        
                        # 结合策略信号
                        strategy_signal = current_strategy.should_buy(features)
                        
                        # 综合得分（模型预测 + 策略信号）
                        final_score = score * 0.7 + (0.6 if strategy_signal else 0.4) * 0.3
                        
                        blocks = self.feature_extractor.stock_blocks.get(code, [])
                        
                        if final_score > buy_threshold:
                            candidates.append((code, name, final_score, price, blocks))
                
                # 买入得分最高的
                candidates.sort(key=lambda x: x[2], reverse=True)
                
                for code, name, score, price, blocks in candidates[:max_positions - len(self.positions)]:
                    # 使用Kelly公式计算仓位
                    shares = self.risk_manager.calculate_position(
                        code, score, self.current_capital
                    )
                    
                    cost = price * shares
                    
                    if cost > self.current_capital * 0.2:  # 单只最多20%
                        continue
                    
                    # 创建持仓
                    pos = StockPosition(
                        code=code,
                        name=name,
                        buy_price=price,
                        buy_time=timestamp,
                        volume=shares,
                        current_price=price,
                        blocks=blocks
                    )
                    
                    self.positions[code] = pos
                    self.current_capital -= cost
                    buy_count += 1
                    
                    blocks_str = ', '.join(blocks[:2]) if blocks else '无'
                    print(f"  [买入] {name}({code}) @ {price:.2f} x {shares}股 "
                          f"成本: {cost:.2f} (得分: {score:.3f}) [{blocks_str}]")
            
            # 6. 定期报告
            if frame_idx % 20 == 0 and self.positions:
                total_value = self.current_capital + sum(
                    pos.current_price * pos.volume for pos in self.positions.values()
                )
                total_profit = total_value - self.initial_capital
                
                print(f"\n  [持仓报告] 帧{frame_idx}/{len(replay_data)} "
                      f"市场状态: {market_state} 策略: {current_strategy.name}")
                print(f"    总资产: ¥{total_value:,.2f} ({total_profit:+.2f}) "
                      f"持仓: {len(self.positions)}只")
                
                # 显示前3只持仓
                for code, pos in sorted(self.positions.items(), 
                                       key=lambda x: x[1].profit_pct, reverse=True)[:3]:
                    profit_str = f"+{pos.profit_pct:.2f}%" if pos.profit_pct >= 0 else f"{pos.profit_pct:.2f}%"
                    print(f"    {pos.name}: {profit_str}")
        
        # 计算最终收益
        final_value = self.current_capital + sum(
            pos.current_price * pos.volume for pos in self.positions.values()
        )
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        
        winning_trades = sum(1 for t in self.trades if t.get('profit', 0) > 0)
        
        report = {
            'strategy_name': strategy_name,
            'params': params,
            'total_return': total_return,
            'final_value': final_value,
            'buy_count': buy_count,
            'sell_count': sell_count,
            'winning_trades': winning_trades,
            'risk_report': self.risk_manager.get_risk_report(),
        }
        
        context.metadata['report'] = report
        
        print(f"\n{'='*70}")
        print(f"✨ 策略 '{strategy_name}' 完成")
        print(f"   初始资金: ¥{self.initial_capital:,.2f}")
        print(f"   最终资产: ¥{final_value:,.2f}")
        print(f"   总收益率: {total_return:+.2f}%")
        print(f"   买入: {buy_count}次 | 卖出: {sell_count}次")
        print(f"   胜率: {winning_trades}/{len(self.trades)}")
        print(f"{'='*70}\n")
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={'stage': 'trading', 'report': report},
            stage='trading'
        )


async def main():
    """主函数 - 运行策略对比"""
    
    print("\n" + "="*70)
    print("🚀 智能选股策略系统 v2.0 - 集成测试")
    print("="*70)
    
    # 定义测试配置
    strategies = [
        {
            'name': 'V2_标准版',
            'params': {
                'warmup_periods': 50,
                'max_position_pct': 0.15,
                'stop_loss': -0.08,
                'max_positions': 8,
            }
        },
        {
            'name': 'V2_激进版',
            'params': {
                'warmup_periods': 30,
                'max_position_pct': 0.20,
                'stop_loss': -0.10,
                'max_positions': 12,
            }
        },
        {
            'name': 'V2_保守版',
            'params': {
                'warmup_periods': 80,
                'max_position_pct': 0.10,
                'stop_loss': -0.05,
                'max_positions': 5,
            }
        }
    ]
    
    engine = get_execution_engine()
    interface = AgentSkillInterface("optimizer")
    
    results = []
    
    for config in strategies:
        skill_id = f"v2_{config['name']}"
        engine.register_skill(skill_id, IntegratedStrategyV2)
        
        print(f"\n{'='*70}")
        print(f"📊 测试策略: {config['name']}")
        print(f"{'='*70}")
        
        result = await interface.invoke_skill(
            skill_id=skill_id,
            input_data={
                'strategy_name': config['name'],
                'strategy_params': config['params']
            }
        )
        
        if result.get('success'):
            for event in reversed(result.get('events', [])):
                if event.event_type == 'stage_completed' and event.data.get('report'):
                    report = event.data['report']
                    results.append({
                        'name': config['name'],
                        'params': config['params'],
                        'return': report.get('total_return', 0),
                        'final_value': report.get('final_value', 0),
                        'buy_count': report.get('buy_count', 0),
                        'sell_count': report.get('sell_count', 0),
                        'winning': report.get('winning_trades', 0),
                    })
                    break
    
    # 显示最终结果
    print("\n" + "="*70)
    print("📊 策略优化结果 - 最终排名")
    print("="*70)
    
    results.sort(key=lambda x: x['return'], reverse=True)
    
    for i, res in enumerate(results, 1):
        win_rate = (res['winning'] / res['sell_count'] * 100) if res['sell_count'] > 0 else 0
        print(f"\n  {i}. {res['name']}")
        print(f"     总收益率: {res['return']:+.2f}%")
        print(f"     最终资产: ¥{res['final_value']:,.2f}")
        print(f"     交易: 买{res['buy_count']}次 / 卖{res['sell_count']}次")
        print(f"     胜率: {win_rate:.1f}%")
    
    if results:
        best = results[0]
        print("\n" + "="*70)
        print("🏆 最优策略推荐")
        print("="*70)
        print(f"\n  策略: {best['name']}")
        print(f"  收益率: {best['return']:+.2f}%")
        print(f"\n  参数配置:")
        for key, value in best['params'].items():
            print(f"    • {key}: {value}")
    
    print("\n" + "="*70)
    print("✨ 集成策略系统 v2.0 测试完成!")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
