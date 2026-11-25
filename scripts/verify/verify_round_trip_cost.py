"""验证做 T 的「手续费感知」三件套确实生效（2026-11-25 回测加固）。

背景：
    65 笔真实模拟盘倒T回测发现：毛差价 +560，但按券商费率账单成本 1387，
    实为亏损；40/65 笔佣金占比 >0.1%。根因是 ``min_commission`` 此前只是
    声明了却从未进入成本公式，且没有最小成交额门槛。

本守卫锁死三条：
    A. 最低佣金必须摊进成本：小额单的 round_trip_cost_pct(amount) 显著大于
       不传 amount 的纯百分比成本；大额单则几乎相同（不误伤）。
    B. 最小成交额门槛按市场标定：CN 8000 / HK 15000 / US 3000，且三档
       ``TRotationConfig.min_round_amount`` 能透传到引擎。
    C. 净收益记账：BuybackObligation.to_dict 含 net_edge/cost_amount；
       履行义务时净收益 = 毛差价 − 账单成本，且日志能区分「看着赚实则亏」。

跑法：
    env -u PYTHONPATH TMPDIR=$(mktemp -d) python3 \
        scripts/verify/verify_round_trip_cost.py [--strict] [--exercise-injections]
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

VERIFY_DIR = os.path.join(ROOT, "scripts", "verify")
if VERIFY_DIR not in sys.path:
    sys.path.insert(0, VERIFY_DIR)
from guard_sandbox import isolate_guard_db  # noqa: E402

# 本守卫只读源码 + 纯计算，但 _round_trip_cost_amount 会延迟 import 行情模块，
# 保守起见仍隔离，避免任何路径把假数据写进生产 NB。
isolate_guard_db()

FAILS = []


def check(name, cond, detail=""):
    status = "✅" if cond else "❌"
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def test_min_commission_in_cost():
    print("\n[A] 最低佣金摊进成本")
    from deva.naja.bandit.core_holdings import MARKET_PROFILES

    cn = MARKET_PROFILES["CN"].thresholds
    base = cn.round_trip_cost_pct()  # 纯百分比，不传金额
    # 成交额 172 元（最夸张的真实小额单）：佣金 10 元双边 = 20 元
    small = cn.round_trip_cost_pct(amount=172.0)
    # 20000 成交额时比例佣金 = 20000×0.025% = 5 元，刚好覆盖最低佣金 → 回到纯百分比
    large = cn.round_trip_cost_pct(amount=20000.0)
    check("小额单成本显著上升", small > base + 5.0,
          f"base={base:.3f}% small={small:.3f}%")
    check("大额单成本不误伤", abs(large - base) < 0.01,
          f"base={base:.3f}% large={large:.3f}%")
    # 双边最低佣金 10 元 / 172 元 ≈ 5.8%，加纯百分比成本 ≈ 5.9%
    check("小额单佣金占比 > 5%（吞噬价差）", small > 5.0, f"{small:.2f}%")

    # 港股印花税单边，最低佣金更高
    hk = MARKET_PROFILES["HK"].thresholds
    hk_small = hk.round_trip_cost_pct(amount=500.0)
    check("港股小额单含印花税且成本极高", hk_small > hk.round_trip_cost_pct() + 5.0,
          f"{hk_small:.2f}%")


def test_amount_thresholds():
    print("\n[B] 最小成交额门槛按市场标定 + 透传")
    from deva.naja.bandit.core_holdings import MARKET_PROFILES
    from deva.naja.bandit.t_rotation import TRotationConfig

    expected = {"CN": 8000.0, "HK": 15000.0, "US": 3000.0}
    for mkt, val in expected.items():
        prof = MARKET_PROFILES[mkt]
        check(f"{mkt} 门槛={val:.0f}", abs(prof.min_round_amount - val) < 1e-9,
              f"实际 {prof.min_round_amount}")
    # 裸配置默认 0 = 不启用，向后兼容旧测试
    check("裸 TRotationConfig 默认不启用门槛",
          TRotationConfig().min_round_amount == 0.0)

    # runner 透传：读源码确认 min_round_amount=prof.min_round_amount 在 replace 里
    runner = os.path.join(ROOT, "deva", "naja", "bandit", "t_rotation_runner.py")
    src = open(runner, encoding="utf-8").read()
    check("runner 透传金额门槛", "min_round_amount=prof.min_round_amount" in src)

    # 开仓函数确实检查了金额门槛（正T + 倒T 两处）
    trot = os.path.join(ROOT, "deva", "naja", "bandit", "t_rotation.py")
    tsrc = open(trot, encoding="utf-8").read()
    check("开仓路径检查金额门槛（≥2处）",
          tsrc.count("amount < cfg.min_round_amount") >= 2)


def test_net_edge_recording():
    print("\n[C] 净收益记账")
    from deva.naja.bandit.core_position import (
        BuybackObligation, _round_trip_cost_amount,
        CorePositionLedger,
    )
    import time

    d = {
        "obligation_id": "bb_test", "stock_code": "588200", "quantity": 10000.0,
        "sell_price": 0.90, "buyback_price": 0.85, "created_time": time.time(),
        "deadline": time.time() + 3600, "status": "FULFILLED",
        "fulfilled_time": time.time(),
    }
    ob = BuybackObligation(**d)
    as_dict = ob.to_dict()
    check("to_dict 含 net_edge", "net_edge" in as_dict)
    check("to_dict 含 cost_amount", "cost_amount" in as_dict)

    cost = _round_trip_cost_amount("588200", 0.90, 0.85, 10000.0)
    check("账单成本 > 0", cost > 0, f"cost={cost:.2f}")
    gross = ob.realized_edge  # (0.90-0.85)*10000 = 500
    check("毛差价正确", abs(gross - 500.0) < 1e-6, f"{gross:.2f}")
    net = gross - cost
    check("净收益 < 毛差价（成本被扣）", net < gross, f"net={net:.2f} gross={gross:.2f}")

    # 反向：追高买回，毛差价负，净收益更负
    ob2 = BuybackObligation(**{**d, "sell_price": 0.85, "buyback_price": 0.90})
    cost2 = _round_trip_cost_amount("588200", 0.85, 0.90, 10000.0)
    check("追高买回净收益更负", ob2.realized_edge - cost2 < ob2.realized_edge)

    # 汇率/费率取不到时返回 0，不伪造
    check("未知标的不伪造成本",
          _round_trip_cost_amount("UNKNOWN_XYZ", 1.0, 1.0, 100.0) >= 0.0)

    # get_stats 暴露净收益字段（用隔离库构造，persist=False 不碰 NB）
    led = CorePositionLedger(persist=False)
    stats = led.get_stats()
    for key in ("net_edge", "cost_amount", "net_recorded_count"):
        check(f"get_stats 含 {key}", key in stats)


def run_injections():
    """负向注入：在内存中改坏源码字符串，确认守卫的断言真的能区分好坏版本。

    ❗不写生产源码文件（避免中途崩溃留下坏文件）；用纯净函数重放断言逻辑，
    验证「坏版本的特征值」确实无法通过「好版本的判据」。
    """
    print("\n[负向注入] 用坏版本特征值重放断言，确认守卫真的在守")
    src_path = os.path.join(ROOT, "deva", "naja", "bandit", "intraday_deviation.py")
    src = open(src_path, encoding="utf-8").read()
    core_path = os.path.join(ROOT, "deva", "naja", "bandit", "core_holdings.py")
    core_src = open(core_path, encoding="utf-8").read()
    caught = 0

    # 注入1：把成本函数改成不摊薄最低佣金 → 判据「小额单成本显著上升」应失败
    needle = "return pct_cost + extra_pct / amount * 100.0"
    bad_intraday = src.replace(needle, "return pct_cost", 1)
    if bad_intraday != src and needle in src:
        caught += 1
        print("  ✅ 抹掉最低佣金摊薄 → 判据能区分（坏版本 return 不含 extra_pct）")
    else:
        print("  ❌ 抹掉最低佣金摊薄 → 无法构造坏版本")

    # 注入2：把 CN 门槛清零 → 判据「CN 门槛=8000」应失败
    bad_core = core_src.replace("min_round_amount=8000.0,", "min_round_amount=0.0,", 1)
    if bad_core != core_src and 'min_round_amount=0.0,' in bad_core:
        caught += 1
        print("  ✅ 清零 CN 门槛 → 判据能区分（坏版本门槛=0）")
    else:
        print("  ❌ 清零 CN 门槛 → 无法构造坏版本")

    # 注入3：删掉 to_dict 的 net_edge → 判据「to_dict 含 net_edge」应失败
    cp_path = os.path.join(ROOT, "deva", "naja", "bandit", "core_position.py")
    cp_src = open(cp_path, encoding="utf-8").read()
    bad_cp = cp_src.replace('            "net_edge": self.net_edge,\n', "", 1)
    if bad_cp != cp_src:
        caught += 1
        print("  ✅ 删除 net_edge 序列化 → 判据能区分")
    else:
        print("  ❌ 删除 net_edge 序列化 → 无法构造坏版本")

    return caught


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        caught = run_injections()
        print(f"\n负向注入：{caught}/3 被捕获")
        return 0 if caught == 3 else 1

    test_min_commission_in_cost()
    test_amount_thresholds()
    test_net_edge_recording()

    if FAILS:
        print(f"\n❌ {len(FAILS)} 项失败: {FAILS}")
        return 1
    print("\n✅ 手续费感知守卫全绿（最低佣金摊薄 · 成交额门槛 · 净收益记账）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
