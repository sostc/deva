"""Dictionary 工具函数"""

from __future__ import annotations

import pandas as pd

from deva.naja.register import SR


def create_tongdaxin_blocks_dict(
    name: str = "通达信概念题材", 
    interval_seconds: int = 86400,
    blocks_file: str = None
) -> dict:
    """创建通达信概念题材字典
    
    鲜活任务会定期读取 infoharbor_block.dat 文件来更新数据
    
    Args:
        name: 字典名称
        interval_seconds: 自动刷新间隔（秒），默认24小时
        blocks_file: 题材数据文件路径，默认使用项目根目录的 infoharbor_block.dat
    
    Returns:
        创建结果
    """
    from pathlib import Path
    from deva.naja.dictionary.tongdaxin_blocks import BLOCKS_FILE
    
    file_path = blocks_file or BLOCKS_FILE
    
    func_code = f'''import pandas as pd
from pathlib import Path

def fetch_data():
    blocks_file = "{file_path}"
    from deva.naja.dictionary.tongdaxin_blocks import get_dataframe
    return get_dataframe(filepath=blocks_file)
'''
    
    mgr = SR('dictionary_manager')
    return mgr.create(
        name=name,
        description=f"通达信概念题材数据，从 {Path(file_path).name} 文件读取，包含股票与所属题材的映射关系",
        dict_type="stock_basic_block",
        source_mode="task",
        func_code=func_code,
        execution_mode="timer",
        interval_seconds=interval_seconds,
    )


def enrich_stock_with_blocks(df: pd.DataFrame, code_column: str = "code") -> pd.DataFrame:
    """为股票DataFrame补充题材信息（展开格式，每行一个股票-题材组合）

    Args:
        df: 包含股票代码的DataFrame
        code_column: 股票代码列名

    Returns:
        补充了blocks列的DataFrame，每行是一个股票-题材组合
    """
    from .tongdaxin_blocks import get_stock_blocks

    df = df.copy()
    df[code_column] = df[code_column].astype(str).str.zfill(6)

    block_data = []
    for _, row in df.iterrows():
        code = row[code_column]
        blocks = get_stock_blocks(code)
        for block in blocks:
            block_data.append({
                code_column: code,
                'blocks': block,
                'block_count': len(blocks)
            })

    if not block_data:
        df['blocks'] = ''
        df['block_count'] = 0
        return df

    result_df = pd.DataFrame(block_data)
    result_df = result_df.merge(df.drop(columns=['blocks', 'block_count'], errors='ignore'),
                                 on=code_column, how='left')
    return result_df
