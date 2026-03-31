"""
股票信息注册表 - Stock Info Registry

统一管理股票代码映射和元数据的核心基础设施。

功能：
1. 代码归一化 - sh600686 ↔ 600686 ↔ 600686.SH
2. 双向映射 - sina_code, normalized_code, display_code
3. 股票元数据 - 名称、市场、类型、交易所
4. 持久化存储 - 重启后可复用

代码格式：
- Sina格式: sh600686, sz000025, bj430001
- 标准格式: 600686.SH, 000025.SZ, 430001.BJ
- 纯数字: 600686, 000025, 430001
- 显示格式: 600686 (A股), AAPL (美股)
"""

import logging
from typing import Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
import threading
import json
import os

log = logging.getLogger(__name__)


@dataclass
class StockInfo:
    """股票信息"""
    sina_code: str          # sh600686, sz000025
    normalized_code: str    # 600686, 000025
    standard_code: str      # 600686.SH, 000025.SZ
    display_code: str       # 600686, AAPL
    name: str               # 股票名称
    market: str             # market, sh, sz, bj
    stock_type: str         # A, B, US, HK, etc.
    exchange: str            # SSE, SZSE, BJSE

    def to_dict(self) -> Dict:
        return {
            'sina_code': self.sina_code,
            'normalized_code': self.normalized_code,
            'standard_code': self.standard_code,
            'display_code': self.display_code,
            'name': self.name,
            'market': self.market,
            'stock_type': self.stock_type,
            'exchange': self.exchange,
        }


class StockCodeNormalizer:
    """股票代码归一化器"""

    MARKET_MAP = {
        'sh': ('SSE', 'SH'),
        'sz': ('SZSE', 'SZ'),
        'bj': ('BJSE', 'BJ'),
        'us': ('NASDAQ', 'US'),
        'hk': ('HKEX', 'HK'),
    }

    @classmethod
    def parse_sina_code(cls, code: str) -> Tuple[str, str, str]:
        """
        解析 Sina 格式代码

        Args:
            code: Sina格式代码，如 sh600686, sz000025, bj430001

        Returns:
            (market, pure_code, normalized_code)
            如 ('sh', '600686', '600686')
        """
        code = code.lower().strip()
        if len(code) < 3:
            return ('', code, code)

        market = code[:2]
        pure_code = code[2:]

        if market in ('sh', 'sz', 'bj'):
            normalized = pure_code.lstrip('0') or pure_code
        else:
            normalized = pure_code

        return (market, pure_code, normalized)

    @classmethod
    def to_sina_code(cls, code: str) -> str:
        """转换为 Sina 格式"""
        code = code.upper().strip()
        if code.startswith(('SH', 'SZ', 'BJ', 'US', 'HK')):
            if '.' in code:
                prefix, suffix = code.split('.')
                market_map = {'SH': 'sh', 'SZ': 'sz', 'BJ': 'bj', 'US': 'us', 'HK': 'hk'}
                return market_map.get(suffix, 'sh') + prefix.lstrip('0')
            return 'sh' + code.lstrip('0')

        if len(code) == 6 and code.isdigit():
            if code.startswith(('6', '5', '7', '8', '9')):
                return 'sh' + code
            else:
                return 'sz' + code

        return code.lower()

    @classmethod
    def to_standard_code(cls, code: str) -> str:
        """转换为标准格式 600686.SH"""
        sina = cls.to_sina_code(code)
        market, pure, _ = cls.parse_sina_code(sina)
        market_upper = {'sh': 'SH', 'sz': 'SZ', 'bj': 'BJ', 'us': 'US', 'hk': 'HK'}.get(market, 'SH')
        return f"{pure}.{market_upper}"

    @classmethod
    def to_display_code(cls, code: str) -> str:
        """转换为显示格式"""
        sina = cls.to_sina_code(code)
        _, pure, _ = cls.parse_sina_code(sina)
        return pure


