"""SimHash 64bit 指纹（**默认不启用**）。

只被 ``dedup.DedupConfig(enable_fuzzy=True)`` 调用。单独成文件是为了
"关掉时零成本"：惰性导入，关闭状态下连模块都不加载。

为什么不默认开：实测 113 条新闻只多合 1 条，耗时却是精确+配对的 10 倍，
而且会把统计局发布会里两条**不同要点**的新闻误合成一条。它唯一擅长的
"截断版/改写版"在本项目的新闻源里并不存在（金十重发是逐字相同，交给
``L1`` 即可）。留着是为了将来接公众号/多源聚合时有现成的开关。
"""

from __future__ import annotations

import zlib

_BITS = 64


def simhash64(text: str, bits: int = _BITS) -> int:
    """字符 2-gram 的 SimHash。纯整数运算，不依赖任何第三方库。"""
    s = text or ""
    if not s:
        return 0
    if len(s) <= 2:
        return zlib.crc32(s.encode())
    vec = [0] * bits
    for i in range(len(s) - 1):
        h = zlib.crc32(s[i:i + 2].encode())
        for b in range(bits):
            vec[b] += 1 if (h >> b) & 1 else -1
    out = 0
    for b in range(bits):
        if vec[b] > 0:
            out |= 1 << b
    return out


def hamming(a: int, b: int) -> int:
    """汉明距离（Brian Kernighan 数位数）。"""
    x = (a ^ b) & ((1 << _BITS) - 1)
    n = 0
    while x:
        n += 1
        x &= x - 1
    return n


__all__ = ["hamming", "simhash64"]
