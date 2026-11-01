#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Naja 看到的新闻推给大有（2026-11-01）。

为什么是"推"不是"拉"
-------------------
大有的线上服务器（ssl.secsay.com）上没有 Naja：8080 只在这台 Mac 上跑。
所以让大有来拉是拉不到的 —— 它连不上家里这台机器。方向只能是这一个：

    Naja 本机 8080 /api/news/digest（= /news 新闻 tab 的同一份数据）
        │  有新条目
        ▼
    POST https://ssl.secsay.com/marketpush   {key, items:[...]}
        │
        ▼
    大有 data/market_news.db → H5 抽屉 GET /marketnews

推什么：**新闻 tab 里那三组** —— 持仓相关 / 关注叙事 / 外部要闻。
2026-11-01 用户改的口径：一开始推的是 `/api/market/timeline`（原始全量时间线），
现在线上看到一大堆伊朗、俄乌、中东的消息，跟"股市"两回事。用户要的是
「和 Naja 新闻 tab 里一致，就是和持仓、关注主题等相关的新闻，不是全部」。

为什么不自己筛
-------------
「该看什么」的口径在 `deva/naja/news/triage.py`：持仓命中、叙事命中、档位、
同事件折叠。在这里再写一遍 = 两份口径，早晚不一样。所以脚本只做搬运：
从 `/api/news/digest` 拿已分好组的条目，摊平后原样推走。

❗为什么走 HTTP 而不是 import deva
----
持仓与叙事是**活的状态**（app container + manas 引擎）。独立进程 import
自己算会降级（实测：「账户初始化失败（虚拟测试）→ 持仓读作空」、
「manas 不可用 → 主题退化为 keyword_registry 预设」），算出来跟页面上看到的
不是一回事。所以宁可要 Naja 开那个只读接口（`/api/news/digest`），
也不在这边拼一份"看起来差不多"的。

用法
----
    python3 scripts/push_market_to_dayou.py --once    # 跑一轮就退（调试/手动补）
    python3 scripts/push_market_to_dayou.py           # 常驻，45 秒一轮

密钥：~/.naja/dayou_push.key（一行），或环境变量 MARKET_PUSH_KEY。
     服务器那边是 data/market_push.key，两边必须一模一样。
     搞不到密钥就**什么都不推**（只记日志），不会静默成功。

状态：~/.naja/doyou_push_state.json 记已推过的 id —— 只是省流量，
     真去重在大有那一层（它按标题+时间做 INSERT OR IGNORE），
     所以状态文件丢了最多重推一遍，不会产生重复条目。
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NAJA_API = os.getenv('NAJA_API', 'http://127.0.0.1:8080')
DAYOU_URL = os.getenv('DAYOU_PUSH_URL', 'https://ssl.secsay.com/marketpush')
HOME = os.path.expanduser('~')
STATE_FILE = os.path.join(HOME, '.naja', 'dayou_push_state.json')
KEY_FILE = os.path.join(HOME, '.naja', 'dayou_push.key')

INTERVAL = int(os.getenv('PUSH_INTERVAL', '45'))     # 秒
KEEP_IDS = 1200                                       # 本地记住多少条已推
TIMEOUT = 20                                          # digest 要现算，给宽一点
# 和 /news 页面一致：24 小时窗、每组 8 条。三组一共最多 24 条 —— 这是"新闻 tab
# 一屏"的量，不是"今天全部新闻"。
WINDOW_HOURS = int(os.getenv('NEWS_WINDOW_HOURS', '24'))
PER_GROUP = int(os.getenv('NEWS_PER_GROUP', '8'))
GROUP_ORDER = ('holding', 'theme', 'macro')

# 分组名由 Naja 给（group_labels），这里只做兜底 —— 两边名字必须一个说法，
# 但**以 Naja 为准**（它才是口径的所有者），兜底只防接口临时缺字段。
GROUP_FALLBACK = {'holding': '持仓相关', 'theme': '关注叙事',
                  'macro': '外部要闻'}



