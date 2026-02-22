import datetime

import pandas as pd

from .tradetime import is_tradetime, is_tradedate


def gen_quant():
    import easyquotation

    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.market_snapshot(prefix=False)
    df = pd.DataFrame(q1).T
    df = df[(True ^ df["close"].isin([0]))]
    df = df[(True ^ df["now"].isin([0]))]
    df["p_change"] = (df.now - df.close) / df.close
    df["p_change"] = df.p_change.map(float)
    df["code"] = df.index
    return df


def get_realtime_quant():
    """获取实盘实时行情,非盘中时间不获取数据"""
    if is_tradedate(datetime.datetime.today()) and is_tradetime(datetime.datetime.now()):
        return gen_quant()
