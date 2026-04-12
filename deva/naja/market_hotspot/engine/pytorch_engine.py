"""
PyTorch 引擎 - 专家层/异常层

基于 PyTorch 的深度学习引擎，提供：
- 异步批量推理
- 模式识别（突破确认/假突破/洗盘）
- 并发限制保护
"""

import numpy as np
from typing import Dict, List, Optional, Any
from collections import deque
import time
import asyncio

from .models import PatternSignal, AnomalySignal


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


