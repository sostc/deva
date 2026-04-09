#!/usr/bin/env python3
"""
条件选股

功能：根据价格、市值、PE、涨跌幅等条件筛选股票
用法：python get_stock_filter.py --market HK --min-price 10 --max-price 100

接口限制：
- 港股 BMP 权限不支持
- 每 30 秒内最多请求 10 次
- 每页最多返回 200 个结果

参数说明：
- market: 不区分沪股和深股，传入沪股或深股都会返回沪深市场的股票
- filter_list: 元素类型为 SimpleFilter / AccumulateFilter / FinancialFilter / CustomIndicatorFilter / PatternFilter
- filter_min/filter_max: 闭区间，不传默认 -∞ / +∞
- is_no_filter: True 不筛选，False 筛选，不传默认不筛选
- sort: 不传默认不排序

返回字段说明：
- turnover_rate/change_rate/amplitude: 百分比字段，20 实际对应 20%
- total_share/float_share: 单位：股
- float_market_val: 单位：元
"""
import argparse
import json
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    create_quote_context,
    check_ret,
    safe_close,
    is_empty,
    safe_get,
    safe_float,
    safe_int,
    df_to_records,
    Market,
    SimpleFilter,
    AccumulateFilter,
    FinancialFilter,
    FinancialQuarter,
    StockField,
    SortDir,
)

MARKET_MAP = {
    "HK": Market.HK,
    "US": Market.US,
    "SH": Market.SH,
    "SZ": Market.SZ,
}

SORT_MAP = {
    "market_val": StockField.MARKET_VAL,
    "price": StockField.CUR_PRICE,
    "volume": StockField.VOLUME,
    "turnover": StockField.TURNOVER,
    "turnover_rate": StockField.TURNOVER_RATE,
    "change_rate": StockField.CHANGE_RATE,
    "pe": StockField.PE_TTM,
    "pb": StockField.PB_RATE,
}

QUARTER_MAP = {
    "ANNUAL": FinancialQuarter.ANNUAL,
    "FIRST_QUARTER": FinancialQuarter.FIRST_QUARTER,
    "INTERIM": FinancialQuarter.INTERIM,
    "THIRD_QUARTER": FinancialQuarter.THIRD_QUARTER,
}


