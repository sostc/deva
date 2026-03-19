#!/usr/bin/env python
"""
集成学习模型 - 智能选股策略系统 v2.0
结合多个 River 模型进行预测
"""

import numpy as np
from typing import Dict, Any, List
from collections import defaultdict

from river import linear_model, tree, ensemble, preprocessing, optim


class AdaptiveEnsembleModel:
    """
    自适应集成学习模型
    
    结合多个 River 模型：
    - LogisticRegression: 线性模型，快速学习
    - HoeffdingTree: 决策树，捕捉非线性关系
    - AdaptiveRandomForest: 随机森林，稳定预测
    """
    
    def __init__(self, learning_rate: float = 0.01):
        self.learning_rate = learning_rate
        self.scaler = preprocessing.StandardScaler()
        
        # 初始化多个模型
        self.models = {
            'logistic': linear_model.LogisticRegression(
                optimizer=optim.SGD(learning_rate)
            ),
            'tree': tree.HoeffdingTreeClassifier(),
            'forest': ensemble.AdaptiveRandomForestClassifier(
                n_models=10,
                seed=42
            ),
        }
        
        # 模型权重（根据表现动态调整）
        self.weights = {name: 1.0 for name in self.models}
        
        # 模型性能跟踪
        self.model_performances = defaultdict(list)
        
        # 预测历史
        self.prediction_history = []
    
    def predict_proba(self, features: Dict[str, float]) -> float:
        """
        加权投票预测
        
        Returns:
            预测得分 (0-1)
        """
        if not features:
            return 0.5
        
        try:
            # 标准化特征
            scaled_features = self.scaler.learn_one(features).transform_one(features)
            
            # 获取各模型预测
            predictions = {}
            for name, model in self.models.items():
                try:
                    proba = model.predict_proba_one(scaled_features)
                    predictions[name] = proba.get(True, 0.5) if isinstance(proba, dict) else 0.5
                except Exception:
                    predictions[name] = 0.5
            
            # 加权平均
            weighted_sum = sum(
                pred * self.weights[name]
                for name, pred in predictions.items()
            )
            total_weight = sum(self.weights.values())
            
            final_prediction = weighted_sum / total_weight if total_weight > 0 else 0.5
            
            # 记录预测历史
            self.prediction_history.append({
                'features': features,
                'predictions': predictions,
                'weights': self.weights.copy(),
                'final': final_prediction
            })
            
            # 限制历史长度
            if len(self.prediction_history) > 100:
                self.prediction_history = self.prediction_history[-100:]
            
            return final_prediction
            
        except Exception as e:
            print(f"[集成模型] 预测失败: {e}")
            return 0.5
    
    def learn(self, features: Dict[str, float], label: bool):
        """
        在线学习更新所有模型
        
        Args:
            features: 特征字典
            label: 标签（True=盈利, False=亏损）
        """
        if not features:
            return
        
        try:
            # 标准化特征
            scaled_features = self.scaler.learn_one(features).transform_one(features)
            
            # 更新所有模型
            for name, model in self.models.items():
                try:
                    model.learn_one(scaled_features, label)
                except Exception as e:
                    print(f"[集成模型] {name} 学习失败: {e}")
            
        except Exception as e:
            print(f"[集成模型] 学习失败: {e}")
    
    def update_weights(self, actual_result: bool):
        """
        根据实际结果更新模型权重
        
        Args:
            actual_result: 实际结果（True=盈利, False=亏损）
        """
        if not self.prediction_history:
            return
        
        # 获取最近一次预测
        last_prediction = self.prediction_history[-1]
        predictions = last_prediction['predictions']
        
        # 更新各模型权重
        for name, pred in predictions.items():
            # 预测正确则增加权重，错误则降低
            predicted_label = pred > 0.5
            if predicted_label == actual_result:
                # 预测正确，增加权重
                self.weights[name] *= 1.1
                self.model_performances[name].append(1)
            else:
                # 预测错误，降低权重
                self.weights[name] *= 0.9
                self.model_performances[name].append(0)
            
            # 限制权重范围
            self.weights[name] = max(0.1, min(5.0, self.weights[name]))
        
        # 归一化权重
        total_weight = sum(self.weights.values())
        if total_weight > 0:
            self.weights = {k: v/total_weight * len(self.weights) for k, v in self.weights.items()}
    
    def get_model_status(self) -> Dict[str, Any]:
        """获取模型状态"""
        status = {
            'weights': self.weights.copy(),
            'performances': {}
        }
        
        for name in self.models:
            if self.model_performances[name]:
                recent_perf = self.model_performances[name][-20:]
                accuracy = sum(recent_perf) / len(recent_perf) if recent_perf else 0
                status['performances'][name] = {
                    'accuracy': accuracy,
                    'total_samples': len(self.model_performances[name])
                }
            else:
                status['performances'][name] = {
                    'accuracy': 0.5,
                    'total_samples': 0
                }
        
        return status
    
    def print_status(self):
        """打印模型状态"""
        status = self.get_model_status()
        
        print("\n" + "="*70)
        print("🤖 集成模型状态")
        print("="*70)
        
        for name in self.models:
            weight = status['weights'][name]
            perf = status['performances'][name]
            print(f"  {name:15s} 权重: {weight:.3f}  准确率: {perf['accuracy']:.2%}  样本: {perf['total_samples']}")
        
        print("="*70 + "\n")


