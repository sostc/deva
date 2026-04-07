import urllib.request

url = "https://hq.sinajs.cn/list=sh000001,s_sh000300,sz399006,hf_NQ,hf_ES,hf_YM"
headers = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0"
}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    data = resp.read().decode('gbk')

cn_shanghai_pct = None
cn_hs300_pct = None
cn_chinext_pct = None
us_nasdaq_pct = None
us_sp500_pct = None
us_dow_pct = None

for line in data.split('\n'):
    if 'hq_str_sh000001' in line:
        parts = line.split('"')
        if len(parts) < 2:
            continue
        fields = parts[1].split(',')
        if len(fields) > 2:
            cur = float(fields[1]) if fields[1] else 0
            prev = float(fields[2]) if fields[2] else 0
            if prev:
                cn_shanghai_pct = round((cur - prev) / prev * 100, 2)
            print(f"上证: cur={cur}, prev={prev}, pct={cn_shanghai_pct}")
    elif 'hq_str_s_sh000300' in line:
        parts = line.split('"')
        if len(parts) < 2:
            continue
        fields = parts[1].split(',')
        print(f"沪深300 fields: {fields[:5]}")
        if len(fields) > 3:
            pct_str = fields[3] if len(fields) > 3 else fields[2]
            try:
                cn_hs300_pct = float(pct_str)
                print(f"沪深300: pct={cn_hs300_pct}")
            except (ValueError, TypeError):
                print(f"沪深300: 解析失败 pct_str={pct_str}")
    elif 'hq_str_sz399006' in line:
        parts = line.split('"')
        if len(parts) < 2:
            continue
        fields = parts[1].split(',')
        if len(fields) > 2:
            cur = float(fields[1]) if fields[1] else 0
            prev = float(fields[2]) if fields[2] else 0
            if prev:
                cn_chinext_pct = round((cur - prev) / prev * 100, 2)
            print(f"创业板: cur={cur}, prev={prev}, pct={cn_chinext_pct}")

for line in data.split('\n'):
    if 'hq_str_hf_NQ' in line:
        parts = line.split('"')
        if len(parts) < 2:
            continue
        fields = parts[1].split(',')
        print(f"\n纳指期货 fields: {fields[:10]}")
        if len(fields) > 9:
            cur = float(fields[0]) if fields[0] else 0
            prev = float(fields[8]) if fields[8] else 0
            if prev:
                us_nasdaq_pct = round((cur - prev) / prev * 100, 2)
            print(f"纳指: cur={cur}, prev={prev}, pct={us_nasdaq_pct}")
    elif 'hq_str_hf_ES' in line:
        parts = line.split('"')
        if len(parts) < 2:
            continue
        fields = parts[1].split(',')
        if len(fields) > 9:
            cur = float(fields[0]) if fields[0] else 0
            prev = float(fields[8]) if fields[8] else 0
            if prev:
                us_sp500_pct = round((cur - prev) / prev * 100, 2)
            print(f"标普: cur={cur}, prev={prev}, pct={us_sp500_pct}")
    elif 'hq_str_hf_YM' in line:
        parts = line.split('"')
        if len(parts) < 2:
            continue
        fields = parts[1].split(',')
        if len(fields) > 9:
            cur = float(fields[0]) if fields[0] else 0
            prev = float(fields[8]) if fields[8] else 0
            if prev:
                us_dow_pct = round((cur - prev) / prev * 100, 2)
            print(f"道指: cur={cur}, prev={prev}, pct={us_dow_pct}")

print("\n=== 结果汇总 ===")
print(f"上证: {cn_shanghai_pct}")
print(f"沪深300: {cn_hs300_pct}")
print(f"创业板: {cn_chinext_pct}")
print(f"纳指: {us_nasdaq_pct}")
print(f"标普: {us_sp500_pct}")
print(f"道指: {us_dow_pct}")