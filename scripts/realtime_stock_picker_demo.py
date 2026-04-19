#!/usr/bin/env python
"""
实时选股策略演示 - 简化版
展示流式 Skill + River 在线学习的核心概念
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
    volume: int = 100
    current_price: float = 0.0
    
    @property
    def profit_pct(self) -> float:
        if self.buy_price == 0:
            return 0.0
        return (self.current_price - self.buy_price) / self.buy_price * 100


class SimpleStockPickerSkill(StreamSkill):
    """简化版实时选股策略 Skill"""
    
    def __init__(self, skill_id: str = "simple_picker"):
        super().__init__(skill_id)
        
        # River 模型
        self.model = linear_model.LogisticRegression(
            optimizer=optim.SGD(0.01)
        )
        self.scaler = preprocessing.StandardScaler()
        
        # 资金和持仓
        self.initial_capital = 100000.0
        self.current_capital = 100000.0
        self.positions: Dict[str, StockPosition] = {}
        
        # 历史数据
        self.stock_history: Dict[str, List[Dict]] = defaultdict(list)
        
    def extract_features(self, code: str) -> Dict[str, float]:
        """提取股票特征"""
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
        if not features:
            return 0.5
        try:
            scaled = self.scaler.learn_one(features).transform_one(features)
            # 使用 predict_proba_one 获取概率
            proba = self.model.predict_proba_one(scaled)
            return proba.get(True, 0.5) if isinstance(proba, dict) else 0.5
        except:
            return 0.5
    
    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行策略"""
        strategy_name = input_data.get('strategy_name', 'default')
        max_frames = input_data.get('max_frames', 50)  # 只处理前50帧
        
        print(f"\n🚀 [Skill] 启动策略: {strategy_name}")
        
        # 连接数据源
        db = NB("quant_snapshot_5min_window")
        replay_data = list(db.items())[:max_frames]
        
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "trading", "frames": len(replay_data)},
            stage="trading"
        )
        
        trades_count = 0
        
        # 处理每一帧
        for i, (timestamp, df) in enumerate(replay_data):
            if not isinstance(df, pd.DataFrame):
                continue
            
            # 更新持仓价格
            for code, pos in self.positions.items():
                stock_data = df[df['code'] == code]
                if not stock_data.empty:
                    pos.current_price = float(stock_data.iloc[0].get('now', pos.buy_price))
            
            # 检查止损（亏损超过5%）
            codes_to_sell = [code for code, pos in self.positions.items() if pos.profit_pct < -5]
            for code in codes_to_sell:
                pos = self.positions[code]
                sell_value = pos.current_price * pos.volume
                self.current_capital += sell_value
                
                # 在线学习：用实际收益更新模型
                features = self.extract_features(code)
                if features:
                    scaled = self.scaler.learn_one(features).transform_one(features)
                    self.model.learn_one(scaled, pos.profit_pct > 0)
                
                del self.positions[code]
                trades_count += 1
                print(f"  [卖出] {code} @ {pos.current_price:.2f}, 收益: {pos.profit_pct:.2f}%")
            
            # 选股买入
            if len(self.positions) < 3:  # 最多3只持仓
                candidates = []
                
                for _, row in df.head(100).iterrows():  # 只看前100只
                    code = row.get('code')
                    if not code or code in self.positions:
                        continue
                    
                    # 更新历史
                    self.stock_history[code].append({
                        'price': float(row.get('now', row.get('close', 0))),
                        'volume': float(row.get('volume', 0)),
                    })
                    
                    # 提取特征并预测
                    features = self.extract_features(code)
                    if features:
                        score = self.predict_score(features)
                        if score > 0.6:  # 买入阈值
                            candidates.append((code, score, row))
                
                # 买入得分最高的
                candidates.sort(key=lambda x: x[1], reverse=True)
                for code, score, row in candidates[:3 - len(self.positions)]:
                    price = float(row.get('now', 0))
                    if price <= 0:
                        continue
                    
                    volume = 100
                    cost = price * volume
                    
                    if cost <= self.current_capital * 0.3:  # 单只最多30%资金
                        pos = StockPosition(
                            code=code,
                            name=row.get('name', code),
                            buy_price=price,
                            volume=volume,
                            current_price=price
                        )
                        self.positions[code] = pos
                        self.current_capital -= cost
                        trades_count += 1
                        print(f"  [买入] {code} @ {price:.2f} x {volume}股 (得分: {score:.2f})")
            
            # 每10帧报告进度
            if i % 10 == 0:
                total_value = self.current_capital + sum(
                    pos.current_price * pos.volume for pos in self.positions.values()
                )
                return_pct = (total_value - self.initial_capital) / self.initial_capital * 100
                
                yield SkillEvent(
                    event_type="progress",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={
                        "progress": int(i / len(replay_data) * 100),
                        "frame": i,
                        "capital": total_value,
                        "return_pct": return_pct,
                        "positions": len(self.positions),
                        "trades": trades_count
                    },
                    stage="trading"
                )
        
        # 计算最终收益
        final_value = self.current_capital + sum(
            pos.current_price * pos.volume for pos in self.positions.values()
        )
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        
        report = {
            "strategy_name": strategy_name,
            "initial_capital": self.initial_capital,
            "final_value": final_value,
            "total_return": total_return,
            "trades_count": trades_count,
            "final_positions": len(self.positions)
        }
        
        context.metadata["report"] = report
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "trading", "report": report},
            stage="trading"
        )
        
        print(f"\n✨ [Skill] 策略完成，总收益率: {total_return:.2f}%")


