#!/usr/bin/env python
"""
简化版板块增强策略 - 确保产生交易
"""

import asyncio
import time
from typing import AsyncIterator, Any, Dict, List
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd
import numpy as np

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
    code: str
    name: str
    buy_price: float
    volume: int
    current_price: float = 0.0
    blocks: List[str] = field(default_factory=list)
    
    @property
    def profit_pct(self) -> float:
        if self.buy_price == 0:
            return 0.0
        return (self.current_price - self.buy_price) / self.buy_price * 100


class SimpleBlockStrategy(StreamSkill):
    def __init__(self, skill_id: str = "simple_block"):
        super().__init__(skill_id)
        self.stock_blocks: Dict[str, List[str]] = {}
        self.model = None
        self.scaler = preprocessing.StandardScaler()
        self.initial_capital = 100000.0
        self.current_capital = 100000.0
        self.positions: Dict[str, StockPosition] = {}
        self.stock_history: Dict[str, List[Dict]] = defaultdict(list)
        self.trades: List[Dict] = []
        
    def load_block_data(self):
        """加载板块数据"""
        print("  [数据加载] 加载通达信概念板块数据...")
        
        try:
            with open("/Users/spark/pycharmproject/deva/deva/naja/dictionary/infoharbor_block.dat", 
                      'r', encoding='gb2312', errors='ignore') as f:
                content = f.read()
            
            lines = content.split('\n')
            current_block = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith('#'):
                    current_block = line[1:].split(',')[0].strip()
                elif current_block:
                    stocks = line.split(',')
                    for stock in stocks:
                        stock = stock.strip()
                        if stock and '#' in stock:
                            code = stock.split('#')[1]
                            if code not in self.stock_blocks:
                                self.stock_blocks[code] = []
                            if current_block not in self.stock_blocks[code]:
                                self.stock_blocks[code].append(current_block)
            
            print(f"  [数据加载] 成功: {len(self.stock_blocks)} 只股票有关联板块")
            
        except Exception as e:
            print(f"  [数据加载] 失败: {e}")
    
    def init_model(self, learning_rate: float):
        self.model = linear_model.LogisticRegression(optimizer=optim.SGD(learning_rate))
    
    def extract_features(self, code: str) -> Dict[str, float]:
        history = self.stock_history.get(code, [])
        if len(history) < 2:
            return {}
        
        recent = history[-2:]
        prices = [h['price'] for h in recent]
        volumes = [h['volume'] for h in recent]
        
        return {
            'price_change': (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] > 0 else 0,
            'volume_ratio': volumes[-1] / volumes[0] if volumes[0] > 0 else 1.0,
            'block_count': len(self.stock_blocks.get(code, [])),
        }
    
    def predict_score(self, features: Dict[str, float]) -> float:
        if not features or self.model is None:
            return 0.5
        try:
            scaled = self.scaler.learn_one(features).transform_one(features)
            proba = self.model.predict_proba_one(scaled)
            return proba.get(True, 0.5) if isinstance(proba, dict) else 0.5
        except:
            return 0.5
    
    def update_model(self, features: Dict[str, float], profit: float):
        if self.model is None or not features:
            return
        try:
            scaled = self.scaler.learn_one(features).transform_one(features)
            self.model.learn_one(scaled, profit > 0)
        except:
            pass
    
    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        strategy_name = input_data.get('strategy_name', 'default')
        params = input_data.get('strategy_params', {})
        
        learning_rate = params.get('learning_rate', 0.01)
        buy_threshold = params.get('buy_threshold', 0.50)  # 很低
        sell_threshold = params.get('sell_threshold', -0.10)  # 宽松
        max_positions = params.get('max_positions', 10)
        
        self.init_model(learning_rate)
        self.current_capital = self.initial_capital
        self.positions.clear()
        self.stock_history.clear()
        self.trades.clear()
        self.stock_blocks.clear()
        
        print(f"\n{'='*70}")
        print(f"🚀 启动策略: {strategy_name}")
        print(f"   买入阈值={buy_threshold}, 止损={sell_threshold*100:.1f}%, 最大持仓={max_positions}")
        print(f"{'='*70}\n")
        
        self.load_block_data()
        
        db = NB("quant_snapshot_5min_window")
        replay_data = list(db.items())
        
        print(f"📊 行情数据: {len(replay_data)} 帧\n")
        
        buy_count = 0
        sell_count = 0
        
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
                    sell_value = pos.current_price * pos.volume
                    profit = (pos.current_price - pos.buy_price) * pos.volume
                    profit_pct = pos.profit_pct
                    
                    self.current_capital += sell_value
                    self.trades.append({'profit': profit})
                    
                    features = self.extract_features(code)
                    if features:
                        self.update_model(features, profit_pct)
                    
                    blocks_str = ', '.join(pos.blocks[:2]) if pos.blocks else '无'
                    print(f"  [卖出] {pos.name}({code}) @ {pos.current_price:.2f} "
                          f"盈亏: {profit_pct:+.2f}% [{blocks_str}]")
                    
                    del self.positions[code]
                    sell_count += 1
            
            # 选股买入
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
                    
                    self.stock_history[code].append({'price': price, 'volume': volume})
                    if len(self.stock_history[code]) > 10:
                        self.stock_history[code] = self.stock_history[code][-10:]
                    
                    if len(self.stock_history[code]) >= 2:
                        features = self.extract_features(code)
                        if features:
                            score = self.predict_score(features)
                            blocks = self.stock_blocks.get(code, [])
                            if score > buy_threshold:
                                candidates.append((code, name, score, price, blocks))
                        else:
                            blocks = self.stock_blocks.get(code, [])
                            if blocks:
                                candidates.append((code, name, 0.51, price, blocks))
                
                candidates.sort(key=lambda x: x[2], reverse=True)
                
                for code, name, score, price, blocks in candidates[:max_positions - len(self.positions)]:
                    buy_volume = 100
                    cost = price * buy_volume
                    
                    if cost > self.current_capital * 0.12:
                        continue
                    
                    pos = StockPosition(
                        code=code, name=name, buy_price=price,
                        volume=buy_volume, current_price=price, blocks=blocks
                    )
                    
                    self.positions[code] = pos
                    self.current_capital -= cost
                    buy_count += 1
                    
                    blocks_str = ', '.join(blocks[:2]) if blocks else '无'
                    print(f"  [买入] {name}({code}) @ {price:.2f} x {buy_volume}股 "
                          f"(得分: {score:.3f}) [{blocks_str}]")
            
            # 每20帧打印持仓
            if frame_idx % 20 == 0 and self.positions:
                total_value = self.current_capital + sum(
                    pos.current_price * pos.volume for pos in self.positions.values()
                )
                print(f"\n  [持仓] 帧{frame_idx} 总资产: ¥{total_value:,.2f} 持仓{len(self.positions)}只")
                for code, pos in sorted(self.positions.items(), key=lambda x: x[1].profit_pct, reverse=True)[:5]:
                    profit_str = f"+{pos.profit_pct:.2f}%" if pos.profit_pct >= 0 else f"{pos.profit_pct:.2f}%"
                    print(f"    {pos.name}: {profit_str}")
        
        final_value = self.current_capital + sum(
            pos.current_price * pos.volume for pos in self.positions.values()
        )
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        
        winning = sum(1 for t in self.trades if t.get('profit', 0) > 0)
        
        report = {
            'strategy_name': strategy_name,
            'params': params,
            'total_return': total_return,
            'final_value': final_value,
            'buy_count': buy_count,
            'sell_count': sell_count,
            'winning_trades': winning,
        }
        
        context.metadata['report'] = report
        
        print(f"\n{'='*70}")
        print(f"✨ {strategy_name} 完成")
        print(f"   收益率: {total_return:+.2f}% | 买入: {buy_count}次 | 卖出: {sell_count}次")
        print(f"{'='*70}\n")
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={'stage': 'trading', 'report': report},
            stage='trading'
        )