class ModelSelector:
    """
    模型选择器
    
    根据市场状态选择最佳模型
    """
    
    def __init__(self):
        self.models = {
            'conservative': AdaptiveEnsembleModel(learning_rate=0.005),
            'balanced': AdaptiveEnsembleModel(learning_rate=0.01),
            'aggressive': AdaptiveEnsembleModel(learning_rate=0.02),
        }
        
        self.current_model = 'balanced'
        self.performance_history = defaultdict(list)
    
    def select_model(self, market_state: str) -> AdaptiveEnsembleModel:
        """
        根据市场状态选择模型
        
        Args:
            market_state: 市场状态
            
        Returns:
            选中的模型
        """
        model_mapping = {
            'bull_volatile': 'aggressive',
            'bull_stable': 'balanced',
            'bear_volatile': 'conservative',
            'bear_stable': 'conservative',
            'sideways': 'balanced',
            'neutral': 'balanced',
        }
        
        self.current_model = model_mapping.get(market_state, 'balanced')
        return self.models[self.current_model]
    
    def get_current_model(self) -> AdaptiveEnsembleModel:
        """获取当前使用的模型"""
        return self.models[self.current_model]
    
    def record_performance(self, model_name: str, profit: float):
        """记录模型表现"""
        self.performance_history[model_name].append(profit)
        
        # 限制历史长度
        if len(self.performance_history[model_name]) > 100:
            self.performance_history[model_name] = self.performance_history[model_name][-100:]
    
    def get_best_model(self) -> str:
        """获取表现最好的模型"""
        avg_performances = {}
        for name, profits in self.performance_history.items():
            if profits:
                avg_performances[name] = np.mean(profits[-20:])
            else:
                avg_performances[name] = 0
        
        return max(avg_performances, key=avg_performances.get)


# 测试代码
if __name__ == "__main__":
    print("="*70)
    print("集成学习模型测试")
    print("="*70)
    
    # 创建集成模型
    ensemble_model = AdaptiveEnsembleModel(learning_rate=0.01)
    
    # 模拟训练
    print("\n模拟训练过程:")
    for i in range(30):
        # 模拟特征
        features = {
            'price_change': np.random.randn() * 2,
            'volume_ratio': 1.0 + np.random.randn() * 0.3,
            'rsi': 50 + np.random.randn() * 20,
        }
        
        # 预测
        pred = ensemble_model.predict_proba(features)
        
        # 模拟结果
        actual = np.random.random() > 0.4  # 60%胜率
        
        # 学习
        ensemble_model.learn(features, actual)
        ensemble_model.update_weights(actual)
        
        if i % 10 == 0:
            print(f"  样本{i:2d}: 预测={pred:.3f}, 实际={'盈利' if actual else '亏损'}")
    
    # 打印状态
    ensemble_model.print_status()
    
    print("="*70)
    print("测试完成!")
    print("="*70)
