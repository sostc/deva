import asyncio
import aiohttp

def _parse_sina_response(text: str):
    """解析新浪返回的数据"""
    result = {}
    for line in text.strip().split('\n'):
        if not line or '="' not in line:
            continue
        try:
            prefix, data = line.split('="')
            code = prefix.split("_")[-1]
            data = data.rstrip('"')
            if not data:
                continue
            fields = data.split(",")
            if len(fields) < 33:
                continue
            result[code] = {
                "name": fields[0],
                "open": float(fields[1]),
                "close": float(fields[2]),
                "now": float(fields[3]),
                "high": float(fields[4]),
                "low": float(fields[5]),
                "volume": int(fields[8]),
                "amount": float(fields[9]) if len(fields) > 9 and fields[9] else 0.0,
            }
        except Exception:
            continue
    return result

async def test_sina_api():
    """测试新浪 API 修复"""
    print('Testing Sina API fix...')
    
    codes = ['sh600000']  # 上证指数
    codes_str = ",".join(codes)
    url = f"https://hq.sinajs.cn/list={codes_str}"
    
    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=50, limit_per_host=20),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        try:
            print(f"Requesting: {url}")
            async with session.get(url, headers=headers) as resp:
                print(f"Status: {resp.status}")
                if resp.status != 200:
                    print(f"Failed with status: {resp.status}")
                    return
                
                text = await resp.text()
                print(f"Response length: {len(text)}")
                print(f"Response: {text[:200]}...")
                
                # 解析响应
                result = _parse_sina_response(text)
                print(f"Parsed result: {result}")
                
                if result:
                    print('✅ Success! Sina API is working now.')
                else:
                    print('❌ Failed! No data returned.')
                    
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_sina_api())
