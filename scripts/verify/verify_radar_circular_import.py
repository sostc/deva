#!/usr/bin/env python3
"""回归：radar / market_hotspot / bandit 的循环导入。

背景：
    market_hotspot.data.global_market_futures 在模块中途反向 import
    deva.naja.bandit.stock_block_map，而 bandit → radar → radar.global_market_scanner
    又回头要这个半初始化的模块，于是全新解释器下
        import deva.naja.market_hotspot.data
    直接 ImportError。修法是把 radar/__init__.py 的 global_market_scanner
    改为惰性（PEP 562）导出。

本脚本在**干净子进程**里逐个验证导入顺序（同一解释器有 sys.modules 缓存，
测不出问题，必须新进程）。同时确认惰性重导出仍可用。

跑法（必须清环境，避免被注入的 shim 干扰）：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_radar_circular_import.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 每个 case 都是独立子进程里执行的完整语句序列
CASES = [
    # 原先必然失败的场景
    "import deva.naja.market_hotspot.data",
    "import deva.naja.market_hotspot",
    "import deva.naja.market_hotspot.data.realtime_fetcher",
    "import deva.naja.market_hotspot.data.global_market_futures",
    # 反向顺序
    "import deva.naja.bandit; import deva.naja.market_hotspot.data",
    "import deva.naja.radar; import deva.naja.market_hotspot.data",
    "import deva.naja.market_hotspot.data; import deva.naja.radar",
    "import deva.naja.market_hotspot.data; import deva.naja.bandit",
    # 惰性重导出仍需可用（PEP 562）
    "from deva.naja.radar import GlobalMarketScanner, get_global_market_scanner, "
    "MarketAlert, MarketVolatilityTracker, ScanConfig",
    "import deva.naja.radar as r; r.GlobalMarketScanner; r.get_global_market_scanner",
    # 惰性导出触发后再导入 market_hotspot（验证不反向破环）
    "from deva.naja.radar import GlobalMarketScanner; "
    "import deva.naja.market_hotspot.data.global_market_futures",
]

PROBE = "print('IMPORT_CASE_OK')"


def run_case(code: str):
    full = f"import sys; sys.path.insert(0, {ROOT!r}); {code}; {PROBE}"
    proc = subprocess.run(
        [sys.executable, "-c", full],
        capture_output=True, text=True, env=os.environ.copy(),
    )
    ok = proc.returncode == 0 and "IMPORT_CASE_OK" in proc.stdout
    return ok, (proc.stderr or proc.stdout).strip().splitlines()[-1:] if not ok else ""


def main():
    failures = []
    for code in CASES:
        ok, err = run_case(code)
        label = code if len(code) <= 72 else code[:69] + "..."
        if ok:
            print(f"1) OK  {label}")
        else:
            print(f"1) FAIL {label}\n      -> {err}")
            failures.append(code)

    if failures:
        print(f"\n{len(failures)} CASE(S) FAILED")
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