def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


# ------------------------------------------------------------------ 密钥 / 状态

def read_key():
    k = (os.getenv('MARKET_PUSH_KEY') or '').strip()
    if k:
        return k
    try:
        with open(KEY_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return ''


def load_state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            s = json.load(f)
            if isinstance(s, dict) and isinstance(s.get('sent'), list):
                return s
    except Exception:
        pass
    return {'sent': []}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        sent = state.get('sent') or []
        if len(sent) > KEEP_IDS:
            sent = sent[-KEEP_IDS:]
        tmp = STATE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'sent': sent, 'at': time.time()}, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log('状态写不进去（不影响推送）: %s' % e)


# ------------------------------------------------------------------ 取 / 推

def fetch_digest():
    """取「新闻 tab」那三组。返回 (items, labels, meta)。

    条目已经分好组、组内按相关度排、同事件折叠过 —— 这里**不再筛**，
    只把三组摊平成一个列表（holding → theme → macro）。
    """
    q = urllib.parse.urlencode({'hours': WINDOW_HOURS,
                                'per_group_limit': PER_GROUP})
    url = NAJA_API + '/api/news/digest?' + q
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    if not isinstance(data, dict) or not data.get('success'):
        # 接口自己失败时带 error —— 原样报出来，别让它看起来像"今天没新闻"
        raise RuntimeError((data or {}).get('error') or 'digest 接口返回失败')
    dg = data.get('digest') or {}
    if not dg.get('available'):
        return [], {}, {'reason': dg.get('reason') or '最近窗口内没有已评分的新闻',
                        'stats': dg.get('stats') or {}}
    labels = dg.get('group_labels') or {}
    out = []
    for g in GROUP_ORDER:
        for it in (dg.get('groups') or {}).get(g) or []:
            if isinstance(it, dict) and (it.get('title') or '').strip():
                the = dict(it)
                the['_group'] = g
                out.append(the)
    return out, labels, {'stats': dg.get('stats') or {},
                         'focus': dg.get('focus') or {},
                         'hours': dg.get('window_hours') or WINDOW_HOURS}


def norm(it):
    """只留大有要的字段 —— 多余的（reasons / tier_band…）不往线上送。"""
    ts = it.get('timestamp') or 0
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        ts = 0.0
    if ts > 1e11:                                   # 毫秒 → 秒
        ts = ts / 1000.0
    title = (it.get('title') or '').strip()[:300]
    text = (it.get('summary') or '').strip()
    if text and text == title:
        text = ''
    # 「为什么给你看」：持仓/自选命中最重要，其次是叙事命中；股票代码也是命中。
    hits = []
    for name in (it.get('holding_hits') or []):
        hits.append('持仓·%s' % str(name)[:14])
    for name in (it.get('watchlist_hits') or []):
        hits.append('自选·%s' % str(name)[:14])
    for name in (it.get('narrative_hits') or []):
        hits.append('主题·%s' % str(name)[:14])
    if not hits:
        for code in (it.get('stock_codes') or [])[:2]:
            hits.append('相关·%s' % str(code)[:14])
    out = {
        'group': it.get('_group') or it.get('group') or '',
        'title': title,
        'text': text[:2000],
        'source': it.get('source') or '',
        'url': it.get('url') or '',
        'timestamp': ts,
        'relevance': it.get('relevance') or 0,
        'hits': hits[:4],
    }
    if isinstance(it.get('topics'), list):
        out['topics'] = [str(x)[:12] for x in it['topics'][:4]]
    if it.get('sentiment') is not None:
        out['sentiment'] = it.get('sentiment')
    if it.get('dup_count') and int(it['dup_count']) > 1:
        out['dup_count'] = int(it['dup_count'])
    return out


