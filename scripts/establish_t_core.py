"""一次性建仓：在三个富途模拟仓里建立做 T 底仓。

用法（cwd = 仓库根）::
    python scripts/establish_t_core.py --probe                 # 每市场试探 1 手
    python scripts/establish_t_core.py --build                 # 建到目标份额
    python scripts/establish_t_core.py --build --only CN --slip 0.01 --max-amount 100000

目标 = 该市场账户总资产 × 40%（alloc_pct 默认值，用户拍板过）÷ 现价，
按每手取整。**休市的市场自动跳过**（不下无效单）。

``--slip``：限价上浮比例。休市/午休期间下的单要等开盘撮合，限价贴在现价
上很可能被开盘一跳穿过去，上浮一点换"确实成交"。
``--max-amount``：单批金额上限（本币）。40% 一次挂满风险太大，分批补。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deva.naja.bandit.core_holdings import load_core_holdings
from deva.naja.bandit.futu_portfolio_syncer import FutuPortfolioSyncer  # noqa
from deva.naja.bandit.futu_quote_source import FutuQuoteSource
from deva.naja.bandit.futu_sim_portfolio import FutuSimPortfolio
from deva.naja.bandit.market_session import market_phase, minutes_to_close

ALLOC_PCT = 40.0


def build(spec, pf: FutuSimPortfolio, quotes: FutuQuoteSource, probe: bool,
          slip: float = 0.0, max_amount: float = 0.0):
    market = spec.market
    phase = market_phase(market, datetime.now())
    if phase == "closed":
        print(f"⏭️  {market} {spec.code} 已休市，跳过（不下无效单）")
        return

    q = quotes.fetch([(spec.code, market)]).get(spec.code)
    if q is None or not q.ok or q.current <= 0:
        print(f"❌ {market} {spec.code} 取不到行情: {getattr(q, 'error', '无返回')}")
        return

    summary = pf.get_summary()
    total = float(summary.get("total_capital", 0.0) or 0.0)
    cash = float(summary.get("available_capital", 0.0) or 0.0)
    held = sum(
        p.quantity for p in pf.get_positions_by_stock(spec.code)
    )
    raw_price = q.current
    # 休市/午休时下的单要等开盘撮合，限价贴在现价上很可能不成交
    # （开盘一跳就穿过去）。上浮一点换取"确实成交"。
    price = round(raw_price * (1 + slip), 3) if slip > 0 else raw_price
    lot = spec.round_lot

    target = (total * ALLOC_PCT / 100.0) / price
    target = int(target / lot) * lot
    missing = target - held

    print(
        f"\n[{market}] {spec.code} {spec.name} 现价={price:.3f} 每手={lot:g}\n"
        f"   账户总资产={total:,.0f} {summary.get('currency')} 现金={cash:,.0f}\n"
        f"   目标={target:,.0f} 份（总资产 {ALLOC_PCT:g}%） 已持有={held:,.0f} 缺={missing:,.0f}"
    )

    if probe:
        qty = lot
        print(f"   —— 试探模式：只买 {qty:g} 份（{qty * price:,.0f}）")
    else:
        if missing <= 0:
            print("   ✅ 底仓已到位，无需建仓")
            return
        qty = int(missing / lot) * lot
        # 分批：一次挂满 40% 的单子风险太大（开盘一跳就可能整笔废掉），
        # 交给后续轮次继续补。
        if max_amount > 0:
            cap_qty = int(max_amount / price / lot) * lot
            if qty > cap_qty:
                print(f"   ℹ️ 分批：本批只买 {cap_qty:g} 份（上限 {max_amount:,.0f} 本币）")
                qty = cap_qty
        if qty * price > cash:
            qty = int((cash * 0.95) / price / lot) * lot
            print(f"   ⚠️ 现金不足，按可用资金下调到 {qty:g} 份")
        if qty <= 0:
            print("   ❌ 资金不足，买不起一手")
            return

    pf.set_slot_tag(f"establish_{time.strftime('%Y%m%d')}_{int(time.time() // 60)}")
    pos = pf.open_position(
        strategy_id="core_position",
        strategy_name="长期底仓",
        stock_code=spec.code,
        stock_name=spec.name,
        price=price,
        quantity=qty,
    )
    if pos is None:
        print(f"   ❌ 建仓失败: {pf.last_error}")
        return
    print(f"   ✅ 已买 {qty:g} 份 @{price:.3f}，当前持有 {pos.quantity:,.0f} 份")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--slip", type=float, default=0.0, help="限价上浮比例，如 0.01")
    ap.add_argument("--max-amount", type=float, default=0.0, help="单批金额上限（本币）")
    ap.add_argument("--only", default="", help="只做这些市场，逗号分隔，如 CN,US")
    args = ap.parse_args()
    if not (args.probe or args.build):
        ap.error("必须指定 --probe 或 --build")

    os.environ.setdefault("NAJA_T_ROTATION_SYMBOLS", "588200,HK:00700,US:QQQ")
    only = {m.strip().upper() for m in args.only.split(",") if m.strip()}

    quotes = FutuQuoteSource()
    for spec in load_core_holdings():
        if only and spec.market not in only:
            continue
        try:
            build(spec, FutuSimPortfolio(spec.market), quotes, probe=args.probe,
                  slip=args.slip, max_amount=args.max_amount)
        except Exception as e:
            print(f"🚨 {spec.market} {spec.code} 建仓异常: {e}")


main()
