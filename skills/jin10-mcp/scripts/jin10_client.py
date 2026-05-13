#!/usr/bin/env python3
"""
金十数据 MCP 客户端 - Python 封装

Usage:
    python jin10_client.py <command> [options]

Commands:
    quote <code>              获取指定品种实时行情
    kline <code> [time] [count]  获取 K 线数据
    flash [cursor]            获取快讯列表
    search_flash <keyword>    搜索快讯
    news [cursor]             获取新闻列表
    search_news <keyword> [cursor]  搜索新闻
    get_news <id>             获取新闻详情
    calendar                  获取财经日历
    list                      列出所有可用工具
    help                      显示帮助

Examples:
    python jin10_client.py quote XAUUSD
    python jin10_client.py kline XAUUSD
    python jin10_client.py flash
    python jin10_client.py search_flash 黄金
    python jin10_client.py calendar
"""

import argparse
import json
import subprocess
import sys


def call_mcporter(tool_name, **kwargs):
    """调用 mcporter 工具"""
    args = []
    for key, value in kwargs.items():
        if value is not None:
            args.append(f"{key}:{value}")
    
    cmd = ["mcporter", "call", f"jin10.{tool_name}"] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                # 有时候 mcporter 输出可能不是纯 JSON，尝试清理
                stdout = result.stdout.strip()
                # 尝试找到第一个 { 和最后一个 } 之间的内容
                if '{' in stdout and '}' in stdout:
                    start = stdout.find('{')
                    end = stdout.rfind('}') + 1
                    return json.loads(stdout[start:end])
                return None
        else:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Exception: {e}", file=sys.stderr)
        return None


def format_quote(data):
    """格式化行情数据"""
    if not data:
        return
    
    print(f"\n{'='*60}")
    print(f"{data.get('name', 'N/A')} ({data.get('code', 'N/A')})")
    print(f"{'='*60}")
    print(f"时间: {data.get('time', 'N/A')}")
    print(f"开盘: {data.get('open', 'N/A')}")
    print(f"收盘: {data.get('close', 'N/A')}")
    print(f"最高: {data.get('high', 'N/A')}")
    print(f"最低: {data.get('low', 'N/A')}")
    print(f"成交量: {data.get('volume', 'N/A')}")
    
    ups_price = data.get('ups_price', 'N/A')
    ups_percent = data.get('ups_percent', 'N/A')
    print(f"涨跌: {ups_price} ({ups_percent}%)")
    print(f"{'='*60}\n")


def format_kline(data):
    """格式化 K 线数据"""
    if not data:
        return
    
    print(f"\n{'='*60}")
    print(f"{data.get('name', 'N/A')} ({data.get('code', 'N/A')}) K线")
    print(f"{'='*60}")
    
    klines = data.get('klines', [])
    if klines:
        print(f"{'时间':<20} {'开盘':<10} {'收盘':<10} {'最高':<10} {'最低':<10} {'成交量':<10}")
        print("-"*70)
        for k in klines[:10]:  # 只显示前10条
            time_val = k.get('time', '')
            time_str = str(time_val)[:19] if time_val is not None else ''
            print(f"{time_str:<20} "
                  f"{k.get('open', ''):<10} "
                  f"{k.get('close', ''):<10} "
                  f"{k.get('high', ''):<10} "
                  f"{k.get('low', ''):<10} "
                  f"{k.get('volume', ''):<10}")
        if len(klines) > 10:
            print(f"... (共 {len(klines)} 条)")
    print(f"{'='*60}\n")


def format_flash(data):
    """格式化快讯数据"""
    if not data:
        return
    
    items = data.get('items', [])
    print(f"\n{'='*60}")
    print(f"最新快讯 ({len(items)} 条)")
    print(f"{'='*60}")
    
    for idx, item in enumerate(items, 1):
        print(f"\n[{idx}] {item.get('title', 'N/A')}")
        print(f"    时间: {item.get('time', 'N/A')}")
        if item.get('content'):
            print(f"    内容: {item.get('content', '')[:100]}...")
    
    next_cursor = data.get('next_cursor')
    has_more = data.get('has_more', False)
    print(f"\n更多数据: {'是' if has_more else '否'}")
    if next_cursor:
        print(f"下一页 cursor: {next_cursor}")
    print(f"{'='*60}\n")