async def main():
    print("\n" + "="*70)
    print("🚀 板块增强策略优化")
    print("="*70)
    
    strategies = [
        {
            'name': '策略1_超激进',
            'params': {
                'learning_rate': 0.03,
                'buy_threshold': 0.48,  # 很低
                'sell_threshold': -0.12,  # 很宽松
                'max_positions': 12
            }
        },
        {
            'name': '策略2_激进',
            'params': {
                'learning_rate': 0.02,
                'buy_threshold': 0.50,
                'sell_threshold': -0.10,
                'max_positions': 10
            }
        },
        {
            'name': '策略3_平衡',
            'params': {
                'learning_rate': 0.01,
                'buy_threshold': 0.52,
                'sell_threshold': -0.08,
                'max_positions': 8
            }
        }
    ]
    
    engine = get_execution_engine()
    interface = AgentSkillInterface("optimizer")
    
    results = []
    
    for config in strategies:
        skill_id = f"block_{config['name']}"
        engine.register_skill(skill_id, SimpleBlockStrategy)
        
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
                    results.append({
                        'name': config['name'],
                        'params': config['params'],
                        **event.data['report']
                    })
                    break
    
    print("\n" + "="*70)
    print("📊 最终排名")
    print("="*70)
    
    results.sort(key=lambda x: x.get('total_return', 0), reverse=True)
    
    for i, res in enumerate(results, 1):
        print(f"\n  {i}. {res['name']}")
        print(f"     收益率: {res.get('total_return', 0):+.2f}%")
        print(f"     交易: 买{res.get('buy_count', 0)}次 / 卖{res.get('sell_count', 0)}次")
    
    if results:
        best = results[0]
        print("\n" + "="*70)
        print("🏆 最优策略")
        print("="*70)
        print(f"\n  策略: {best['name']}")
        print(f"  收益率: {best.get('total_return', 0):+.2f}%")
        print(f"\n  参数:")
        for k, v in best['params'].items():
            print(f"    • {k}: {v}")
    
    print("\n" + "="*70)
    print("✨ 完成!")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
