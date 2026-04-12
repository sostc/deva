"""
兼容性垫片 - 原 dual_engine.py 已拆分为独立模块

- models.py: AnomalyLevel, AnomalySignal, PatternSignal
- river_engine.py: RiverEngine
- pytorch_engine.py: PyTorchEngine
- coordinator.py: DualEngineCoordinator

所有符号从子模块重新导出，保持向后兼容。
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
