import datetime
from functools import lru_cache, wraps

import pandas as pd
import requests
from pymaybe import maybe


def is_holiday(now_time):
    today = now_time.strftime("%Y%m%d")
    return _is_holiday(today)


@lru_cache()
def _is_holiday(day):
    api = "http://tool.bitefu.net/jiari/"
    params = {"d": day, "apiserviceid": 1116}
    rep = requests.get(api, params)
    res = rep.text
    return res != "0"


def is_holiday_today():
    today = datetime.date.today()
    return is_holiday(today)


def is_weekend(now_time):
    return now_time.weekday() >= 5


def is_tradedate(now_time=None):
    now_time = maybe(now_time).or_else(datetime.datetime.today())
    return not (is_holiday(now_time) or is_weekend(now_time))


def get_next_trade_date(now):
    if isinstance(now, str):
        now = pd.to_datetime(now)
    if isinstance(now, datetime.date):
        now = datetime.datetime.combine(now, datetime.time())

    max_days = 365
    days = 0
    while 1:
        days += 1
        now += datetime.timedelta(days=1)
        if is_tradedate(now):
            return now.date()
        if days > max_days:
            raise ValueError("无法确定 %s 下一个交易日" % now)


def get_last_trade_date(now):
    if isinstance(now, str):
        now = pd.to_datetime(now)
    if isinstance(now, datetime.date):
        now = datetime.datetime.combine(now, datetime.time())

    max_days = 365
    days = 0
    while 1:
        days += 1
        now -= datetime.timedelta(days=1)
        if is_tradedate(now):
            return now.date()
        if days > max_days:
            raise ValueError("无法确定 %s 上一个交易日" % now)


def get_lastest_trade_date(_datetime):
    from pandas.tseries.offsets import BDay

    if is_tradedate(_datetime):
        return _datetime
    return get_last_trade_date(_datetime - BDay(1))


OPEN_TIME = (
    (datetime.time(9, 15, 0), datetime.time(11, 30, 0)),
    (datetime.time(13, 0, 0), datetime.time(15, 0, 0)),
)


def is_tradetime(now_time=None):
    now_time = maybe(now_time).or_else(datetime.datetime.today())
    now = now_time.time()
    for begin, end in OPEN_TIME:
        if begin <= now < end:
            return True
    return False


PAUSE_TIME = (
    (datetime.time(11, 30, 0), datetime.time(12, 59, 30)),
)


def is_pause(now_time):
    now = now_time.time()
    for b, e in PAUSE_TIME:
        if b <= now < e:
            return True
    return False


CONTINUE_TIME = (
    (datetime.time(12, 59, 30), datetime.time(13, 0, 0)),
)


def is_continue(now_time):
    now = now_time.time()
    for b, e in CONTINUE_TIME:
        if b <= now < e:
            return True
    return False


CLOSE_TIME = (datetime.time(15, 0, 0),)


def is_closing(now_time, start=datetime.time(14, 54, 30)):
    now = now_time.time()
    for close in CLOSE_TIME:
        if start <= now < close:
            return True
    return False


def when_tradetime(func):
    @wraps(func)
    def wrapper(*args, **kw):
        if is_tradetime():
            func(*args, **kw)

    return wrapper


def when_tradedate(func):
    @wraps(func)
    def wrapper(*args, **kw):
        if is_tradedate():
            func(*args, **kw)

    return wrapper


def today() -> str:
    return datetime.date.today().strftime("%Y-%m-%d")


def yesterday() -> str:
    return (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
