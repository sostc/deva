#!/usr/bin/env python
"""
运行策略优化 - 选出最优策略和参数
"""

import asyncio
import time
from typing import AsyncIterator, Any, Dict, List
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd
import numpy as np

# River 在线学习库
from river import linear_model
from river import preprocessing
from river import optim

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
    volume: int = 100
    current_price: float = 0.0
    
    @property
    def profit_pct(self) -> float:
        if self.buy_price == 0:
            return 0.0
        return (self.current_price - self.buy_price) / self.buy_price * 100
    
    @property
    def profit_amount(self) -> float:
        return (self.current_price - self.buy_price) * self.volume


class StockPickerSkill(StreamSkill):
    """选股策略 Skill - 优化版"""
    
    def __init__(self, skill_id: str = "picker"):
        super().__init__(skill_id)
        
        # River 模型
        self.model = None
        self.scaler = preprocessing.StandardScaler()
        
        # 资金和持仓
        self.initial_capital = 100000.0
        self.current_capital = 100000.0
        self.positions: Dict[str, StockPosition] = {}
        
        # 历史数据
        self.stock_history: Dict[str, List[Dict]] = defaultdict(list)
        
        # 交易记录
        self.trades: List[Dict] = []
        
    def init_model(self, model_type: str, learning_rate: float):
        """初始化模型"""
        if model_type == "logistic":
            self.model = linear_model.LogisticRegression(optimizer=optim.SGD(learning_rate))
        elif model_type == "linear":
            self.model = linear_model.LinearRegression(optimizer=optim.SGD(learning_rate))
        else:
            self.model = linear_model.PARegressor()
    
    def extract_features(self, code: str) -> Dict[str, float]:
        """提取特征"""
        history = self.stock_history.get(code, [])
        if len(history) < 3:
            return {}
        
        recent = history[-3:]
        prices = [h['price'] for h in recent]
        volumes = [h['volume'] for h in recent]
        
        return {
            'price_change': (prices[-1] - prices[0]) / prices[0] * 100,
            'volatility': np.std(prices) / np.mean(prices) * 100 if np.mean(prices) > 0 else 0,
            'volume_ratio': volumes[-1] / np.mean(volumes) if np.mean(volumes) > 0 else 1.0,
        }
    
    def predict_score(self, features: Dict[str, float]) -> float:
        """预测得分"""
        if not features or self.model is None:
            return 0.5
        try:
            scaled = self.scaler.learn_one(features).transform_one(features)
            proba = self.model.predict_proba_one(scaled)
            return proba.get(True, 0.5) if isinstance(proba, dict) else 0.5
        except:
            return 0.5
    
    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行策略"""
        strategy_name = input_data.get('strategy_name', 'default')
        params = input_data.get('strategy_params', {})
        
        # 解析参数
        model_type = params.get('model_type', 'logistic')
        learning_rate = params.get('learning_rate', 0.01)
        buy_threshold = params.get('buy_threshold', 0.6)
        sell_threshold = params.get('sell_threshold', -0.05)
        max_positions = params.get('max_positions', 5)
        
        # 初始化
        self.init_model(model_type, learning_rate)
        self.current_capital = self.initial_capital
        self.positions.clear()
        self.stock_history.clear()
        self.trades.clear()
        
        print(f"\n{'='*70}")
        print(f"🚀 启动策略: {strategy_name}")
        print(f"   参数: 模型={model_type}, 学习率={learning_rate}, 买入阈值={buy_threshold}")
        print(f"{'='*70}\n")
        
        # 获取数据
        db = NB("quant_snapshot_5min_window")
        replay_data = list(db.items())
        
        print(f"📊 数据源: {len(replay_data)} 帧数据\n")
        
        # 按时间顺序处理每一帧
        for frame_idx, (timestamp, df) in enumerate(replay_data):
            if not isinstance(df, pd.DataFrame):
                continue
            
            # 更新持仓价格
            for code, pos in self.positions.items():
                stock_data = df[df['code'] == code]
                if not stock_data.empty:
                    pos.current_price = float(stock_data.iloc[0].get('now', pos.buy_price))
            
            # 检查止损
            for code in list(self.positions.keys()):
                pos = self.positions[code]
                if pos.profit_pct < sell_threshold * 100:
                    # 卖出
                    sell_value = pos.current_price * pos.volume
                    profit = pos.profit_amount
                    profit_pct = pos.profit_pct
                    
                    self.current_capital += sell_value
                    
                    # 记录交易
                    self.trades.append({
                        'code': code, 'name': pos.name, 'profit': profit,
                        'profit_pct': profit_pct, 'type': 'sell'
                    })
                    
                    # 在线学习
                    features = self.extract_features(code)
                    if features:
                        scaled = self.scaler.learn_one(features).transform_one(features)
                        self.model.learn_one(scaled, profit > 0)
                    
                    del self.positions[code]
                    
                    print(f"  [卖出] {pos.name}({code}) @ {pos.current_price:.2f} "
                          f"盈亏: {profit:+.2f} ({profit_pct:+.2f}%) [止损]")
            
            # 选股买入
            if len(self.positions) < max_positions:
                candidates = []
                
                for _, row in df.iterrows():
                    code = row.get('code')
                    if not code or code in self.positions:
                        continue
                    
                    # 更新历史
                    price = float(row.get('now', row.get('close', 0)))
                    volume = float(row.get('volume', 0))
                    
                    if price <= 0:
                        continue
                    
                    self.stock_history[code].append({
                        'price': price, 'volume': volume, 'timestamp': timestamp
                    })
                    
                    if len(self.stock_history[code]) > 20:
                        self.stock_history[code] = self.stock_history[code][-20:]
                    
                    # 提取特征并预测
                    features = self.extract_features(code)
                    if features:
                        score = self.predict_score(features)
                        if score > buy_threshold:
                            candidates.append((code, score, row, price))
                
                # 买入得分最高的
                candidates.sort(key=lambda x: x[1], reverse=True)
                
                for code, score, row, price in candidates[:max_positions - len(self.positions)]:
                    name = row.get('name', code)
                    buy_volume = 100
                    cost = price * buy_volume
                    
                    if cost > self.current_capital * 0.2:  # 单只最多20%资金
                        continue
                    
                    # 创建持仓
                    pos = StockPosition(
                        code=code, name=name, buy_price=price,
                        buy_time=timestamp, volume=buy_volume, current_price=price
                    )
                    
                    self.positions[code] = pos
                    self.current_capital -= cost
                    
                    print(f"  [买入] {name}({code}) @ {price:.2f} x {buy_volume}股 "
                          f"成本: {cost:.2f} (得分: {score:.3f})")
            
            # 每10帧打印持仓
            if frame_idx % 10 == 0 and self.positions:
                total_value = self.current_capital + sum(
                    pos.current_price * pos.volume for pos in self.positions.values()
                )
                total_profit = total_value - self.initial_capital
                print(f"\n  [持仓报告] 帧{frame_idx}/{len(replay_data)} "
                      f"总资产: {total_value:.2f} ({total_profit:+.2f})")
                for code, pos in sorted(self.positions.items(), key=lambda x: x[1].profit_pct, reverse=True):
                    profit_str = f"+{pos.profit_pct:.2f}%" if pos.profit_pct >= 0 else f"{pos.profit_pct:.2f}%"
                    print(f"    {pos.name}({code}): {pos.buy_price:.2f}→{pos.current_price:.2f} {profit_str}")
        
        # 计算最终收益
        final_value = self.current_capital + sum(
            pos.current_price * pos.volume for pos in self.positions.values()
        )
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        
        # 生成报告
        report = {
            'strategy_name': strategy_name,
            'params': params,
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'trades_count': len(self.trades),
            'winning_trades': sum(1 for t in self.trades if t.get('profit', 0) > 0),
            'final_positions': len(self.positions)
        }
        
        context.metadata['report'] = report
        
        print(f"\n{'='*70}")
        print(f"✨ 策略 '{strategy_name}' 完成")
        print(f"   初始资金: {self.initial_capital:.2f}")
        print(f"   最终资产: {final_value:.2f}")
        print(f"   总收益率: {total_return:+.2f}%")
        print(f"   交易次数: {len(self.trades)}")
        print(f"{'='*70}\n")
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={'stage': 'trading', 'report': report},
            stage='trading'
        )


async def main():
    """主函数 - 运行多策略优化"""
    
    print("\n" + "="*70)
    print("🚀 实时选股策略优化系统")
    print("="*70)
    
    # 定义要测试的策略配置
    strategies = [
        {
            'name': 'Momentum_v1',
            'params': {
                'model_type': 'logistic',
                'learning_rate': 0.01,
                'buy_threshold': 0.6,
                'sell_threshold': -0.05,
                'max_positions': 5
            }
        },
        {
            'name': 'Momentum_v2_Aggressive',
            'params': {
                'model_type': 'logistic',
                'learning_rate': 0.02,
                'buy_threshold': 0.55,
                'sell_threshold': -0.08,
                'max_positions': 8
            }
        },
        {
            'name': 'Momentum_v3_Conservative',
            'params': {
                'model_type': 'logistic',
                'learning_rate': 0.005,
                'buy_threshold': 0.65,
                'sell_threshold': -0.03,
                'max_positions': 3
            }
        },
        {
            'name': 'Linear_Aggressive',
            'params': {
                'model_type': 'linear',
                'learning_rate': 0.05,
                'buy_threshold': 0.5,
                'sell_threshold': -0.1,
                'max_positions': 10
            }
        },
        {
            'name': 'PA_Adaptive',
            'params': {
                'model_type': 'pa',
                'learning_rate': 0.01,
                'buy_threshold': 0.58,
                'sell_threshold': -0.05,
                'max_positions': 6
            }
        }
    ]
    
    engine = get_execution_engine()
    interface = AgentSkillInterface("optimizer")
    
    results = []
    
    for config in strategies:
        skill_id = f"picker_{config['name']}"
        engine.register_skill(skill_id, StockPickerSkill)
        
        # 运行策略
        result = await interface.invoke_skill(
            skill_id=skill_id,
            input_data={
                'strategy_name': config['name'],
                'strategy_params': config['params']
            }
        )
        
        # 提取结果
        if result.get('success'):
            for event in reversed(result.get('events', [])):
                if event.event_type == 'stage_completed' and event.data.get('report'):
                    report = event.data['report']
                    results.append({
                        'name': config['name'],
                        'params': config['params'],
                        'return': report.get('total_return', 0),
                        'final_value': report.get('final_value', 0),
                        'trades': report.get('trades_count', 0),
                        'winning': report.get('winning_trades', 0)
                    })
                    break
    
    # 显示最终结果
    print("\n" + "="*70)
    print("📊 策略优化结果 - 最终排名")
    print("="*70)
    
    # 按收益率排序
    results.sort(key=lambda x: x['return'], reverse=True)
    
    for i, res in enumerate(results, 1):
        win_rate = (res['winning'] / res['trades'] * 100) if res['trades'] > 0 else 0
        print(f"\n  {i}. {res['name']}")
        print(f"     总收益率: {res['return']:+.2f}%")
        print(f"     最终资产: ¥{res['final_value']:,.2f}")
        print(f"     交易次数: {res['trades']} (胜率: {win_rate:.1f}%)")
        print(f"     参数配置: {res['params']}")
    
    # 选出最优策略
    if results:
        best = results[0]
        print("\n" + "="*70)
        print("🏆 最优策略推荐")
        print("="*70)
        print(f"\n  策略名称: {best['name']}")
        print(f"  总收益率: {best['return']:+.2f}%")
        print(f"  最终资产: ¥{best['final_value']:,.2f}")
        print(f"\n  推荐参数配置:")
        for key, value in best['params'].items():
            print(f"    {key}: {value}")
        print(f"\n  建议使用此策略进行实盘交易!")
    
    print("\n" + "="*70)
    print("✨ 策略优化完成!")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
