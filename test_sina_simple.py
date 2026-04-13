import urllib.request
import socket

try:
    # Test 1: DNS resolution
    print('Test 1: DNS resolution')
    ip = socket.gethostbyname('hq.sinajs.cn')
    print(f'DNS resolution successful: {ip}')
    
    # Test 2: HTTP request with proper headers
    print('\nTest 2: HTTP request with proper headers')
    url = 'https://hq.sinajs.cn/list=sh600000'
    
    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    req = urllib.request.Request(url, headers=headers)
    response = urllib.request.urlopen(req, timeout=10)
    print(f'HTTP Status: {response.getcode()}')
    content = response.read()
    print(f'Response Length: {len(content)}')
    print(f'Response: {content}')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