# =============================================================================
# 主程序 - 运行多个策略对比
# =============================================================================

async def main():
    """主函数"""
    print("\n" + "="*70)
    print("🚀 实时选股策略演示 - 多策略对比")
    print("="*70)
    
    # 定义多个策略配置
    strategies = [
        {"name": "Momentum_Picker", "buy_threshold": 0.6},
        {"name": "Aggressive_Picker", "buy_threshold": 0.5},
        {"name": "Conservative_Picker", "buy_threshold": 0.7},
    ]
    
    engine = get_execution_engine()
    interface = AgentSkillInterface("demo")
    
    results = []
    
    for strategy in strategies:
        skill_id = f"picker_{strategy['name']}"
        engine.register_skill(skill_id, SimpleStockPickerSkill)
        
        print(f"\n{'='*70}")
        print(f"📊 测试策略: {strategy['name']}")
        print(f"{'='*70}")
        
        # 运行策略
        result = await interface.invoke_skill(
            skill_id=skill_id,
            input_data={
                'strategy_name': strategy['name'],
                'max_frames': 100  # 只处理100帧数据
            }
        )
        
        # 提取结果
        if result.get('success'):
            for event in reversed(result.get('events', [])):
                if event.event_type == 'stage_completed' and event.data.get('report'):
                    report = event.data['report']
                    results.append({
                        'name': strategy['name'],
                        'return': report.get('total_return', 0),
                        'trades': report.get('trades_count', 0),
                        'final_value': report.get('final_value', 0)
                    })
                    break
    
    # 显示对比结果
    print("\n" + "="*70)
    print("📊 策略对比结果")
    print("="*70)
    
    # 按收益率排序
    results.sort(key=lambda x: x['return'], reverse=True)
    
    for i, res in enumerate(results, 1):
        print(f"\n  {i}. {res['name']}")
        print(f"     总收益率: {res['return']:.2f}%")
        print(f"     交易次数: {res['trades']}")
        print(f"     最终资产: ¥{res['final_value']:,.2f}")
    
    if results:
        best = results[0]
        print(f"\n{'='*70}")
        print("🏆 最优策略")
        print(f"{'='*70}")
        print(f"  策略: {best['name']}")
        print(f"  收益率: {best['return']:.2f}%")
    
    print(f"\n{'='*70}")
    print("✨ 演示完成!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