def ident(it):
    """稳定的去重键：**只认标题**（+ 日期）。

    digest 里没有 flash_id；timestamp 偶尔为 0（重要事件那种聚合条），拿它当
    键的一部分会让同一条每轮算出不同的键、被反复推。标题 + 日期既能挡住重复，
    也不会把隔天同名的一条当成旧的吞掉。
    """
    title = (it.get('title') or '').strip()
    ts = it.get('timestamp') or 0
    try:
        day = time.strftime('%Y-%m-%d', time.localtime(float(ts) or time.time()))
    except (TypeError, ValueError, OSError):
        day = time.strftime('%Y-%m-%d')
    h = hashlib.md5(('%s|%s' % (title, day)).encode('utf-8')).hexdigest()[:16]
    return 'd:' + h


def post(items, key):
    body = json.dumps({'key': key, 'items': items}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        DAYOU_URL, data=body, method='POST',
        headers={'Content-Type': 'application/json; charset=UTF-8'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except Exception:
        return {'ok': False, 'raw': raw[:120]}


def beat(key, state):
    try:
        items, labels, meta = fetch_digest()
    except urllib.error.URLError as e:
        log('Naja 8080 连不上（那边没在跑？）: %s' % getattr(e, 'reason', e))
        return 0
    except Exception as e:
        log('取新闻 tab 失败: %s: %s' % (type(e).__name__, e))
        return 0

    if not items:
        # 「没新闻」和「取不到」要分开说：前者是市场安静，后者是管线断了。
        log('这一轮没有可推的：%s' % (meta.get('reason') or '三组都是空的'))
        return 0

    sent = set(state.get('sent') or [])
    fresh = []
    for it in items:
        n = norm(it)
        if not n['title']:
            continue
        k = ident(it)
        if k in sent:
            continue
        fresh.append((k, n))

    if not fresh:
        return 0

    # 时间正序推：大有那边按 ts 倒序排，先到先落，读者看到的是"从上往下变新"。
    fresh.sort(key=lambda x: x[1].get('timestamp') or 0)
    try:
        res = post([n for _, n in fresh], key)
    except urllib.error.HTTPError as e:
        log('推送被拒 HTTP %s（密钥对不上？看服务器 data/market_push.key）' % e.code)
        return 0
    except Exception as e:
        log('推送失败: %s: %s' % (type(e).__name__, e))
        return 0

    if not (res or {}).get('ok'):
        log('推送没成: %s' % json.dumps(res, ensure_ascii=False)[:160])
        return 0

    state['sent'] = (state.get('sent') or []) + [k for k, _ in fresh]
    save_state(state)
    cnt = {}
    for _, n in fresh:
        lbl = (labels or {}).get(n.get('group')) or GROUP_FALLBACK.get(
            n.get('group')) or n.get('group') or '未分组'
        cnt[lbl] = cnt.get(lbl, 0) + 1
    log('推了 %d 条（新增 %s / 重复 %s）%s'
        % (len(fresh), res.get('added'), res.get('skipped'),
           '｜' + ' · '.join('%s %d' % (k, v) for k, v in cnt.items())))
    return len(fresh)


def main():
    ap = argparse.ArgumentParser(description='把 Naja 的新闻推给大有')
    ap.add_argument('--once', action='store_true', help='跑一轮就退出')
    ap.add_argument('--interval', type=int, default=INTERVAL, help='常驻轮询秒数')
    args = ap.parse_args()

    key = read_key()
    if not key:
        log('没有推送密钥，什么都不推。放一份到 %s（内容与服务器 '
            'data/market_push.key 相同），或设 MARKET_PUSH_KEY。' % KEY_FILE)
        return 2

    state = load_state()
    if args.once:
        n = beat(key, state)
        log('这一轮结束，推了 %d 条' % n)
        return 0

    log('常驻推送：每 %d 秒一轮 → %s' % (args.interval, DAYOU_URL))
    while True:
        try:
            beat(key, state)
        except KeyboardInterrupt:
            log('手动停')
            return 0
        except Exception as e:                       # 任何意外都不许把守护弄死
            log('这一轮出错（继续）: %s: %s' % (type(e).__name__, e))
        time.sleep(max(10, args.interval))


if __name__ == '__main__':
    sys.exit(main())
