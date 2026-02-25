#!/usr/bin/env python3
"""
测试 Deva admin 的并发性能

此脚本用于模拟多个浏览器窗口同时访问 admin 界面的情况，
以测试系统在高并发下的性能表现。
"""

import asyncio
import aiohttp
import time
import argparse

async def test_connection(session, url, client_id):
    """测试单个 WebSocket 连接"""
    try:
        async with session.ws_connect(url) as ws:
            print(f"Client {client_id}: 已连接")
            
            # 发送初始消息
            await ws.send_json({"stream_ids": []})
            
            # 保持连接 10 秒
            start_time = time.time()
            while time.time() - start_time < 10:
                try:
                    msg = await ws.receive(timeout=1.0)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        # 接收消息但不处理，模拟浏览器行为
                        pass
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        break
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        break
                except asyncio.TimeoutError:
                    # 超时是正常的，继续保持连接
                    pass
            
            print(f"Client {client_id}: 连接关闭")
            return True
    except Exception as e:
        print(f"Client {client_id}: 连接失败: {e}")
        return False

async def main(num_clients, url):
    """测试多个并发连接"""
    print(f"测试 {num_clients} 个并发连接...")
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(num_clients):
            task = asyncio.create_task(test_connection(session, url, i+1))
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    success_count = sum(results)
    
    print(f"测试完成: {success_count}/{num_clients} 个连接成功")
    print(f"总耗时: {end_time - start_time:.2f} 秒")
    print(f"平均每个连接耗时: {(end_time - start_time)/num_clients:.2f} 秒")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试 Deva admin 并发性能")
    parser.add_argument("--clients", type=int, default=10, help="并发客户端数量")
    parser.add_argument("--url", type=str, default="ws://localhost:9999/sockjs/websocket", help="WebSocket 连接 URL")
    
    args = parser.parse_args()
    
    asyncio.run(main(args.clients, args.url))
