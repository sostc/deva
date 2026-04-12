"""
Engine - River + PyTorch 双引擎

模块结构：
- models.py: 公共数据模型（AnomalyLevel, AnomalySignal, PatternSignal）
- river_engine.py: River 在线学习引擎
- pytorch_engine.py: PyTorch 深度学习引擎
- coordinator.py: 双引擎协调器
"""

from .models import AnomalyLevel, AnomalySignal, PatternSignal
from .river_engine import RiverEngine
from .pytorch_engine import PyTorchEngine
from .coordinator import DualEngineCoordinator

__all__ = [
    "AnomalyLevel",
    "AnomalySignal",
    "PatternSignal",
    "RiverEngine",
    "PyTorchEngine",
    "DualEngineCoordinator",
]
