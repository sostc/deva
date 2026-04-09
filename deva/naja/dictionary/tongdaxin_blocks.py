"""通达信概念题材数据解析和查询工具"""

import os
import re
from pathlib import Path
from typing import Dict, Generator, List, Set

_blocks_data = None
_stock_to_blocks = None
_block_info = None

BLOCKS_FILE = os.environ.get(
    "TONGDAXIN_BLOCKS_FILE",
    str(Path(__file__).resolve().parent / "infoharbor_block.dat")
)

MARKET_NAMES = {
    "0": "深圳",
    "1": "上海",
    "2": "北京",
}

MARKET_PREFIX = {
    "深圳": "0",
    "上海": "1",
    "北京": "2",
}


def normalize_stock_code(code: str) -> str:
    text = str(code or "").strip()
    if not text:
        return ""
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    m = re.search(r"(\d{6})", text)
    if m:
        return m.group(1)
    return text


def _parse_blocks_file(filepath: str = None):
    global _blocks_data, _stock_to_blocks, _block_info
    
    if _blocks_data is not None:
        return
    
    filepath = filepath or BLOCKS_FILE
    blocks = []
    current_block = None
    
    with open(filepath, 'r', encoding='gbk', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('#GN_'):
                if current_block:
                    blocks.append(current_block)
                
                parts = line.split(',')
                block_name = parts[0][4:]
                stock_count = int(parts[1]) if parts[1] else 0
                block_id = parts[2]
                start_date = parts[3] if len(parts) > 3 else ''
                end_date = parts[4] if len(parts) > 4 else ''
                
                current_block = {
                    'name': block_name,
                    'stock_count': stock_count,
                    'block_id': block_id,
                    'start_date': start_date,
                    'end_date': end_date,
                    'stocks': []
                }
            elif current_block and line:
                stocks = [s.strip() for s in line.split(',') if s.strip()]
                for stock in stocks:
                    if '#' in stock:
                        prefix, code = stock.split('#')
                        current_block['stocks'].append({
                            'prefix': prefix,
                            'code': normalize_stock_code(code),
                            'full': stock
                        })
        
        if current_block:
            blocks.append(current_block)
    
    _blocks_data = blocks
    
    stock_to_blocks = {}
    block_info = {}
    
    for block in blocks:
        block_key = block['name']
        block_info[block_key] = {
            'name': block['name'],
            'stock_count': len(block['stocks']),
            'block_id': block['block_id'],
            'start_date': block['start_date'],
            'end_date': block['end_date'],
        }
        
        for stock in block['stocks']:
            code = stock['code']
            if code not in stock_to_blocks:
                stock_to_blocks[code] = set()
            stock_to_blocks[code].add(block_key)
    
    _stock_to_blocks = stock_to_blocks
    _block_info = block_info


def get_stock_blocks(code: str) -> List[str]:
    """获取股票所属的所有题材
    
    Args:
        code: 股票代码 (如 '000001', '600000')
    
    Returns:
        题材名称列表
    """
    _parse_blocks_file()
    normalized = normalize_stock_code(code)
    return sorted(list(_stock_to_blocks.get(normalized, set())))


def get_block_info(block_name: str) -> Dict:
    """获取题材的详细信息
    
    Args:
        block_name: 题材名称 (如 '人工智能', '新能源车')
    
    Returns:
        题材信息字典，包含 name, stock_count, block_id, start_date, end_date
    """
    _parse_blocks_file()
    return _block_info.get(block_name, {})


def get_block_stocks(block_name: str) -> List[str]:
    """获取题材包含的所有股票代码
    
    Args:
        block_name: 题材名称
    
    Returns:
        股票代码列表
    """
    _parse_blocks_file()
    for block in _blocks_data:
        if block['name'] == block_name:
            return [s['code'] for s in block['stocks']]
    return []


def get_all_blocks() -> List[str]:
    """获取所有题材名称
    
    Returns:
        题材名称列表
    """
    _parse_blocks_file()
    return sorted([b['name'] for b in _blocks_data])


def get_blocks_by_keyword(keyword: str) -> List[str]:
    """根据关键词搜索题材
    
    Args:
        keyword: 关键词
    
    Returns:
        匹配的题材名称列表
    """
    _parse_blocks_file()
    keyword = keyword.lower()
    return [b for b in get_all_blocks() if keyword in b.lower()]


def reload_blocks(filepath: str = None):
    """重新加载题材数据
    
    Args:
        filepath: 可选的题材数据文件路径
    """
    global _blocks_data, _stock_to_blocks, _block_info
    _blocks_data = None
    _stock_to_blocks = None
    _block_info = None
    _parse_blocks_file(filepath)


def get_dataframe(filepath: str = None) -> "pd.DataFrame":
    """获取题材数据的 DataFrame 格式
    
    Args:
        filepath: 可选的文件路径，不提供则使用默认路径
    
    Returns:
        pandas DataFrame，包含 code, blocks 列
    """
    import pandas as pd
    
    filepath = filepath or BLOCKS_FILE
    
    stock_to_blocks = {}
    
    with open(filepath, 'r', encoding='gbk', errors='ignore') as f:
        current_block = None
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('#GN_'):
                parts = line.split(',')
                block_name = parts[0][4:]
                current_block = block_name
            elif current_block and line:
                stocks = [s.strip() for s in line.split(',') if s.strip()]
                for stock in stocks:
                    if '#' in stock:
                        prefix, code = stock.split('#')
                        code = normalize_stock_code(code)
                        if code not in stock_to_blocks:
                            stock_to_blocks[code] = set()
                        stock_to_blocks[code].add(current_block)
    
    rows = []
    for code, blocks in stock_to_blocks.items():
        for block in sorted(blocks):
            rows.append({
                'code': code,
                'blocks': block,
                'block_count': len(blocks)
            })

    return pd.DataFrame(rows)


def get_stock_block_mapping() -> Dict[str, Set[str]]:
    """获取股票代码到题材的映射字典
    
    Returns:
        {股票代码: {题材名称集合}}
    """
    _parse_blocks_file()
    return _stock_to_blocks.copy()


__all__ = [
    'get_stock_blocks',
    'get_block_info',
    'get_block_stocks',
    'get_all_blocks',
    'get_blocks_by_keyword',
    'reload_blocks',
    'get_dataframe',
    'get_stock_block_mapping',
    'BLOCKS_FILE',
]
