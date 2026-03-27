"""通达信概念板块数据获取脚本

从 infoharbor_block.dat 文件读取板块数据，返回展开格式的 DataFrame。
"""

import pandas as pd
from pathlib import Path


def fetch_data():
    """获取通达信概念板块数据

    返回展开格式的 DataFrame，每行一个股票-板块组合：
    [
        {'code': '000001', 'blocks': 'AI营销', 'block_count': 3},
        {'code': '000001', 'blocks': '一带一路', 'block_count': 3},
        {'code': '000002', 'blocks': 'AI营销', 'block_count': 2},
        ...
    ]
    """
    blocks_file = Path(__file__).parent.parent.parent.parent / "dictionary" / "infoharbor_block.dat"

    if not blocks_file.exists():
        return pd.DataFrame(columns=['code', 'blocks', 'block_count'])

    stock_to_blocks = {}
    with open(blocks_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            block_name = parts[0]
            codes = parts[1].split(',') if len(parts) > 1 else []

            for code_entry in codes:
                code = code_entry.split('#')[0].strip()
                if code:
                    if code not in stock_to_blocks:
                        stock_to_blocks[code] = set()
                    stock_to_blocks[code].add(block_name)

    rows = []
    for code, blocks in stock_to_blocks.items():
        for block in sorted(blocks):
            rows.append({
                'code': code,
                'blocks': block,
                'block_count': len(blocks)
            })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = fetch_data()
    print(f"Loaded {len(df)} stock-sector records from {df['code'].nunique()} stocks")
    print(df.head(10))
