"""
Dual Engine Module - River + PyTorch 双引擎策略体系

架构:
- River Engine: 基础层/常态层，全覆盖，轻量
- PyTorch Engine: 专家层/异常层，稀疏，深度判断

数据流:
tick → River(全量) → anomaly_score → Attention系统 → Top-K选择 → 
    PyTorch → pattern_score → Strategy Allocation

性能约束:
- River: O(1)/tick, 常驻内存
- PyTorch: 异步执行，批量推理，有并发限制
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass
from collections import deque, defaultdict
from enum import Enum
import time
import asyncio
from abc import ABC, abstractmethod

# River 库
from river import stats
from river import anomaly


class AnomalyLevel(Enum):
    """异常等级"""
    NORMAL = 0
    WEAK = 1      # 弱异常
    STRONG = 2    # 强异常


@dataclass
class AnomalySignal:
    """异常信号"""
    symbol: str
    anomaly_score: float
    anomaly_level: AnomalyLevel
    features: Dict[str, float]
    timestamp: float


@dataclass
class PatternSignal:
    """模式识别信号"""
    symbol: str
    pattern_score: float
    pattern_type: str
    confidence: float
    timestamp: float


class RiverEngine:
    """
    River 引擎 - 基础层/常态层
    
    功能:
    - 流式均值/方差
    - 在线回归
    - 残差检测
    - 输出 anomaly_score
    """
    
    def __init__(
        self,
        max_symbols: int = 5000,
        history_window: int = 20,
        anomaly_threshold_weak: float = 2.0,
        anomaly_threshold_strong: float = 3.5
    ):
        self.max_symbols = max_symbols
        self.history_window = history_window
        self.anomaly_threshold_weak = anomaly_threshold_weak
        self.anomaly_threshold_strong = anomaly_threshold_strong
        
        # Symbol 映射
        self._symbol_to_idx: Dict[str, int] = {}
        
        # River 统计量 (每个symbol独立)
        self._mean_estimators: Dict[str, stats.RollingMean] = {}
        self._var_estimators: Dict[str, stats.RollingVar] = {}
        self._anomaly_detectors: Dict[str, anomaly.GaussianScorer] = {}
        
        # 历史数据缓存
        self._price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_window))
        self._volume_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_window))
        
        # 异常分数缓存
        self._anomaly_scores = np.zeros(max_symbols)
        self._last_update = np.zeros(max_symbols)
        
        # 统计
        self._processed_count = 0
        self._anomaly_count = 0
    
    def register_symbol(self, symbol: str) -> bool:
        """注册个股"""
        if symbol in self._symbol_to_idx:
            return True
        
        if len(self._symbol_to_idx) >= self.max_symbols:
            return False
        
        idx = len(self._symbol_to_idx)
        self._symbol_to_idx[symbol] = idx
        
        # 初始化 River 统计量
        self._mean_estimators[symbol] = stats.Mean()
        self._var_estimators[symbol] = stats.Var()
        self._anomaly_detectors[symbol] = anomaly.GaussianScorer()
        
        return True
    
    def process_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        timestamp: float
    ) -> Optional[AnomalySignal]:
        """
        处理单个 tick 数据
        
        返回:
            AnomalySignal 如果检测到异常，否则 None
        """
        if symbol not in self._symbol_to_idx:
            return None
        
        idx = self._symbol_to_idx[symbol]
        
        # 更新历史
        self._price_history[symbol].append(price)
        self._volume_history[symbol].append(volume)
        
        # 提取特征
        features = self._extract_features(symbol, price, volume)
        
        # 更新 River 统计量
        mean_est = self._mean_estimators[symbol]
        var_est = self._var_estimators[symbol]
        anomaly_det = self._anomaly_detectors[symbol]
        
        # 计算预测值 (使用均值作为简单预测)
        predicted = mean_est.get() if mean_est.get() is not None else price
        
        # 更新统计量
        mean_est.update(price)
        var_est.update(price)
        
        # 计算残差
        residual = abs(price - predicted)
        
        # 异常检测 - 使用基于标准差的方法
        std = np.sqrt(var_est.get()) if var_est.get() is not None else 0
        if std > 0:
            anomaly_score = residual / std
        else:
            anomaly_score = 0.0
        
        self._anomaly_scores[idx] = anomaly_score
        self._last_update[idx] = timestamp
        self._processed_count += 1
        
        # 判断异常等级
        anomaly_level = self._classify_anomaly(anomaly_score)
        
        if anomaly_level != AnomalyLevel.NORMAL:
            self._anomaly_count += 1
            return AnomalySignal(
                symbol=symbol,
                anomaly_score=anomaly_score,
                anomaly_level=anomaly_level,
                features=features,
                timestamp=timestamp
            )
        
        return None
    
    def _extract_features(
        self,
        symbol: str,
        price: float,
        volume: float
    ) -> Dict[str, float]:
        """提取特征"""
        features = {
            'price': price,
            'volume': volume,
            'price_change': 0.0,
            'volume_ratio': 1.0,
            'volatility': 0.0
        }

        prices = list(self._price_history[symbol])
        volumes = list(self._volume_history[symbol])

        if len(prices) >= 2:
            prev_price = prices[-2]
            if prev_price > 0.01:  # 避免除零或极小值
                features['price_change'] = (price - prev_price) / prev_price * 100
                # 限制范围，防止异常值
                features['price_change'] = max(-50.0, min(50.0, features['price_change']))

        if len(volumes) >= 2:
            avg_volume = np.mean(volumes[:-1]) if len(volumes) > 1 else volumes[0]
            if avg_volume > 0:
                features['volume_ratio'] = volume / avg_volume
                # 限制范围
                features['volume_ratio'] = max(0.01, min(100.0, features['volume_ratio']))

        if len(prices) >= 5:
            price_window = prices[-5:]
            mean_price = np.mean(price_window)
            if mean_price > 0.01:
                volatility = np.std(price_window) / mean_price * 100
                features['volatility'] = max(0.0, min(50.0, volatility))

        return features
    
    def _classify_anomaly(self, score: float) -> AnomalyLevel:
        """分类异常等级"""
        if score >= self.anomaly_threshold_strong:
            return AnomalyLevel.STRONG
        elif score >= self.anomaly_threshold_weak:
            return AnomalyLevel.WEAK
        else:
            return AnomalyLevel.NORMAL
    
    def get_anomaly_score(self, symbol: str) -> float:
        """获取个股的异常分数"""
        idx = self._symbol_to_idx.get(symbol)
        if idx is None:
            return 0.0
        return float(self._anomaly_scores[idx])
    
    def get_top_anomalies(self, n: int = 20, min_score: float = 0.0) -> List[Tuple[str, float]]:
        """获取异常分数最高的个股"""
        anomalies = [
            (symbol, float(self._anomaly_scores[idx]))
            for symbol, idx in self._symbol_to_idx.items()
            if self._anomaly_scores[idx] >= min_score
        ]
        anomalies.sort(key=lambda x: x[1], reverse=True)
        return anomalies[:n]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'processed_count': self._processed_count,
            'anomaly_count': self._anomaly_count,
            'anomaly_ratio': self._anomaly_count / max(self._processed_count, 1),
            'active_symbols': len(self._symbol_to_idx)
        }
    
    def reset(self):
        """重置引擎"""
        self._symbol_to_idx.clear()
        self._mean_estimators.clear()
        self._var_estimators.clear()
        self._anomaly_detectors.clear()
        self._price_history.clear()
        self._volume_history.clear()
        self._anomaly_scores.fill(0.0)
        self._last_update.fill(0.0)
        self._processed_count = 0
        self._anomaly_count = 0


class PyTorchEngine:
    """
    PyTorch 引擎 - 专家层/异常层
    
    功能:
    - 只处理被 River 标记为异常的标的
    - 高阶模式识别
    - 回答: "这次异动像不像历史上的某种行为?"
    
    模式类型:
    - accumulation: 吸筹
    - shakeout: 洗盘
    - pre_pump: 拉升前震荡
    - distribution: 出货
    """
    
    def __init__(
        self,
        max_concurrent: int = 10,
        batch_size: int = 32,
        sequence_length: int = 20,
        pattern_types: Optional[List[str]] = None
    ):
        self.max_concurrent = max_concurrent
        self.batch_size = batch_size
        self.sequence_length = sequence_length
        
        self.pattern_types = pattern_types or [
            'accumulation', 'shakeout', 'pre_pump', 'distribution'
        ]
        
        # 待处理队列
        self._pending_queue: deque = deque()
        self._processing: set = set()
        
        # 模型 (延迟加载)
        self._model = None
        self._model_loaded = False
        
        # 结果缓存
        self._pattern_cache: Dict[str, PatternSignal] = {}
        self._cache_ttl = 60.0  # 缓存有效期(秒)
        
        # 统计
        self._inference_count = 0
        self._inference_time = 0.0
    
    def _load_model(self):
        """加载 PyTorch 模型 (延迟加载) - 支持GPU"""
        if self._model_loaded:
            return
        
        try:
            import torch
            import torch.nn as nn
            
            # 检查GPU可用性 - 支持CUDA和Apple MPS
            if torch.cuda.is_available():
                self._device = torch.device('cuda')
                print(f"[PyTorchEngine] 使用 NVIDIA GPU: {torch.cuda.get_device_name(0)}")
                print(f"[PyTorchEngine] 显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            elif torch.backends.mps.is_available():
                self._device = torch.device('mps')
                print(f"[PyTorchEngine] 使用 Apple MPS (Metal Performance Shaders)")
                print(f"[PyTorchEngine] 设备: Apple Silicon (M1/M2/M3)")
            else:
                self._device = torch.device('cpu')
                print(f"[PyTorchEngine] 使用 CPU")
            
            # 定义简单的 LSTM 模型
            class PatternLSTM(nn.Module):
                def __init__(self, input_size=5, hidden_size=64, num_classes=4):
                    super().__init__()
                    self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
                    self.fc = nn.Linear(hidden_size, num_classes)
                    self.softmax = nn.Softmax(dim=1)
                
                def forward(self, x):
                    lstm_out, _ = self.lstm(x)
                    last_output = lstm_out[:, -1, :]
                    output = self.fc(last_output)
                    return self.softmax(output)
            
            self._model = PatternLSTM()
            # 将模型移动到GPU
            self._model = self._model.to(self._device)
            self._model.eval()
            self._model_loaded = True
            
            print(f"[PyTorchEngine] 模型加载完成，已迁移到 {self._device}")
            
        except ImportError:
            # PyTorch 未安装，使用模拟模式
            self._model = None
            self._device = None
            self._model_loaded = True
            print("[PyTorchEngine] PyTorch未安装，使用模拟模式")
    
    def submit(self, anomaly_signal: AnomalySignal) -> bool:
        """
        提交异常信号到 PyTorch 引擎
        
        Returns:
            是否成功提交
        """
        # 检查是否已在处理中
        if anomaly_signal.symbol in self._processing:
            return False
        
        # 检查缓存
        cached = self._pattern_cache.get(anomaly_signal.symbol)
        if cached and (time.time() - cached.timestamp) < self._cache_ttl:
            return False
        
        # 检查并发限制
        if len(self._processing) >= self.max_concurrent:
            return False
        
        # 提交到队列
        self._pending_queue.append(anomaly_signal)
        return True
    
    async def process_batch(self) -> List[PatternSignal]:
        """
        批量处理异常信号
        
        Returns:
            模式识别结果列表
        """
        self._load_model()
        
        # 收集待处理信号
        batch = []
        while len(batch) < self.batch_size and self._pending_queue:
            signal = self._pending_queue.popleft()
            if signal.symbol not in self._processing:
                batch.append(signal)
                self._processing.add(signal.symbol)
        
        if not batch:
            return []
        
        # 执行推理
        start_time = time.time()
        
        if self._model is not None:
            results = await self._inference_with_model(batch)
        else:
            results = self._inference_mock(batch)
        
        inference_time = time.time() - start_time
        self._inference_count += len(batch)
        self._inference_time += inference_time
        
        # 更新缓存和处理状态
        for result in results:
            self._pattern_cache[result.symbol] = result
            self._processing.discard(result.symbol)
        
        return results
    
    async def _inference_with_model(self, batch: List[AnomalySignal]) -> List[PatternSignal]:
        """使用 PyTorch 模型推理 - GPU加速版本"""
        import torch
        
        results = []
        
        # 批量处理以提高GPU利用率
        features_list = []
        for signal in batch:
            features = self._build_feature_tensor(signal)
            features_list.append(features)
        
        # 合并为批次张量
        if features_list:
            batch_tensor = torch.cat(features_list, dim=0)
            # 移动到GPU
            if hasattr(self, '_device') and self._device:
                batch_tensor = batch_tensor.to(self._device)
            
            # 批量推理
            with torch.no_grad():
                outputs = self._model(batch_tensor)
                # 移回CPU进行后续处理
                outputs = outputs.cpu()
                probs_batch = outputs.numpy()
            
            # 解析结果
            for i, signal in enumerate(batch):
                probs = probs_batch[i]
                pattern_idx = np.argmax(probs)
                pattern_type = self.pattern_types[pattern_idx]
                confidence = float(probs[pattern_idx])
                
                results.append(PatternSignal(
                    symbol=signal.symbol,
                    pattern_score=signal.anomaly_score * confidence,
                    pattern_type=pattern_type,
                    confidence=confidence,
                    timestamp=time.time()
                ))
        
        return results
    
    def _inference_mock(self, batch: List[AnomalySignal]) -> List[PatternSignal]:
        """模拟推理 (当 PyTorch 不可用时)"""
        results = []
        
        for signal in batch:
            # 基于特征简单判断模式
            features = signal.features
            
            # 简单启发式规则
            if features.get('volume_ratio', 1.0) > 2.0 and features.get('price_change', 0) > 3:
                pattern_type = 'pre_pump'
                confidence = 0.7
            elif features.get('volume_ratio', 1.0) > 2.0 and features.get('price_change', 0) < -3:
                pattern_type = 'shakeout'
                confidence = 0.6
            elif features.get('volatility', 0) < 1.0 and features.get('volume_ratio', 1.0) > 1.5:
                pattern_type = 'accumulation'
                confidence = 0.5
            else:
                pattern_type = 'distribution'
                confidence = 0.4
            
            results.append(PatternSignal(
                symbol=signal.symbol,
                pattern_score=signal.anomaly_score * confidence,
                pattern_type=pattern_type,
                confidence=confidence,
                timestamp=time.time()
            ))
        
        return results
    
    def _build_feature_tensor(self, signal: AnomalySignal) -> Any:
        """构建特征张量 - 支持GPU"""
        import torch
        
        # 简化版本: 使用当前特征
        features = [
            signal.features.get('price', 0),
            signal.features.get('volume', 0),
            signal.features.get('price_change', 0),
            signal.features.get('volume_ratio', 1.0),
            signal.features.get('volatility', 0)
        ]
        
        # 创建张量 [1, sequence_length, features]
        tensor = torch.tensor([features] * self.sequence_length, dtype=torch.float32)
        tensor = tensor.unsqueeze(0)
        
        # 如果模型在GPU/MPS上，张量也移到对应设备
        if hasattr(self, '_device') and self._device and self._device.type in ['cuda', 'mps']:
            tensor = tensor.to(self._device)
        
        return tensor
    
    def get_pattern(self, symbol: str) -> Optional[PatternSignal]:
        """获取个股的模式识别结果"""
        cached = self._pattern_cache.get(symbol)
        if cached and (time.time() - cached.timestamp) < self._cache_ttl:
            return cached
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        avg_inference_time = (
            self._inference_time / max(self._inference_count, 1)
        )
        
        return {
            'inference_count': self._inference_count,
            'avg_inference_time_ms': avg_inference_time * 1000,
            'pending_queue_size': len(self._pending_queue),
            'processing_count': len(self._processing),
            'cache_size': len(self._pattern_cache)
        }
    
    def reset(self):
        """重置引擎"""
        self._pending_queue.clear()
        self._processing.clear()
        self._pattern_cache.clear()
        self._inference_count = 0
        self._inference_time = 0.0


class DualEngineCoordinator:
    """
    双引擎协调器
    
    职责:
    1. 管理 River 和 PyTorch 引擎
    2. 处理触发逻辑
    3. 控制资源占用
    4. 避免重复触发
    """
    
    def __init__(
        self,
        river_engine: Optional[RiverEngine] = None,
        pytorch_engine: Optional[PyTorchEngine] = None,
        max_pytorch_triggers: int = 50  # 每轮最大 PyTorch 触发数
    ):
        self.river = river_engine or RiverEngine()
        self.pytorch = pytorch_engine or PyTorchEngine()
        self.max_pytorch_triggers = max_pytorch_triggers
        
        # 触发控制
        self._trigger_cooldown: Dict[str, float] = {}
        self._cooldown_period = 60.0  # 冷却期(秒)
        
        # 触发分数权重
        self._anomaly_weight = 0.4
        self._symbol_weight = 0.3
        self._sector_weight = 0.2
        self._global_weight = 0.1
        
        # 统计
        self._trigger_count = 0
    
    def process_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        global_attention: float,
        block_attention: Dict[str, float],
        symbol_weight: float,
        timestamp: float
    ) -> Optional[PatternSignal]:
        """
        处理单个 tick
        
        流程:
        1. River 处理
        2. 如果异常，计算触发分数
        3. 如果触发分数高，提交到 PyTorch
        4. 返回 PyTorch 结果
        """
        # Step 0: 确保股票已注册
        if symbol not in self.river._symbol_to_idx:
            self.river.register_symbol(symbol)
        
        # Step 1: River 处理
        anomaly_signal = self.river.process_tick(symbol, price, volume, timestamp)
        
        if anomaly_signal is None:
            return None
        
        # Step 2: 计算触发分数
        trigger_score = self._calc_trigger_score(
            anomaly_signal,
            global_attention,
            block_attention,
            symbol_weight
        )
        
        # Step 3: 检查是否触发 PyTorch
        if not self._should_trigger_pytorch(symbol, trigger_score, timestamp):
            return None
        
        # Step 4: 提交到 PyTorch
        self.pytorch.submit(anomaly_signal)
        
        # 返回缓存的结果 (如果有)
        return self.pytorch.get_pattern(symbol)
    
    def _calc_trigger_score(
        self,
        anomaly_signal: AnomalySignal,
        global_attention: float,
        block_attention: Dict[str, float],
        symbol_weight: float
    ) -> float:
        """
        计算触发分数

        trigger_score = f(anomaly_score, symbol_weight, block_attention, global_attention)
        """
        try:
            # 板块注意力取平均 - 添加数值检查
            if block_attention:
                values = list(block_attention.values())
                # 过滤掉异常值
                valid_values = [v for v in values if isinstance(v, (int, float)) and not np.isnan(v) and not np.isinf(v)]
                avg_block_attention = np.mean(valid_values) if valid_values else 0.0
            else:
                avg_block_attention = 0.0

            # 确保 global_attention 是有效数值
            if not isinstance(global_attention, (int, float)) or np.isnan(global_attention) or np.isinf(global_attention):
                global_attention = 0.0

            # 确保 symbol_weight 是有效数值
            if not isinstance(symbol_weight, (int, float)) or np.isnan(symbol_weight) or np.isinf(symbol_weight):
                symbol_weight = 0.0

            # 归一化 anomaly_score (假设正常范围 0-5)
            normalized_anomaly = min(max(anomaly_signal.anomaly_score, 0.0) / 5.0, 1.0)

            # 归一化 symbol_weight (假设正常范围 0-5)
            normalized_symbol = min(max(symbol_weight, 0.0) / 5.0, 1.0)

            # 限制 block_attention 和 global_attention 范围
            avg_block_attention = max(0.0, min(1.0, avg_block_attention))
            global_attention = max(0.0, min(1.0, global_attention))

            score = (
                normalized_anomaly * self._anomaly_weight +
                normalized_symbol * self._symbol_weight +
                avg_block_attention * self._sector_weight +
                global_attention * self._global_weight
            )

            return max(0.0, min(1.0, score))
        except Exception:
            return 0.0
    
    def _should_trigger_pytorch(
        self,
        symbol: str,
        trigger_score: float,
        timestamp: float
    ) -> bool:
        """判断是否应该触发 PyTorch - 降低阈值版本"""
        # 检查冷却期
        last_trigger = self._trigger_cooldown.get(symbol, 0)
        if timestamp - last_trigger < self._cooldown_period:
            return False
        
        # 检查触发分数阈值 - 从 0.5 降低到 0.3，更容易触发
        if trigger_score < 0.3:
            return False
        
        # 更新冷却时间
        self._trigger_cooldown[symbol] = timestamp
        self._trigger_count += 1
        
        return True
    
    async def process_pytorch_batch(self) -> List[PatternSignal]:
        """处理 PyTorch 批量推理"""
        return await self.pytorch.process_batch()
    
    def get_trigger_summary(self) -> Dict[str, Any]:
        """获取触发摘要"""
        return {
            'trigger_count': self._trigger_count,
            'river_stats': self.river.get_stats(),
            'pytorch_stats': self.pytorch.get_stats()
        }
    
    def reset(self):
        """重置协调器"""
        self.river.reset()
        self.pytorch.reset()
        self._trigger_cooldown.clear()
        self._trigger_count = 0