def get_stock_filter(market="HK", limit=20, sort=None, asc=False, output_json=False, **kwargs):
    market_enum = MARKET_MAP.get(market.upper(), Market.HK)
    filter_list = []

    # SimpleFilter: 价格、市值、PE、PB
    simple = SimpleFilter()
    has_simple = False
    if kwargs.get("min_price") is not None:
        simple.filter_min = kwargs["min_price"]
        simple.stock_field = StockField.CUR_PRICE
        has_simple = True
    if kwargs.get("max_price") is not None:
        simple.filter_max = kwargs["max_price"]
        simple.stock_field = StockField.CUR_PRICE
        has_simple = True
    if has_simple:
        filter_list.append(simple)

    if kwargs.get("min_market_cap") is not None or kwargs.get("max_market_cap") is not None:
        sf = SimpleFilter()
        sf.stock_field = StockField.MARKET_VAL
        if kwargs.get("min_market_cap") is not None:
            sf.filter_min = kwargs["min_market_cap"] * 1e8
        if kwargs.get("max_market_cap") is not None:
            sf.filter_max = kwargs["max_market_cap"] * 1e8
        filter_list.append(sf)

    if kwargs.get("min_pe") is not None or kwargs.get("max_pe") is not None:
        sf = SimpleFilter()
        sf.stock_field = StockField.PE_TTM
        if kwargs.get("min_pe") is not None:
            sf.filter_min = kwargs["min_pe"]
        if kwargs.get("max_pe") is not None:
            sf.filter_max = kwargs["max_pe"]
        filter_list.append(sf)

    if kwargs.get("min_pb") is not None or kwargs.get("max_pb") is not None:
        sf = SimpleFilter()
        sf.stock_field = StockField.PB_RATE
        if kwargs.get("min_pb") is not None:
            sf.filter_min = kwargs["min_pb"]
        if kwargs.get("max_pb") is not None:
            sf.filter_max = kwargs["max_pb"]
        filter_list.append(sf)

    # AccumulateFilter: 涨跌幅、成交量、换手率
    if kwargs.get("min_change_rate") is not None or kwargs.get("max_change_rate") is not None:
        af = AccumulateFilter()
        af.stock_field = StockField.CHANGE_RATE
        if kwargs.get("min_change_rate") is not None:
            af.filter_min = kwargs["min_change_rate"]
        if kwargs.get("max_change_rate") is not None:
            af.filter_max = kwargs["max_change_rate"]
        filter_list.append(af)

    if kwargs.get("min_volume") is not None:
        af = AccumulateFilter()
        af.stock_field = StockField.VOLUME
        af.filter_min = kwargs["min_volume"]
        filter_list.append(af)

    if kwargs.get("min_turnover_rate") is not None or kwargs.get("max_turnover_rate") is not None:
        af = AccumulateFilter()
        af.stock_field = StockField.TURNOVER_RATE
        if kwargs.get("min_turnover_rate") is not None:
            af.filter_min = kwargs["min_turnover_rate"]
        if kwargs.get("max_turnover_rate") is not None:
            af.filter_max = kwargs["max_turnover_rate"]
        filter_list.append(af)

    # 排序
    accumulate_fields = {"volume", "turnover", "turnover_rate", "change_rate"}
    if sort and sort in SORT_MAP:
        if sort in accumulate_fields:
            sf_sort = AccumulateFilter()
        else:
            sf_sort = SimpleFilter()
        sf_sort.stock_field = SORT_MAP[sort]
        sf_sort.is_no_filter = True
        sf_sort.sort = SortDir.ASCEND if asc else SortDir.DESCEND
        filter_list.append(sf_sort)

    if not filter_list:
        sf_default = SimpleFilter()
        sf_default.stock_field = StockField.MARKET_VAL
        sf_default.is_no_filter = True
        sf_default.sort = SortDir.DESCEND
        filter_list.append(sf_default)

    ctx = None
    try:
        ctx = create_quote_context()
        ret, data = ctx.get_stock_filter(market_enum, filter_list, begin=0, num=limit)
        check_ret(ret, data, ctx, "条件选股")

        last_page, all_count, stock_list = data

        if not stock_list:
            if output_json:
                print(json.dumps({"data": []}))
            else:
                print("无数据")
            return

        records = []
        for item in stock_list:
            records.append({
                "code": getattr(item, "stock_code", ""),
                "name": getattr(item, "stock_name", ""),
                "price": safe_float(getattr(item, "cur_price", 0)),
                "change_rate": safe_float(getattr(item, "change_rate", 0)),
                "market_val": safe_float(getattr(item, "market_val", 0)),
                "volume": safe_int(getattr(item, "volume", 0)),
                "pe": safe_float(getattr(item, "pe_ttm", 0)),
                "pb": safe_float(getattr(item, "pb_rate", 0)),
                "turnover_rate": safe_float(getattr(item, "turnover_rate", 0)),
            })

        if output_json:
            print(json.dumps({"market": market, "count": len(records), "data": records}, ensure_ascii=False))
        else:
            print("=" * 100)
            print(f"条件选股结果: {market} (共 {len(records)} 只)")
            print("=" * 100)
            print(f"  {'代码':<15} {'名称':<12} {'价格':>8} {'涨跌%':>8} {'市值(亿)':>10} {'PE':>8} {'换手%':>8}")
            print("  " + "-" * 96)
            for r in records:
                mv = r['market_val'] / 1e8 if r['market_val'] > 0 else 0
                print(f"  {r['code']:<15} {r['name']:<12} {r['price']:>8.2f} {r['change_rate']:>8.2f} {mv:>10.2f} {r['pe']:>8.2f} {r['turnover_rate']:>8.2f}")
            print("=" * 100)

    except Exception as e:
        if output_json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"错误: {e}")
        sys.exit(1)
    finally:
        safe_close(ctx)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="条件选股")
    parser.add_argument("--market", choices=["HK", "US", "SH", "SZ"], default="HK", help="市场")
    parser.add_argument("--min-price", type=float, default=None)
    parser.add_argument("--max-price", type=float, default=None)
    parser.add_argument("--min-market-cap", type=float, default=None, help="最小市值（亿）")
    parser.add_argument("--max-market-cap", type=float, default=None, help="最大市值（亿）")
    parser.add_argument("--min-pe", type=float, default=None)
    parser.add_argument("--max-pe", type=float, default=None)
    parser.add_argument("--min-pb", type=float, default=None)
    parser.add_argument("--max-pb", type=float, default=None)
    parser.add_argument("--min-change-rate", type=float, default=None, help="最小涨跌幅(%%)")
    parser.add_argument("--max-change-rate", type=float, default=None, help="最大涨跌幅(%%)")
    parser.add_argument("--min-volume", type=int, default=None)
    parser.add_argument("--min-turnover-rate", type=float, default=None, help="最小换手率(%%)")
    parser.add_argument("--max-turnover-rate", type=float, default=None, help="最大换手率(%%)")
    parser.add_argument("--sort", choices=["market_val", "price", "volume", "turnover", "turnover_rate", "change_rate", "pe", "pb"],
                        default=None, help="排序字段")
    parser.add_argument("--asc", action="store_true", help="升序排序（默认降序）")
    parser.add_argument("--limit", type=int, default=20, help="返回数量（默认: 20）")
    parser.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = parser.parse_args()

    get_stock_filter(
        market=args.market, limit=args.limit, sort=args.sort, asc=args.asc,
        output_json=args.output_json,
        min_price=args.min_price, max_price=args.max_price,
        min_market_cap=args.min_market_cap, max_market_cap=args.max_market_cap,
        min_pe=args.min_pe, max_pe=args.max_pe,
        min_pb=args.min_pb, max_pb=args.max_pb,
        min_change_rate=args.min_change_rate, max_change_rate=args.max_change_rate,
        min_volume=args.min_volume,
        min_turnover_rate=args.min_turnover_rate, max_turnover_rate=args.max_turnover_rate,
    )
