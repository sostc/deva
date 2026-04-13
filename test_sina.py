import urllib.request
import socket

try:
    # Test 1: DNS resolution
    print('Test 1: DNS resolution')
    ip = socket.gethostbyname('hq.sinajs.cn')
    print(f'DNS resolution successful: {ip}')
    
    # Test 2: HTTP request
    print('\nTest 2: HTTP request')
    url = 'https://hq.sinajs.cn/list=sh600000'
    response = urllib.request.urlopen(url, timeout=10)
    print(f'HTTP Status: {response.getcode()}')
    content = response.read()
    print(f'Response Length: {len(content)}')
    print(f'First 200 chars: {content[:200]}')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
