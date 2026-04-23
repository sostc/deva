"""
Naja 字典模块 - Block 信息统一管理

统一管理 A股和美股的股票基础信息和Block(题材/行业)信息。

数据来源:
- cn_blocks.yaml: A股题材数据
- us_blocks.yaml: 美股行业/题材数据

使用方式:
    from deva.naja.dictionary.blocks import get_blocks_dataframe, get_stock_registry

    # 获取A股题材DataFrame
    df = get_blocks_dataframe(market='CN')

    # 获取美股题材DataFrame
    df = get_blocks_dataframe(market='US')

    # 获取股票注册表
    registry = get_stock_registry()
"""

import os
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import pandas as pd

log = logging.getLogger(__name__)

BLOCKS_DIR = os.path.dirname(os.path.abspath(__file__))

CN_BLOCKS_FILE = os.path.join(BLOCKS_DIR, 'cn_blocks.yaml')
US_BLOCKS_FILE = os.path.join(BLOCKS_DIR, 'us_blocks.yaml')


@dataclass
class BlockInfo:
    """Block信息"""
    block_id: str
    name: str
    market: str
    stocks: List[str]
    industry_code: str = ""
    industry_name: str = ""
    description: str = ""


@dataclass
class StockBasicInfo:
    """股票基础信息"""
    code: str
    name: str
    market: str
    exchange: str
    stock_type: str
    status: str = "active"


