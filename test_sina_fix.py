import asyncio
from deva.naja.market_hotspot.data.sina_parser import _fetch_sina_batch_async

async def test_sina_fix():
    print('Testing Sina API fix...')
    codes = ['sh600000']  # 上证指数
    result = await _fetch_sina_batch_async(codes)
    print(f'Result: {result}')
    if result:
        print('✅ Success! Sina API is working now.')
    else:
        print('❌ Failed! No data returned.')

if __name__ == '__main__':
    asyncio.run(test_sina_fix())