class StockInfoRegistry:
    """
    股票信息注册表 - 单例模式

    核心数据结构：
    - _code_to_info: {sina_code -> StockInfo}
    - _normalized_to_sina: {normalized_code -> sina_code}
    - _name_index: {name -> sina_code}
    """

    _instance: Optional['StockInfoRegistry'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        with self._lock:
            if getattr(self, '_initialized', False):
                return

            self._code_to_info: Dict[str, StockInfo] = {}
            self._normalized_to_sina: Dict[str, str] = {}
            self._name_index: Dict[str, Set[str]] = {}
            self._data_lock = threading.RLock()

            self._cache_file = self._get_cache_path()
            self._load_cache()

            self._initialized = True
            log.info(f"[StockInfoRegistry] 初始化完成，已加载 {len(self._code_to_info)} 条股票信息")

    def _get_cache_path(self) -> str:
        """获取缓存文件路径"""
        try:
            from deva.naja.config.file_config import BASE_CONFIG_DIR
            cache_dir = BASE_CONFIG_DIR.parent / "data" / "registry"
            os.makedirs(cache_dir, exist_ok=True)
            return str(cache_dir / "stock_registry.json")
        except Exception:
            return os.path.expanduser("~/.deva/naja_stock_registry.json")

    def _load_cache(self):
        """从缓存文件加载"""
        if not os.path.exists(self._cache_file):
            return
        try:
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for sina_code, info_dict in data.items():
                info = StockInfo(**info_dict)
                self._code_to_info[sina_code] = info
                self._normalized_to_sina[info.normalized_code] = sina_code
                if info.name not in self._name_index:
                    self._name_index[info.name] = set()
                self._name_index[info.name].add(sina_code)
            log.info(f"[StockInfoRegistry] 从缓存加载了 {len(self._code_to_info)} 条股票信息")
        except Exception as e:
            log.warning(f"[StockInfoRegistry] 缓存加载失败: {e}")

    def _save_cache(self):
        """保存缓存到文件"""
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            data = {code: info.to_dict() for code, info in self._code_to_info.items()}
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.debug(f"[StockInfoRegistry] 缓存已保存: {self._cache_file}")
        except Exception as e:
            log.warning(f"[StockInfoRegistry] 缓存保存失败: {e}")

    def register(self, sina_code: str, name: str, market: str = None, stock_type: str = 'A') -> StockInfo:
        """
        注册股票信息

        Args:
            sina_code: Sina格式代码，如 sh600686
            name: 股票名称
            market: 市场，如 sh, sz, bj
            stock_type: 股票类型，A, B, US, HK等

        Returns:
            StockInfo 对象
        """
        with self._data_lock:
            if sina_code in self._code_to_info:
                info = self._code_to_info[sina_code]
                if name and name != info.name:
                    self._update_name_index(info.name, sina_code, name)
                    info.name = name
                return info

            if market is None:
                market = sina_code[:2].lower() if len(sina_code) > 2 else 'sh'

            market_upper, suffix = StockCodeNormalizer.MARKET_MAP.get(market, ('SSE', 'SH'))
            pure_code = sina_code[2:]
            normalized_code = pure_code.lstrip('0') or pure_code
            standard_code = f"{normalized_code}.{suffix}"

            info = StockInfo(
                sina_code=sina_code,
                normalized_code=normalized_code,
                standard_code=standard_code,
                display_code=normalized_code,
                name=name,
                market=market,
                stock_type=stock_type,
                exchange=market_upper,
            )

            self._code_to_info[sina_code] = info
            self._normalized_to_sina[normalized_code] = sina_code
            if name:
                if name not in self._name_index:
                    self._name_index[name] = set()
                self._name_index[name].add(sina_code)

            return info

    def register_batch(self, data: Dict[str, str]):
        """
        批量注册股票信息

        Args:
            data: {sina_code: name} 字典
        """
        count = 0
        for sina_code, name in data.items():
            self.register(sina_code, name)
            count += 1
        if count > 0:
            self._save_cache()
            log.info(f"[StockInfoRegistry] 批量注册了 {count} 条股票信息")

    def _update_name_index(self, old_name: str, sina_code: str, new_name: str):
        """更新名称索引"""
        if old_name in self._name_index:
            self._name_index[old_name].discard(sina_code)
            if not self._name_index[old_name]:
                del self._name_index[old_name]
        if new_name not in self._name_index:
            self._name_index[new_name] = set()
        self._name_index[new_name].add(sina_code)

    def get(self, code: str) -> Optional[StockInfo]:
        """
        获取股票信息

        Args:
            code: 任意格式代码

        Returns:
            StockInfo 或 None
        """
        with self._data_lock:
            sina = StockCodeNormalizer.to_sina_code(code)
            return self._code_to_info.get(sina)

    def get_by_sina_code(self, sina_code: str) -> Optional[StockInfo]:
        """通过 Sina 格式获取"""
        with self._data_lock:
            return self._code_to_info.get(sina_code)

    def get_by_normalized(self, normalized_code: str) -> Optional[StockInfo]:
        """通过归一化代码获取"""
        with self._data_lock:
            sina = self._normalized_to_sina.get(normalized_code)
            if sina:
                return self._code_to_info.get(sina)
            return None

    def get_name(self, code: str) -> str:
        """获取股票名称"""
        info = self.get(code)
        return info.name if info else code

    def get_sina_code(self, code: str) -> str:
        """获取 Sina 格式代码"""
        info = self.get(code)
        return info.sina_code if info else StockCodeNormalizer.to_sina_code(code)

    def normalize(self, code: str) -> str:
        """归一化代码"""
        info = self.get(code)
        return info.normalized_code if info else code.lstrip('sh').lstrip('sz').lstrip('bj').lstrip('SH').lstrip('SZ').lstrip('BJ')

    def to_display(self, code: str) -> str:
        """转换为显示格式"""
        info = self.get(code)
        if info:
            if info.stock_type in ('US', 'HK'):
                return info.display_code
            return info.normalized_code
        return StockCodeNormalizer.to_display_code(code)

    def get_all_codes(self) -> Set[str]:
        """获取所有 Sina 格式代码"""
        with self._data_lock:
            return set(self._code_to_info.keys())

    def get_count(self) -> int:
        """获取注册数量"""
        with self._data_lock:
            return len(self._code_to_info)

    def clear(self):
        """清空注册表"""
        with self._data_lock:
            self._code_to_info.clear()
            self._normalized_to_sina.clear()
            self._name_index.clear()
            log.info("[StockInfoRegistry] 已清空")

    def reset(self):
        """重置单例（用于测试）"""
        with self._lock:
            self._code_to_info.clear()
            self._normalized_to_sina.clear()
            self._name_index.clear()
            StockInfoRegistry._instance = None
            self._initialized = False


def get_stock_registry() -> StockInfoRegistry:
    """获取股票注册表单例"""
    return StockInfoRegistry()


def normalize_stock_code(code: str) -> str:
    """快捷函数：归一化股票代码"""
    return StockCodeNormalizer.to_sina_code(code)


def get_stock_name(code: str) -> str:
    """快捷函数：获取股票名称"""
    return get_stock_registry().get_name(code)
