#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Naja 看到的新闻推给大有（2026-11-01）。

为什么是"推"不是"拉"
-------------------
大有的线上服务器（ssl.secsay.com）上没有 Naja：8080 只在这台 Mac 上跑。
所以让大有来拉是拉不到的 —— 它连不上家里这台机器。方向只能是这一个：

    Naja 本机 8080 /api/market/timeline（Naja 自己抓的，抓取逻辑只此一份）
        │  有新条目
        ▼
    POST https://ssl.secsay.com/marketpush   {key, items:[...]}
        │
        ▼
    大有 data/market_news.db → H5 抽屉 GET /marketnews

这个脚本**不碰 Naja 的内部状态、不 import deva**：它只读一个现成的 HTTP
接口，Naja 怎么改都不影响它（接口没了就只记一条日志，什么都不干）。
反过来说，大有那边也没有第二份抓取实现 —— 金十怎么翻、怎么打分，永远只有
Naja 这一处口径。

用法
----
    python3 scripts/push_market_to_dayou.py --once    # 跑一轮就退（调试/手动补）
    python3 scripts/push_market_to_dayou.py           # 常驻，45 秒一轮

密钥：~/.naja/dayou_push.key（一行），或环境变量 MARKET_PUSH_KEY。
     服务器那边是 data/market_push.key，两边必须一模一样。
     搞不到密钥就**什么都不推**（只记日志），不会静默成功。

状态：~/.naja/dayou_push_state.json 记已推过的 id —— 只是省流量，
     真去重在大有那一层（它按 flash_id / 标题+时间做 INSERT OR IGNORE），
     所以状态文件丢了最多重推一遍，不会产生重复条目。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

NAJA_API = os.getenv('NAJA_API', 'http://127.0.0.1:8080')
DAYOU_URL = os.getenv('DAYOU_PUSH_URL', 'https://ssl.secsay.com/marketpush')
HOME = os.path.expanduser('~')
STATE_FILE = os.path.join(HOME, '.naja', 'dayou_push_state.json')
KEY_FILE = os.path.join(HOME, '.naja', 'dayou_push.key')

INTERVAL = int(os.getenv('PUSH_INTERVAL', '45'))     # 秒
KEEP_IDS = 1200                                       # 本地记住多少条已推
KINDS = ('jin10_news', 'high_score_news')             # 新闻 tab 里那两类
TIMEOUT = 12


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

def fetch_timeline():
    url = NAJA_API + '/api/market/timeline'
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    if not isinstance(data, dict):
        return []
    return [x for x in (data.get('list') or [])
            if isinstance(x, dict) and x.get('type') in KINDS]


def norm(it):
    """只留大有要的字段 —— 多余的（block_name / stock_codes…）不往线上送。"""
    out = {
        'type': it.get('type') or '',
        'title': (it.get('title') or it.get('summary') or '').strip()[:300],
        'text': (it.get('text') or '').strip()[:2000],
        'source': it.get('source') or '',
        'url': it.get('url') or '',
        'timestamp': it.get('timestamp') or 0,
    }
    if it.get('flash_id'):
        out['flash_id'] = str(it['flash_id'])
    if it.get('importance_score') is not None:
        out['importance_score'] = it.get('importance_score')
    elif it.get('score') is not None:
        out['score'] = it.get('score')
    if isinstance(it.get('topics'), list):
        out['topics'] = it['topics'][:6]
    if it.get('sentiment') is not None:
        out['sentiment'] = it.get('sentiment')
    return out


def ident(it):
    if it.get('flash_id'):
        return 'f:' + str(it['flash_id'])
    return 't:%s|%s' % (it.get('title', '')[:120], it.get('timestamp') or 0)


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
        items = fetch_timeline()
    except urllib.error.URLError as e:
        log('Naja 8080 连不上（那边没在跑？）: %s' % getattr(e, 'reason', e))
        return 0
    except Exception as e:
        log('取时间线失败: %s: %s' % (type(e).__name__, e))
        return 0

    if not items:
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
    log('推了 %d 条（新增 %s / 重复 %s）'
        % (len(fresh), res.get('added'), res.get('skipped')))
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
