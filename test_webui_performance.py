#!/usr/bin/env python3
"""
测试 Deva web UI 的并发性能

此脚本用于模拟多个浏览器窗口同时与 web UI 交互的情况，
以测试系统在高并发下的性能表现，特别是响应时间和稳定性。
"""

import asyncio
import aiohttp
import time
import argparse
import json
import random

async def test_webui_interaction(session, url, client_id):
    """测试单个 WebSocket 连接的交互"""
    try:
        async with session.ws_connect(url) as ws:
            print(f"Client {client_id}: 已连接")
            
            # 发送初始消息 - 连接到默认流
            await ws.send_json({"stream_ids": ["default"]})
            
            # 模拟用户交互 - 发送多个消息
            start_time = time.time()
            message_count = 0
            response_times = []
            
            # 保持连接 20 秒，期间发送一些消息
            while time.time() - start_time < 20:
                try:
                    # 每 2 秒发送一次消息
                    if int(time.time() - start_time) % 2 == 0:
                        message = {
                            "action": "ping",
                            "timestamp": time.time(),
                            "client_id": client_id,
                            "data": f"test message {message_count}"
                        }
                        send_time = time.time()
                        await ws.send_json(message)
                        message_count += 1
                        
                        # 等待响应
                        msg = await ws.receive(timeout=3.0)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            receive_time = time.time()
                            response_times.append(receive_time - send_time)
                            # 解析响应
                            try:
                                data = json.loads(msg.data)
                                if "error" in data:
                                    print(f"Client {client_id}: 收到错误: {data['error']}")
                            except json.JSONDecodeError:
                                pass
                    else:
                        # 非发送时间，仍然监听消息
                        try:
                            msg = await ws.receive(timeout=1.0)
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                # 处理其他消息
                                pass
                        except asyncio.TimeoutError:
                            # 超时是正常的，继续
                            pass
                    
                    if msg.type == aiohttp.WSMsgType.CLOSED:
                        print(f"Client {client_id}: 连接关闭")
                        break
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"Client {client_id}: 连接错误")
                        break
                except asyncio.TimeoutError:
                    # 超时是正常的，继续保持连接
                    pass
            
            end_time = time.time()
            total_time = end_time - start_time
            
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                max_response_time = max(response_times)
                min_response_time = min(response_times)
                print(f"Client {client_id}: 完成 - 发送 {message_count} 条消息，平均响应时间: {avg_response_time:.3f} 秒，最大: {max_response_time:.3f} 秒，最小: {min_response_time:.3f} 秒")
            else:
                print(f"Client {client_id}: 完成 - 发送 {message_count} 条消息，但没有收到响应")
            
            print(f"Client {client_id}: 连接关闭，总耗时: {total_time:.2f} 秒")
            return {
                "success": True,
                "messages_sent": message_count,
                "response_times": response_times,
                "total_time": total_time
            }
    except Exception as e:
        print(f"Client {client_id}: 连接失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def main(num_clients, url):
    """测试多个并发连接"""
    print(f"测试 {num_clients} 个并发 web UI 交互...")
    print(f"连接到: {url}")
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(num_clients):
            task = asyncio.create_task(test_webui_interaction(session, url, i+1))
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    total_duration = end_time - start_time
    
    # 分析结果
    success_count = sum(1 for r in results if r["success"])
    total_messages = sum(r.get("messages_sent", 0) for r in results if r["success"])
    all_response_times = []
    for r in results:
        if r["success"] and "response_times" in r:
            all_response_times.extend(r["response_times"])
    
    print("\n===== 测试结果 =====")
    print(f"总并发客户端: {num_clients}")
    print(f"成功连接: {success_count}/{num_clients}")
    print(f"总消息数: {total_messages}")
    print(f"总耗时: {total_duration:.2f} 秒")
    print(f"平均每个客户端耗时: {total_duration/num_clients:.2f} 秒")
    
    if all_response_times:
        avg_response_time = sum(all_response_times) / len(all_response_times)
        max_response_time = max(all_response_times)
        min_response_time = min(all_response_times)
        print(f"\n响应时间统计:")
        print(f"平均响应时间: {avg_response_time:.3f} 秒")
        print(f"最大响应时间: {max_response_time:.3f} 秒")
        print(f"最小响应时间: {min_response_time:.3f} 秒")
    else:
        print("\n没有收到响应数据")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试 Deva web UI 并发性能")
    parser.add_argument("--clients", type=int, default=10, help="并发客户端数量")
    parser.add_argument("--url", type=str, default="ws://localhost:9999/sockjs/websocket", help="WebSocket 连接 URL")
    
    args = parser.parse_args()
    
    asyncio.run(main(args.clients, args.url))