class BlockDictionary:
    """
    Block字典管理器

    统一管理A股和美股的Block信息，支持:
    1. 从YAML文件加载Block数据
    2. 提供股票->Block的映射查询
    3. 提供Block->股票的映射查询
    4. 生成兼容市场热点引擎的DataFrame格式
    """

    _instance: Optional['BlockDictionary'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._cn_blocks: Dict[str, BlockInfo] = {}
        self._us_blocks: Dict[str, BlockInfo] = {}
        self._cn_stock_to_blocks: Dict[str, Set[str]] = {}
        self._us_stock_to_blocks: Dict[str, Set[str]] = {}
        self._cn_stocks: Dict[str, StockBasicInfo] = {}
        self._us_stocks: Dict[str, StockBasicInfo] = {}

        self._load_all()
        self._initialized = True
        log.info(f"[BlockDictionary] 初始化完成: A股Block={len(self._cn_blocks)}, 美股Block={len(self._us_blocks)}")

    def _load_all(self):
        """加载所有市场数据"""
        self._load_cn_blocks()
        self._load_us_blocks()
        self._load_stock_registry()

    def _load_cn_blocks(self):
        """加载A股Block数据"""
        if not os.path.exists(CN_BLOCKS_FILE):
            log.warning(f"[BlockDictionary] A股Block文件不存在: {CN_BLOCKS_FILE}")
            return

        try:
            import yaml
            with open(CN_BLOCKS_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                log.warning(f"[BlockDictionary] A股Block文件为空: {CN_BLOCKS_FILE}")
                return

            blocks_list = data.get('blocks', [])
            if not blocks_list:
                log.warning(f"[BlockDictionary] A股Block文件中没有找到blocks数据")
                return

            for block_data in blocks_list:
                block = BlockInfo(
                    block_id=block_data.get('id', block_data.get('name', '')),
                    name=block_data['name'],
                    market='CN',
                    stocks=block_data.get('stocks', []),
                    industry_code=block_data.get('industry_code', ''),
                    industry_name=block_data.get('industry_name', ''),
                    description=block_data.get('description', ''),
                )
                self._cn_blocks[block.block_id] = block

                for stock in block.stocks:
                    if stock not in self._cn_stock_to_blocks:
                        self._cn_stock_to_blocks[stock] = set()
                    self._cn_stock_to_blocks[stock].add(block.block_id)

            log.info(f"[BlockDictionary] 加载A股Block: {len(self._cn_blocks)} 个")

        except Exception as e:
            log.error(f"[BlockDictionary] 加载A股Block失败: {e}")

    def _load_us_blocks(self):
        """加载美股Block数据"""
        if not os.path.exists(US_BLOCKS_FILE):
            log.warning(f"[BlockDictionary] 美股Block文件不存在: {US_BLOCKS_FILE}")
            return

        try:
            import yaml
            with open(US_BLOCKS_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                log.warning(f"[BlockDictionary] 美股Block文件为空: {US_BLOCKS_FILE}")
                return

            blocks_list = data.get('industry_blocks') or data.get('blocks', [])
            if not blocks_list:
                log.warning(f"[BlockDictionary] 美股Block文件中没有找到blocks数据")
                return

            for block_data in blocks_list:
                block = BlockInfo(
                    block_id=block_data.get('id', block_data.get('name', '')),
                    name=block_data['name'],
                    market='US',
                    stocks=block_data.get('stocks', []),
                    industry_code=block_data.get('industry_code', ''),
                    industry_name=block_data.get('industry_name', ''),
                    description=block_data.get('description', ''),
                )
                self._us_blocks[block.block_id] = block

                for stock in block.stocks:
                    if stock not in self._us_stock_to_blocks:
                        self._us_stock_to_blocks[stock] = set()
                    self._us_stock_to_blocks[stock].add(block.block_id)

            log.info(f"[BlockDictionary] 加载美股Block: {len(self._us_blocks)} 个")

        except Exception as e:
            log.error(f"[BlockDictionary] 加载美股Block失败: {e}")

    CN_STOCKS_FILE = os.path.join(BLOCKS_DIR, 'cn_stocks.yaml')
    US_STOCKS_FILE = os.path.join(BLOCKS_DIR, 'us_stocks.yaml')

    def _load_stock_registry(self):
        """从YAML文件加载股票注册表数据"""
        self._load_cn_stocks()
        self._load_us_stocks()

    def _load_cn_stocks(self):
        """加载A股股票基础信息"""
        if not os.path.exists(self.CN_STOCKS_FILE):
            log.warning(f"[BlockDictionary] A股股票文件不存在: {self.CN_STOCKS_FILE}")
            return

        try:
            import yaml
            with open(self.CN_STOCKS_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data or 'stocks' not in data:
                return

            for code, info in data['stocks'].items():
                self._cn_stocks[code] = StockBasicInfo(
                    code=code,
                    name=info.get('name', code),
                    market=self._infer_market(code),
                    exchange=self._infer_exchange(code),
                    stock_type=info.get('stock_type', 'A'),
                    status=info.get('status', 'active')
                )

            log.info(f"[BlockDictionary] 加载A股股票: {len(self._cn_stocks)} 只")

        except Exception as e:
            log.error(f"[BlockDictionary] 加载A股股票失败: {e}")

    def _load_us_stocks(self):
        """加载美股股票基础信息（从us_blocks.yaml的stock_metadata）"""
        try:
            import yaml
            with open(US_BLOCKS_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                return

            stock_metadata = data.get('stock_metadata', {})
            for code, info in stock_metadata.items():
                self._us_stocks[code] = StockBasicInfo(
                    code=code,
                    name=info.get('name', code),
                    market='US',
                    exchange=info.get('exchange', 'NASDAQ'),
                    stock_type='US',
                    status=info.get('status', 'active')
                )

            if not stock_metadata:
                for block in self._us_blocks.values():
                    for code in block.stocks:
                        if code not in self._us_stocks:
                            self._us_stocks[code] = StockBasicInfo(
                                code=code,
                                name=code,
                                market='US',
                                exchange='NASDAQ',
                                stock_type='US'
                            )

            log.info(f"[BlockDictionary] 加载美股股票: {len(self._us_stocks)} 只")

        except Exception as e:
            log.error(f"[BlockDictionary] 加载美股股票失败: {e}")

    def _infer_market(self, code: str) -> str:
        """从代码推断市场"""
        code_lower = code.lower()
        if code_lower.startswith('sh'):
            return 'SH'
        elif code_lower.startswith('sz'):
            return 'SZ'
        elif code_lower.startswith('bj'):
            return 'BJ'
        elif code_lower.startswith('gb_') or code_lower.startswith(('nvda', 'aapl', 'msft', 'amzn', 'googl', 'meta', 'tsla')):
            return 'US'
        return 'UNKNOWN'

    def _infer_exchange(self, code: str) -> str:
        """从代码推断交易所"""
        code_lower = code.lower()
        if code_lower.startswith('sh'):
            return 'SSE'
        elif code_lower.startswith('sz'):
            return 'SZSE'
        elif code_lower.startswith('bj'):
            return 'BJSE'
        return 'UNKNOWN'

    def get_blocks_dataframe(self, market: str = 'CN') -> pd.DataFrame:
        """
        获取Block数据的DataFrame格式

        用于市场热点引擎初始化

        Args:
            market: 'CN' for A股, 'US' for 美股

        Returns:
            DataFrame(columns=['code', 'blocks', 'block_count'])
            - code: 股票代码(新浪格式)
            - blocks: 题材/行业名称
            - block_count: 该股票所属Block数量
        """
        if market == 'CN':
            blocks = self._cn_blocks
            stock_to_blocks = self._cn_stock_to_blocks
        elif market == 'US':
            blocks = self._us_blocks
            stock_to_blocks = self._us_stock_to_blocks
        else:
            raise ValueError(f"不支持的市场: {market}")

        rows = []
        for stock_code, block_ids in stock_to_blocks.items():
            block_names = [blocks[bid].name for bid in block_ids if bid in blocks]
            rows.append({
                'code': stock_code,
                'blocks': '|'.join(block_names) if block_names else '',
                'block_count': len(block_names)
            })

        return pd.DataFrame(rows)

    def get_blocks(self, market: str = 'CN') -> List[BlockInfo]:
        """获取指定市场的所有Block"""
        if market == 'CN':
            return list(self._cn_blocks.values())
        elif market == 'US':
            return list(self._us_blocks.values())
        return []

    def get_block_info(self, block_id: str, market: str = 'CN') -> Optional[BlockInfo]:
        """获取指定Block信息"""
        if market == 'CN':
            return self._cn_blocks.get(block_id)
        elif market == 'US':
            return self._us_blocks.get(block_id)
        return None

    def get_stock_blocks(self, code: str, market: str = 'CN') -> List[str]:
        """获取股票所属的所有Block名称"""
        if market == 'CN':
            stock_to_blocks = self._cn_stock_to_blocks
            blocks = self._cn_blocks
        elif market == 'US':
            stock_to_blocks = self._us_stock_to_blocks
            blocks = self._us_blocks
        else:
            return []

        block_ids = stock_to_blocks.get(code, set())
        return [blocks[bid].name for bid in block_ids if bid in blocks]

    def get_block_stocks(self, block_id: str, market: str = 'CN') -> List[str]:
        """获取Block包含的所有股票"""
        block = self.get_block_info(block_id, market)
        return block.stocks if block else []

    def get_all_stocks(self, market: str = 'CN') -> Set[str]:
        """获取指定市场的所有股票代码（仅包含在stocks字典中有记录的）"""
        if market == 'CN':
            return set(self._cn_stocks.keys())
        elif market == 'US':
            return set(self._us_stocks.keys())
        return set()

    def get_active_stocks(self, market: str = 'CN') -> Set[str]:
        """获取指定市场的活跃股票代码（排除退市和停牌）"""
        if market == 'CN':
            stocks = self._cn_stocks
        elif market == 'US':
            stocks = self._us_stocks
        else:
            return set()

        return {
            code for code, info in stocks.items()
            if info.status == 'active'
        }

    def update_stock_status(self, code: str, status: str):
        """更新股票状态"""
        code_lower = code.lower()
        if code_lower in self._cn_stocks:
            self._cn_stocks[code_lower].status = status
        elif code_lower in self._us_stocks:
            self._us_stocks[code_lower].status = status

    def get_stock_info(self, code: str) -> Optional[StockBasicInfo]:
        """获取股票基础信息"""
        code_lower = code.lower()
        if code_lower.startswith(('sh', 'sz', 'bj')):
            return self._cn_stocks.get(code_lower)
        else:
            return self._us_stocks.get(code_lower)

    def get_stock_name(self, code: str) -> str:
        """获取股票名称"""
        info = self.get_stock_info(code)
        return info.name if info else code

    def reload(self, market: Optional[str] = None):
        """
        重新加载数据

        Args:
            market: None=全部, 'CN'=仅A股, 'US'=仅美股
        """
        if market is None or market == 'CN':
            self._cn_blocks.clear()
            self._cn_stock_to_blocks.clear()
            self._load_cn_blocks()

        if market is None or market == 'US':
            self._us_blocks.clear()
            self._us_stock_to_blocks.clear()
            self._load_us_blocks()

        log.info(f"[BlockDictionary] 重新加载完成: CN={len(self._cn_blocks)}, US={len(self._us_blocks)}")


_block_dictionary: Optional[BlockDictionary] = None


def get_block_dictionary() -> BlockDictionary:
    """获取Block字典单例"""
    global _block_dictionary
    if _block_dictionary is None:
        _block_dictionary = BlockDictionary()
    return _block_dictionary


def get_blocks_dataframe(market: str = 'CN') -> pd.DataFrame:
    """快捷函数：获取Block数据的DataFrame"""
    return get_block_dictionary().get_blocks_dataframe(market)


def get_stock_blocks(code: str, market: str = 'CN') -> List[str]:
    """快捷函数：获取股票所属的Block"""
    return get_block_dictionary().get_stock_blocks(code, market)


def get_block_stocks(block_id: str, market: str = 'CN') -> List[str]:
    """快捷函数：获取Block包含的股票"""
    return get_block_dictionary().get_block_stocks(block_id, market)


def get_block_info(block_id: str, market: str = 'CN') -> Optional[BlockInfo]:
    """快捷函数：获取Block信息"""
    return get_block_dictionary().get_block_info(block_id, market)


def get_all_blocks(market: str = 'CN') -> List[BlockInfo]:
    """快捷函数：获取指定市场的所有Block"""
    return get_block_dictionary().get_blocks(market)


def get_active_stocks(market: str = 'CN') -> Set[str]:
    """快捷函数：获取指定市场的活跃股票代码"""
    return get_block_dictionary().get_active_stocks(market)


def get_stock_info(code: str) -> Optional[StockBasicInfo]:
    """快捷函数：获取股票基础信息"""
    return get_block_dictionary().get_stock_info(code)


def get_stock_name(code: str) -> str:
    """快捷函数：获取股票名称"""
    return get_block_dictionary().get_stock_name(code)


class StockRegistry:
    """
    股票信息注册表 - 兼容层

    兼容原有 stock_registry.py 的接口，但底层使用 YAML 数据源
    """

    _instance: Optional['StockRegistry'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._block_dict = get_block_dictionary()
        self._initialized = True

    def get_name(self, code: str) -> str:
        """获取股票名称"""
        return self._block_dict.get_stock_name(code)

    def get_info(self, code: str) -> Optional[StockBasicInfo]:
        """获取股票信息"""
        return self._block_dict.get_stock_info(code)

    def get_stock_info(self, code: str) -> Optional[StockBasicInfo]:
        """获取股票信息"""
        return self._block_dict.get_stock_info(code)


_stock_registry: Optional[StockRegistry] = None


def get_stock_registry() -> StockRegistry:
    """获取股票注册表单例"""
    global _stock_registry
    if _stock_registry is None:
        _stock_registry = StockRegistry()
    return _stock_registry