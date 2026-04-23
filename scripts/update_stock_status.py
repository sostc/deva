#!/usr/bin/env python3
"""
批量检测股票状态脚本

从 Sina 获取股票数据，判断状态：
- active: 正常交易
- suspended: 停牌 (now=0.0 但有完整数据)
- delisted: 退市 (返回空数据)

用法:
    python scripts/update_stock_status.py
"""

import asyncio
import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

log = logging.getLogger(__name__)

BATCH_SIZE = 100


def _parse_batch_status(text: str, codes: list) -> dict:
    """解析批量股票状态"""
    result = {code: 'unknown' for code in codes}

    if not text or not text.strip():
        return result

    for line in text.strip().split('\n'):
        if not line or '="' not in line:
            continue
        try:
            parts = line.split('="')
            if len(parts) < 2:
                continue

            prefix = parts[0]
            code = prefix.split('_')[-1]

            if code not in result:
                continue

            data = parts[1].rstrip('"')
            if not data:
                result[code] = 'delisted'
                continue

            fields = data.split(',')
            if len(fields) < 33:
                result[code] = 'delisted'
                continue

            now = float(fields[3]) if fields[3] else 0.0
            if now == 0.0:
                result[code] = 'suspended'
            else:
                result[code] = 'active'
        except Exception:
            continue

    return result


async def check_batch(session, codes: list) -> dict:
    """检查一批股票状态"""
    import aiohttp

    codes_str = ','.join(codes)
    url = f'https://hq.sinajs.cn/list={codes_str}'
    headers = {
        'Referer': 'https://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return {code: 'unknown' for code in codes}
            text = await resp.text()
            return _parse_batch_status(text, codes)
    except Exception as e:
        log.warning(f"批次检查失败: {e}")
        return {code: 'unknown' for code in codes}


async def update_cn_stock_status():
    """更新A股股票状态"""
    from deva.naja.dictionary.blocks import get_block_dictionary

    bd = get_block_dictionary()
    all_codes = list(bd.get_all_stocks('CN'))
    total = len(all_codes)

    print(f"开始检测 {total} 只A股状态...")

    status_count = {'active': 0, 'suspended': 0, 'delisted': 0, 'unknown': 0}
    import aiohttp

    async with aiohttp.ClientSession() as session:
        for i in range(0, total, BATCH_SIZE):
            batch = all_codes[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

            result = await check_batch(session, batch)

            for code, status in result.items():
                bd.update_stock_status(code, status)
                status_count[status] = status_count.get(status, 0) + 1

            print(f"批次 {batch_num}/{total_batches} 完成: {status_count}")
            await asyncio.sleep(0.3)

    print(f"\n检测完成!")
    print(f"  正常交易: {status_count['active']}")
    print(f"  停牌: {status_count['suspended']}")
    print(f"  退市: {status_count['delisted']}")
    print(f"  未知: {status_count['unknown']}")

    return status_count


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s][%(levelname)s] %(message)s'
    )

    start = time.time()
    status = asyncio.run(update_cn_stock_status())
    elapsed = time.time() - start

    print(f"\n耗时: {elapsed:.1f}秒")


if __name__ == '__main__':
    main()