import datetime
from functools import lru_cache, wraps
from bisect import bisect_right

import pandas as pd
import requests
from pymaybe import maybe


_holiday_cache = {}


HOLIDAYS_2024 = {
    "20240101", "20240102", "20240103",  # 元旦
    "20240210", "20240211", "20240212", "20240213", "20240214", "20240215", "20240216", "20240217",  # 春节
    "20240404", "20240405", "20240406",  # 清明
    "20240501", "20240502", "20240503",  # 劳动节
    "20240610",  # 端午
    "20240915", "20240916", "20240917",  # 中秋
    "20241001", "20241002", "20241003", "20241004", "20241005", "20241006", "20241007",  # 国庆
}

HOLIDAYS_2025 = {
    "20250101", "20250102",  # 元旦
    "20250128", "20250129", "20250130", "20250131", "20250201", "20250202", "20250203", "20250204",  # 春节
    "20250404", "20250405", "20250406",  # 清明
    "20250501", "20250502", "20250503",  # 劳动节
    "20250531",  # 端午
    "20250915", "20250916", "20250917",  # 中秋 (调整)
    "20251001", "20251002", "20251003", "20251004", "20251005", "20251006", "20251007", "20251008",  # 国庆
}

HOLIDAYS_2026 = {
    "20260101", "20260102", "20260103",  # 元旦
    "20260128", "20260129", "20260130", "20260131", "20260201", "20260202", "20260203", "20260204",  # 春节
    "20260404", "20260405", "20260406",  # 清明
    "20260501", "20260502", "20260503",  # 劳动节
    "20260531",  # 端午
    "20260915", "20260916", "20260917",  # 中秋
    "20261001", "20261002", "20261003", "20261004", "20261005", "20261006", "20261007", "20261008",  # 国庆
}

ALL_HOLIDAYS = HOLIDAYS_2024 | HOLIDAYS_2025 | HOLIDAYS_2026


def is_holiday(now_time):
    today = now_time.strftime("%Y%m%d")
    return _is_holiday(today)


def _is_holiday(day):
    if day in ALL_HOLIDAYS:
        return True

    if day in _holiday_cache:
        return _holiday_cache[day]

    year = day[:4]
    if year in ("2024", "2025", "2026"):
        return False

    api = "http://tool.bitefu.net/jiari/"
    params = {"d": day, "apiserviceid": 1116}
    try:
        rep = requests.get(api, params, timeout=2)
        res = rep.text
        result = res != "0"
        _holiday_cache[day] = result
        return result
    except Exception:
        return False


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

    for days in range(1, 8):
        candidate = now + datetime.timedelta(days=days)
        if is_tradedate(candidate):
            return candidate.date()

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

    for days in range(1, 8):
        candidate = now - datetime.timedelta(days=days)
        if is_tradedate(candidate):
            return candidate.date()

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
