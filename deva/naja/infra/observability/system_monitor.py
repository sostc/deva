"""系统监控模块 - Naja 健康状态监控

监控各模块的运行状态、心跳、关键指标
"""

import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from deva.naja.register import SR

log = logging.getLogger(__name__)


class ModuleStatus(Enum):
    """模块状态枚举"""
    HEALTHY = "healthy"      # 正常运行
    WARNING = "warning"     # 警告（延迟高/部分功能受损）
    ERROR = "error"         # 错误（功能不可用）
    DEAD = "dead"           # 无响应
    UNKNOWN = "unknown"     # 未知


@dataclass
class ModuleHealth:
    """单个模块的健康状态"""
    name: str           # 模块显示名
    key: str            # 模块标识
    status: ModuleStatus
    last_seen: float    # 最后活跃时间戳
    delay: float        # 响应延迟(秒)
    info: str           # 附加信息
    details: Dict[str, Any] = None  # 详细信息
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "key": self.key,
            "status": self.status.value,
            "last_seen": self.last_seen,
            "delay": self.delay,
            "info": self.info,
            "details": self.details or {},
        }


class SystemMonitor:
    """系统监控器"""
    
    # 模块注册表
    MODULES = {
        "orchestrator": {"name": "🧠 注意力中枢", "class": "Orchestrator", "method": "get_stats"},
        "radar": {"name": "📡 雷达引擎", "class": "RadarEngine", "method": "get_recent_events"},
        "bandit": {"name": "🎰 Bandit决策", "class": "BanditRunner", "method": "get_stats"},
        "cognition": {"name": "🧩 认知系统", "class": "CognitionEngine", "method": "get_memory_report"},
        "wisdom": {"name": "📚 智慧陪伴", "class": "TradingCenter", "method": "get_wisdom_stats"},
        "manas": {"name": "👁️ 末那识", "class": "ManasCore", "method": "get_stats"},
        "alaya": {"name": "✨ 阿那亚", "class": "AwakenedAlaya", "method": "get_stats"},
        "data_source": {"name": "📡 数据源", "class": "DataSourceManager", "method": "get_stats"},
        "strategy": {"name": "📊 策略", "class": "StrategyManager", "method": "get_stats"},
        "task": {"name": "⏰ 任务", "class": "TaskManager", "method": "get_stats"},
    }
    
    # 心跳超时阈值(秒)
    HEALTHY_THRESHOLD = 30      # 30秒内活跃 = 健康
    WARNING_THRESHOLD = 60     # 60秒内活跃 = 警告
    DEAD_THRESHOLD = 120       # 120秒无响应 = 死亡
    
    def __init__(self):
        self._module_stats: Dict[str, Dict] = {}  # 缓存各模块状态
        self._last_check = 0
        self._cache_ttl = 5  # 缓存5秒
    
    def check_module(self, module_key: str) -> ModuleHealth:
        """检查单个模块的健康状态"""
        now = time.time()
        
        if now - self._last_check < self._cache_ttl and module_key in self._module_stats:
            cached = self._module_stats[module_key]
            if now - cached.get("last_seen", 0) < self._cache_ttl:
                return ModuleHealth(
                    name=cached["name"],
                    key=module_key,
                    status=ModuleStatus(cached["status"]),
                    last_seen=cached["last_seen"],
                    delay=cached["delay"],
                    info=cached["info"],
                    details=cached.get("details", {}),
                )
        
        module_info = self.MODULES.get(module_key, {})
        name = module_info.get("name", module_key)
        
        try:
            start = time.time()
            stats = self._fetch_module_stats(module_key)
            delay = time.time() - start
            
            if stats is None:
                return self._create_unknown(module_key, name, now)
            
            last_seen = stats.get("_last_update", now)
            status = self._compute_status(now - last_seen, delay)
            
            # 提取摘要信息
            info = self._extract_summary(module_key, stats)
            
            health = ModuleHealth(
                name=name,
                key=module_key,
                status=status,
                last_seen=last_seen,
                delay=delay,
                info=info,
                details=stats if isinstance(stats, dict) else {},
            )
            
            self._module_stats[module_key] = health.to_dict()
            self._last_check = now
            
            return health
            
        except Exception as e:
            log.warning(f"检查模块 {module_key} 失败: {e}")
            return ModuleHealth(
                name=name,
                key=module_key,
                status=ModuleStatus.ERROR,
                last_seen=now,
                delay=0,
                info=f"错误: {str(e)[:50]}",
            )
    
    def _fetch_module_stats(self, module_key: str) -> Optional[Dict]:
        """获取模块统计数据"""
        module_info = self.MODULES.get(module_key)
        if not module_info:
            return None
        
        class_name = module_info["class"]
        method_name = module_info["method"]
        
        # 根据类名获取实例
        instance = None
        try:
            if class_name == "Orchestrator":
                from deva.naja.attention.orchestration.trading_center import get_trading_center
                instance = get_trading_center()
            elif class_name == "TradingCenter":
                from deva.naja.attention.orchestration.trading_center import get_trading_center
                instance = get_trading_center()
            elif class_name == "RadarEngine":
                from deva.naja.radar import get_radar_engine
                instance = get_radar_engine()
            elif class_name == "BanditRunner":
                instance = SR('bandit_runner')
            elif class_name == "CognitionEngine":
                instance = SR('cognition_engine')
            elif class_name == "TradingCenter":
                from deva.naja.attention.orchestration.trading_center import get_trading_center
                instance = get_trading_center()
            elif class_name == "DataSourceManager":
                from deva.naja.datasource import get_datasource_manager
                instance = get_datasource_manager()
            elif class_name == "StrategyManager":
                from deva.naja.strategy import get_strategy_manager
                instance = get_strategy_manager()
            elif class_name == "TaskManager":
                instance = SR('task_manager')
            elif class_name == "ManasCore":
                from deva.naja.attention.orchestration.trading_center import get_trading_center
                tc = get_trading_center()
                instance = tc.get_attention_os().kernel.get_manas_engine()
            elif class_name == "AwakenedAlaya":
                instance = SR('awakened_alaya')
        except ImportError as e:
            log.debug(f"无法导入 {class_name}: {e}")
            return None
        except Exception as e:
            log.debug(f"获取 {class_name} 实例失败: {e}")
            return None
        
        if instance is None:
            return None
        
        # 调用统计方法
        if hasattr(instance, method_name):
            result = getattr(instance, method_name)()
            if callable(result):
                result = result()
            return result if isinstance(result, dict) else {"_last_update": time.time()}
        
        return {"_last_update": time.time()}
    
    def _compute_status(self, age: float, delay: float) -> ModuleStatus:
        """根据活跃时间和延迟计算状态"""
        if age > self.DEAD_THRESHOLD:
            return ModuleStatus.DEAD
        if delay > 5:  # 响应慢
            return ModuleStatus.WARNING
        if age > self.WARNING_THRESHOLD:
            return ModuleStatus.WARNING
        return ModuleStatus.HEALTHY
    
    def _extract_summary(self, module_key: str, stats: Dict) -> str:
        """从统计数据中提取摘要"""
        if not stats:
            return "无数据"
        
        summaries = {
            "orchestrator": lambda s: f"策略 {s.get('registered_strategies', 0)} | 事件 {s.get('total_events', 0)}",
            "radar": lambda s: f"事件 {len(s.get('events', []))}",
            "bandit": lambda s: f"决策 {s.get('total_actions', 0)} | 置信 {s.get('avg_confidence', 0):.2f}" if isinstance(s, dict) else "运行中",
            "cognition": lambda s: f"活跃话题 {s.get('active_topics', 0)}",
            "wisdom": lambda s: f"触发 {s.get('trigger_count', 0)}次",
            "manas": lambda s: f"四眼 {s.get('eyes_active', 0)}/4",
            "alaya": lambda s: f"觉醒 {s.get('awakening_level', 'unknown')}",
            "data_source": lambda s: f"源 {s.get('total', 0)}",
            "strategy": lambda s: f"策略 {s.get('total', 0)}",
            "task": lambda s: f"任务 {s.get('total', 0)}",
        }
        
        extractor = summaries.get(module_key)
        if extractor:
            try:
                return extractor(stats)
            except:
                return "运行中"
        
        return "运行中"
    
    def _create_unknown(self, module_key: str, name: str, now: float) -> ModuleHealth:
        """创建未知状态"""
        return ModuleHealth(
            name=name,
            key=module_key,
            status=ModuleStatus.UNKNOWN,
            last_seen=now,
            delay=0,
            info="模块未初始化",
        )
    
    def get_all_health(self) -> List[ModuleHealth]:
        """获取所有模块的健康状态"""
        return [self.check_module(key) for key in self.MODULES.keys()]
    
    def get_overall_status(self) -> Dict[str, Any]:
        """获取整体系统状态"""
        all_health = self.get_all_health()
        
        healthy = sum(1 for h in all_health if h.status == ModuleStatus.HEALTHY)
        warning = sum(1 for h in all_health if h.status == ModuleStatus.WARNING)
        error = sum(1 for h in all_health if h.status in (ModuleStatus.ERROR, ModuleStatus.DEAD))
        total = len(all_health)
        
        if error > 0:
            overall = "🔴 异常"
        elif warning > 0:
            overall = "🟡 警告"
        else:
            overall = "🟢 正常"
        
        return {
            "overall": overall,
            "healthy": healthy,
            "warning": warning,
            "error": error,
            "total": total,
            "modules": [h.to_dict() for h in all_health],
            "timestamp": time.time(),
        }