def format_news(data):
    """格式化新闻数据"""
    if not data:
        return
    
    items = data.get('items', [])
    print(f"\n{'='*60}")
    print(f"最新新闻 ({len(items)} 条)")
    print(f"{'='*60}")
    
    for idx, item in enumerate(items, 1):
        print(f"\n[{idx}] {item.get('title', 'N/A')}")
        print(f"    ID: {item.get('id', 'N/A')}")
        print(f"    时间: {item.get('time', 'N/A')}")
        if item.get('introduction'):
            print(f"    简介: {item.get('introduction', '')[:80]}...")
    
    next_cursor = data.get('next_cursor')
    has_more = data.get('has_more', False)
    print(f"\n更多数据: {'是' if has_more else '否'}")
    if next_cursor:
        print(f"下一页 cursor: {next_cursor}")
    print(f"{'='*60}\n")


def format_news_detail(data):
    """格式化新闻详情"""
    if not data:
        return
    
    print(f"\n{'='*60}")
    print(f"{data.get('title', 'N/A')}")
    print(f"{'='*60}")
    print(f"ID: {data.get('id', 'N/A')}")
    print(f"时间: {data.get('time', 'N/A')}")
    print(f"URL: {data.get('url', 'N/A')}")
    print(f"\n简介: {data.get('introduction', 'N/A')}")
    print(f"\n内容:\n{data.get('content', 'N/A')[:500]}...")
    print(f"{'='*60}\n")


def format_calendar(data):
    """格式化财经日历"""
    if not data:
        return
    
    print(f"\n{'='*60}")
    print(f"本周财经日历")
    print(f"{'='*60}")
    
    if isinstance(data, list):
        items = data
    else:
        items = data if isinstance(data, list) else []
    
    for idx, item in enumerate(items[:20], 1):  # 只显示前20条
        print(f"\n[{idx}] {item.get('title', 'N/A')}")
        print(f"    时间: {item.get('pub_time', 'N/A')}")
        print(f"    重要性: {'⭐' * item.get('star', 0)}")
        print(f"    前值: {item.get('previous', 'N/A')}")
        print(f"    预期: {item.get('consensus', 'N/A')}")
        print(f"    实际: {item.get('actual', 'N/A')}")
        if item.get('affect_txt'):
            print(f"    影响: {item.get('affect_txt', 'N/A')}")
    
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="金十数据 MCP 客户端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("command", help="命令")
    parser.add_argument("args", nargs="*", help="参数")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    
    parsed = parser.parse_args()
    cmd = parsed.command
    args = parsed.args
    
    if cmd == "help":
        print(__doc__)
        return
    
    elif cmd == "list":
        subprocess.run(["mcporter", "list", "jin10", "--schema"])
        return
    
    elif cmd == "quote" and len(args) >= 1:
        code = args[0]
        result = call_mcporter("get_quote", code=code)
        if parsed.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            format_quote(result)
    
    elif cmd == "kline" and len(args) >= 1:
        code = args[0]
        kwargs = {"code": code}
        if len(args) >= 2:
            kwargs["time"] = int(args[1])
        if len(args) >= 3:
            kwargs["count"] = int(args[2])
        result = call_mcporter("get_kline", **kwargs)
        if parsed.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            format_kline(result)
    
    elif cmd == "flash":
        cursor = args[0] if args else None
        kwargs = {}
        if cursor:
            kwargs["cursor"] = cursor
        result = call_mcporter("list_flash", **kwargs)
        if parsed.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            format_flash(result)
    
    elif cmd == "search_flash" and len(args) >= 1:
        keyword = args[0]
        result = call_mcporter("search_flash", keyword=keyword)
        if parsed.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            format_flash(result)
    
    elif cmd == "news":
        cursor = args[0] if args else None
        kwargs = {}
        if cursor:
            kwargs["cursor"] = cursor
        result = call_mcporter("list_news", **kwargs)
        if parsed.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            format_news(result)
    
    elif cmd == "search_news" and len(args) >= 1:
        keyword = args[0]
        cursor = args[1] if len(args) >= 2 else None
        kwargs = {"keyword": keyword}
        if cursor:
            kwargs["cursor"] = cursor
        result = call_mcporter("search_news", **kwargs)
        if parsed.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            format_news(result)
    
    elif cmd == "get_news" and len(args) >= 1:
        news_id = args[0]
        result = call_mcporter("get_news", id=news_id)
        if parsed.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            format_news_detail(result)
    
    elif cmd == "calendar":
        result = call_mcporter("list_calendar")
        if parsed.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            format_calendar(result)
    
    else:
        print(f"未知命令: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
