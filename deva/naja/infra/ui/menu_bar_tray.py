"""macOS 菜单栏托盘模块"""

import os
import sys
import json
import logging
import signal
import subprocess
import time as time_module
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NAJA_DIR = Path.home() / ".naja"
PID_FILE = NAJA_DIR / "naja.pid"
PORT_FILE = NAJA_DIR / "naja.port"
DEFAULT_PORT = 8080

STATIC_DIR = Path(__file__).parent.parent.parent / "static"
ICON_PURPLE = str(STATIC_DIR / "naja_tray_purple_22.png")
ICON_GREEN = str(STATIC_DIR / "naja_tray_red_22.png")


def _is_trading_time() -> bool:
    """通过 API 或本地计算判断是否在交易时段"""
    data = _http_get("/api/trading/status")
    if data and data.get("success"):
        return data.get("is_trading", False)
    return _is_trading_time_local()


def _is_trading_time_local() -> bool:
    """本地计算判断是否在交易时段"""
    from datetime import datetime, time
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    
    if weekday >= 5:
        return False
    
    if time(9, 25) <= current_time <= time(11, 35):
        return True
    if time(12, 55) <= current_time <= time(15, 5):
        return True
    
    us_hour, us_min = current_time.hour, current_time.minute
    us_total = us_hour * 60 + us_min
    if time(21, 30) <= current_time <= time(23, 59):
        return True
    if time(0, 0) <= current_time <= time(4, 0):
        return True
    
    return False


def _get_naja_port() -> int:
    """从配置文件读取 Naja 端口，失败时返回默认值"""
    try:
        if PORT_FILE.exists():
            return int(PORT_FILE.read_text().strip())
    except Exception:
        pass
    return DEFAULT_PORT


def _get_tray_icon_path():
    base = Path(__file__).parent.parent.parent / "static"
    possible_paths = [
        base / "naja_22.png",
        base / "naja_32.png",
        base / "naja_16.png",
        base / "naja_icon.png",
        base / "naja_128.png",
        Path.home() / ".naja" / "naja_icon.png",
    ]
    for p in possible_paths:
        if p.exists():
            return str(p)
    return None


def _http_get(path: str, port: int = None, timeout: float = 5.0) -> Optional[dict]:
    """向 Naja Web API 发送 GET 请求"""
    if port is None:
        port = _get_naja_port()
    url = f"http://localhost:{port}{path}"
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "NajaTray/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"HTTP GET {url} 失败: {e}")
        return None


class MenuBarTray:
    _instance: Optional['MenuBarTray'] = None

    @classmethod
    def is_available(cls):
        if sys.platform != "darwin":
            return False
        try:
            import rumps
            return True
        except ImportError:
            return False

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._app = None
        self._timeline_events = []
        self._icon_path = _get_tray_icon_path()

    def _get_timeline_events(self) -> dict:
        """获取 24 小时时间线数据"""
        try:
            from datetime import datetime, timedelta
            from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
                _get_a_block_events,
                _get_us_events,
                _get_high_score_news,
                _get_jin10_important_news,
            )
            
            cn_events = _get_a_block_events()
            us_events = _get_us_events()
            news_events = _get_high_score_news()
            jin10_news = _get_jin10_important_news()
            
            all_events = cn_events + us_events + news_events + jin10_news
            all_events.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            cutoff = (datetime.now() - timedelta(hours=24)).timestamp()
            all_events = [e for e in all_events if e.get('timestamp', 0) >= cutoff]
            
            timeline_items = []
            for event in all_events[:15]:
                ts = event.get('timestamp', 0)
                dt = datetime.fromtimestamp(ts)
                event_type = event.get('type', '')
                block_name = event.get('block_name', '')
                
                item = {
                    'type': event_type,
                    'timestamp': ts,
                    'time': dt.strftime('%H:%M'),
                    'date': dt.strftime('%m-%d'),
                    'title': block_name,
                }
                
                if event_type == 'high_score_news':
                    item['score'] = event.get('score', 0.5)
                elif event_type == 'jin10_news':
                    item['score'] = event.get('score', 0.85)
                    item['flash_id'] = event.get('flash_id', '')
                    item['url'] = event.get('url', '')
                elif event_type in ('cn_event', 'us_event'):
                    change_percent = event.get('change_percent', 0)
                    sign = '+' if change_percent >= 0 else ''
                    item['change'] = f"{sign}{change_percent:.1f}%"
                    item['weight'] = event.get('weight', 0.5)
                
                timeline_items.append(item)
            
            return {
                "success": True,
                "stats": {
                    "cn_events": len(cn_events),
                    "us_events": len(us_events),
                    "high_score_news": len(news_events),
                    "jin10_news": len(jin10_news),
                },
                "list": timeline_items,
            }
        except Exception as e:
            logger.error(f"获取 timeline 事件失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "stats": {},
                "list": [],
            }

    def _get_running_pid(self) -> Optional[int]:
        try:
            if not PID_FILE.exists():
                return None
            pid = int(PID_FILE.read_text().strip())
            if pid <= 0:
                return None
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            PID_FILE.unlink(missing_ok=True)
            return None

    def _get_tray_script_path(self) -> str:
        """获取托盘脚本路径"""
        return os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "naja_tray.py")

    def _restart_tray(self):
        """重启 Naja 服务器和托盘程序"""
        import rumps
        logger.info("正在重启 Naja 服务...")

        env = os.environ.copy()
        env["LSUIElement"] = "1"
        deva_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        python_path = env.get("PYTHONPATH", "")
        if python_path:
            env["PYTHONPATH"] = f"{deva_root}:{python_path}"
        else:
            env["PYTHONPATH"] = deva_root

        # 先停止旧的 Naja 服务器
        pid = self._get_running_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info(f"已停止旧 Naja 服务器 (PID: {pid})")
            except ProcessLookupError:
                pass
            time_module.sleep(1.0)

        # 启动新的 Naja 服务器
        naja_cmd = [sys.executable, "-m", "deva.naja", "-s", "start"]
        naja_log_file = NAJA_DIR / "logs" / "naja_restart.log"
        try:
            with open(naja_log_file, 'a') as f:
                subprocess.Popen(
                    naja_cmd,
                    env=env,
                    cwd=deva_root,
                    start_new_session=True,
                    stdout=f,
                    stderr=subprocess.STDOUT
                )
            logger.info(f"已启动新的 Naja 服务器")
        except Exception as e:
            logger.error(f"启动新的 Naja 服务器失败: {e}")

        # 等待 Naja 服务器启动
        time_module.sleep(1.5)

        # 退出当前托盘（新托盘会由 Naja 服务器自动启动）
        logger.info("正在退出当前托盘...")
        rumps.quit_application()

    def _on_reload(self, sender):
        logger.info("托盘菜单触发 reload")
        self._restart_tray()

    def _on_open_web(self, sender):
        logger.info("托盘菜单触发打开 Web")
        port = _get_naja_port()
        try:
            import webbrowser
            webbrowser.open(f"http://localhost:{port}")
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")

    def _on_open_logs(self, sender):
        logger.info("托盘菜单触发打开日志")
        log_dir = NAJA_DIR / "logs"
        try:
            import subprocess
            subprocess.run(["open", str(log_dir)], check=False)
        except Exception as e:
            logger.error(f"打开日志目录失败: {e}")

    def _on_quit(self, sender):
        logger.info("托盘菜单触发退出")
        import rumps
        pid = self._get_running_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        rumps.quit_application()

    def _on_refresh(self, sender):
        logger.info("刷新托盘数据")
        self._build_menu()

    def _on_sync_from_server(self, sender):
        """从服务器同步数据"""
        import threading
        import rumps
        
        logger.info("开始从服务器同步数据...")
        
        def sync_task():
            try:
                from deva.naja.state.system.server_sync_handler import ServerDataSyncHandler
                from datetime import datetime, timedelta
                
                handler = ServerDataSyncHandler()
                now = datetime.now()
                start = now - timedelta(hours=48)
                end = now
                
                result = handler.execute_wake_sync(start, end)
                
                if result.get('success'):
                    logger.info(f"服务器同步成功: {result.get('message', '')}")
                    rumps.notification(
                        title="☁️ 服务器同步成功",
                        subtitle="数据已从服务器更新",
                        message=result.get('message', '同步完成')
                    )
                else:
                    logger.warning(f"服务器同步失败: {result.get('message', '')}")
                    rumps.notification(
                        title="⚠️ 服务器同步失败",
                        subtitle="请检查网络连接",
                        message=result.get('message', '同步失败')
                    )
                
                # 同步完成后刷新菜单
                self._build_menu()
                
            except Exception as e:
                logger.error(f"服务器同步异常: {e}")
                import traceback
                traceback.print_exc()
                rumps.notification(
                    title="❌ 同步异常",
                    subtitle="发生错误",
                    message=str(e)
                )
        
        thread = threading.Thread(target=sync_task, daemon=True)
        thread.start()
        
        rumps.notification(
            title="☁️ 正在同步",
            subtitle="正在从服务器获取数据...",
            message="请稍候，同步完成后会通知您"
        )

    def _on_one_click_summary(self, sender):
        """一键总结：调用大模型总结时间线数据（带缓存）"""
        import threading
        import rumps
        
        logger.info("开始一键总结...")
        
        def summary_task():
            try:
                # 获取时间线数据
                timeline_data = self._get_timeline_events()
                
                if not timeline_data or not timeline_data.get('success'):
                    rumps.notification(
                        title="⚠️ 总结失败",
                        subtitle="无法获取时间线数据",
                        message="请稍后重试"
                    )
                    return
                
                events = timeline_data.get('list', [])
                if not events:
                    rumps.notification(
                        title="📭 暂无数据",
                        subtitle="没有可总结的内容",
                        message="时间线数据为空"
                    )
                    return
                
                # 先检查缓存
                cached_summary = self._get_cached_summary(events)
                if cached_summary:
                    logger.info("使用缓存的总结")
                    summary = cached_summary
                    rumps.notification(
                        title="📦 使用缓存",
                        subtitle="正在加载历史总结...",
                        message="1秒后显示"
                    )
                else:
                    # 构建提示词
                    prompt = self._build_summary_prompt(events)
                    
                    # 调用大模型
                    rumps.notification(
                        title="🧠 正在总结",
                        subtitle="正在分析市场动态...",
                        message="请稍候，总结完成后会通知您"
                    )
                    from deva.llm.client import sync_gpt
                    summary = sync_gpt(prompt)
                    
                    # 保存缓存
                    self._save_summary_cache(events, summary)
                    logger.info("总结已缓存")
                
                # 显示总结结果
                logger.info(f"总结完成: {summary[:100]}...")
                
                # 保存完整总结到本地文件
                summary_file = self._save_summary_to_file(summary)
                
                # 复制到剪贴板
                self._copy_to_clipboard(summary)
                
                # 发送到钉钉
                self._send_to_dingtalk(summary)
                
                # 显示简短通知，同时打开完整总结
                self._show_summary_notification(summary, summary_file)
                
            except Exception as e:
                logger.error(f"一键总结异常: {e}")
                import traceback
                traceback.print_exc()
                rumps.notification(
                    title="❌ 总结失败",
                    subtitle="发生错误",
                    message=str(e)[:100] if len(str(e)) > 100 else str(e)
                )
        
        thread = threading.Thread(target=summary_task, daemon=True)
        thread.start()

    def _build_summary_prompt(self, events):
        """构建大模型总结提示词（小红书爆款风格）"""
        from datetime import datetime
        
        prompt = f"""你是一个擅长写小红书爆款文案的财经博主。请根据以下24小时内的全球市场事件数据，生成一篇小红书风格的市场总结。

当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

市场事件数据：
"""
        for i, event in enumerate(events[:20], 1):
            event_type = event.get('type', 'unknown')
            time_str = event.get('time', '')
            title = event.get('title', '')
            change = event.get('change', '')
            score = event.get('score', '')
            
            type_label = {
                'cn_event': '🇨🇳 A股题材',
                'us_event': '🇺🇸 美股题材',
                'high_score_news': '📰 重要新闻',
                'jin10_news': '📌 金十快讯',
            }.get(event_type, event_type)
            
            prompt += f"{i}. [{time_str}] {type_label}"
            if change:
                prompt += f" 变动: {change}"
            if score:
                prompt += f" 评分: {score:.2f}" if isinstance(score, float) else f" 评分: {score}"
            prompt += f" - {title}\n"
        
        prompt += """

请生成一篇小红书爆款风格的市场总结，要求：
1. 🔥 开头第一句必须是核心结论，直接点明今天市场的关键特征
2. 📝 结论后面再展开细节，每段用一个emoji开头，一行一个要点
3. 💡 语言要轻松活泼，像和朋友聊天
4. 🎯 重点突出，用加粗**强调关键内容**
5. 📊 数据要直观，涨跌幅要醒目
6. ✨ 整体控制在8-12行，每行简短有力

例子风格：
🔥 **创新药**领涨！今天市场情绪火热！
📈 **创新药**板块爆发，涨幅惊人！
🇨🇳 A股题材轮动加快，把握节奏！
💡 建议关注政策驱动型机会～

直接给出文案，不要其他说明！"""
        
        return prompt

    def _save_summary_to_file(self, summary):
        """保存总结到本地文件，返回文件路径"""
        try:
            from datetime import datetime
            import os
            
            summary_dir = NAJA_DIR / "summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            summary_file = summary_dir / f"market_summary_{timestamp}.txt"
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"市场总结 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                f.write(summary)
            
            logger.info(f"总结已保存到: {summary_file}")
            return summary_file
        except Exception as e:
            logger.error(f"保存总结失败: {e}")
            return None

    def _copy_to_clipboard(self, text):
        """复制文本到剪贴板"""
        try:
            import subprocess
            
            # macOS 使用 pbcopy
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            
            logger.info("总结已复制到剪贴板")
            return True
        except Exception as e:
            logger.error(f"复制到剪贴板失败: {e}")
            return False

    def _send_to_dingtalk(self, summary):
        """发送总结到钉钉"""
        try:
            from datetime import datetime
            from deva.endpoints import Dtalk
            
            # 构建 Markdown 格式的消息
            title = f"📊 24小时市场总结 - {datetime.now().strftime('%m-%d %H:%M')}"
            markdown_content = f"@md@{title}|{summary}"
            
            # 发送到钉钉
            dtalk = Dtalk()
            markdown_content >> dtalk
            
            logger.info("总结已发送到钉钉")
            return True
        except Exception as e:
            logger.error(f"发送到钉钉失败: {e}")
            return False

    def _show_summary_notification(self, summary, summary_file):
        """显示总结通知并打开HTML页面"""
        import rumps
        import webbrowser
        from datetime import datetime
        
        # 简短通知
        if len(summary) > 100:
            summary_display = summary[:100] + "..."
        else:
            summary_display = summary
        
        rumps.notification(
            title="✨ 市场总结完成",
            subtitle="已复制到剪贴板并发送到钉钉",
            message=summary_display
        )
        
        # 生成并打开漂亮的HTML页面
        html_file = self._generate_html_summary(summary)
        if html_file:
            try:
                subprocess.run(['open', str(html_file)], check=False)
                logger.info(f"已打开HTML总结: {html_file}")
            except Exception as e:
                logger.error(f"打开HTML总结失败: {e}")

    def _generate_html_summary(self, summary):
        """生成漂亮的HTML总结页面"""
        try:
            from datetime import datetime
            
            summary_dir = NAJA_DIR / "summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            html_file = summary_dir / f"market_summary_{timestamp}.html"
            
            # 简单的Markdown转HTML（处理换行和基本格式）
            html_content = self._simple_markdown_to_html(summary)
            
            html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 24小时市场总结 - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
            color: #333;
        }}
        
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px;
            text-align: center;
            color: white;
        }}
        
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
            font-weight: 700;
        }}
        
        .header .time {{
            font-size: 14px;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 40px;
            line-height: 1.9;
            font-size: 17px;
        }}
        
        .content p {{
            margin-bottom: 14px;
        }}
        
        .content strong {{
            color: #667eea;
        }}
        
        .footer {{
            padding: 20px 40px;
            background: #f8f9fa;
            text-align: center;
            color: #666;
            font-size: 13px;
        }}
        
        .actions {{
            display: flex;
            gap: 12px;
            justify-content: center;
            margin-top: 20px;
            flex-wrap: wrap;
        }}
        
        .btn {{
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        
        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
        }}
        
        .btn-secondary {{
            background: #f0f0f0;
            color: #333;
        }}
        
        .btn-secondary:hover {{
            background: #e0e0e0;
        }}
        
        @media (max-width: 600px) {{
            .header, .content, .footer {{
                padding: 24px;
            }}
            .header h1 {{
                font-size: 22px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 24小时市场总结</h1>
            <div class="time">{datetime.now().strftime('%Y年%m月%d日 %H:%M')}</div>
        </div>
        
        <div class="content">
            {html_content}
        </div>
        
        <div class="footer">
            <p>由 Naja 智能生成 | <a href="#" onclick="window.close(); return false;" style="color: #667eea; text-decoration: none;">关闭窗口</a></p>
            <div class="actions">
                <button class="btn btn-primary" onclick="copyToClipboard()">📋 复制全文</button>
                <button class="btn btn-secondary" onclick="window.print()">🖨️ 打印</button>
            </div>
        </div>
    </div>
    
    <script>
        function copyToClipboard() {{
            const text = `{self._escape_js(summary)}`;
            navigator.clipboard.writeText(text).then(function() {{
                alert('已复制到剪贴板！');
            }}).catch(function(err) {{
                alert('复制失败，请手动选择复制');
            }});
        }}
    </script>
</body>
</html>"""
            
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_template)
            
            logger.info(f"HTML总结已生成: {html_file}")
            return html_file
        except Exception as e:
            logger.error(f"生成HTML总结失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _simple_markdown_to_html(self, text):
        """简单的文本转HTML（优化小红书风格）"""
        import re
        
        # 转义HTML特殊字符
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        # 处理换行 - 每行单独一段，更适合小红书风格
        lines = text.split('\n')
        html_lines = []
        for line in lines:
            line = line.strip()
            if line:
                # 处理加粗（**text**）
                line = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: #764ba2;">\1</strong>', line)
                html_lines.append(f'<p style="margin-bottom: 12px; font-size: 17px;">{line}</p>')
        
        return '\n'.join(html_lines)
    
    def _escape_js(self, text):
        """转义JavaScript字符串"""
        return text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
    
    def _get_events_hash(self, events):
        """生成事件列表的hash值，用于缓存key"""
        import hashlib
        import json
        
        # 只提取关键信息生成hash（避免微小变化也能用缓存
        simplified = []
        for event in events[:15]:  # 只用前15个事件
            simplified.append({
                'type': event.get('type', ''),
                'title': event.get('title', ''),
                'change': event.get('change', ''),
            })
        
        # 生成json字符串
        events_str = json.dumps(simplified, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(events_str.encode('utf-8')).hexdigest()
    
    def _get_cached_summary(self, events):
        """获取缓存的总结"""
        import time
        import json
        
        try:
            cache_dir = NAJA_DIR / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            events_hash = self._get_events_hash(events)
            cache_file = cache_dir / f"summary_{events_hash}.json"
            
            if not cache_file.exists():
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 检查是否过期（2小时 = 7200秒）
            cache_time = cache_data.get('timestamp', 0)
            if time.time() - cache_time > 7200:
                logger.info("缓存已过期")
                return None
            
            logger.info("找到缓存的总结")
            return cache_data.get('summary')
        except Exception as e:
            logger.error(f"读取缓存失败: {e}")
            return None
    
    def _save_summary_cache(self, events, summary):
        """保存总结到缓存"""
        import time
        import json
        
        try:
            cache_dir = NAJA_DIR / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            events_hash = self._get_events_hash(events)
            cache_file = cache_dir / f"summary_{events_hash}.json"
            
            cache_data = {
                'timestamp': time.time(),
                'events_hash': events_hash,
                'summary': summary
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"总结已缓存: {cache_file}")
            
            # 清理旧缓存（保留最近10个）
            self._cleanup_old_cache(cache_dir)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def _cleanup_old_cache(self, cache_dir):
        """清理旧缓存文件"""
        try:
            cache_files = sorted(
                cache_dir.glob("summary_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            # 只保留最近10个
            for old_file in cache_files[10:]:
                try:
                    old_file.unlink()
                    logger.info(f"清理旧缓存: {old_file.name}")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")

    def _get_system_status(self):
        """获取系统运行状态"""
        health_data = _http_get("/api/health")
        if health_data:
            return health_data
        return {"status": "unknown", "message": "无法连接"}

    def _build_menu(self):
        """构建托盘菜单（带完整异常保护）"""
        if self._app is None:
            return

        try:
            self._timeline_events = self._get_timeline_events()
        except Exception as e:
            logger.error(f"获取时间线数据失败: {e}")
            self._timeline_events = {"success": False, "stats": {}, "list": []}

        try:
            port = _get_naja_port()
        except Exception as e:
            logger.error(f"获取端口失败: {e}")
            port = 8080

        try:
            system_status = self._get_system_status()
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            system_status = {}

        try:
            import rumps

            icon_path = ICON_GREEN if _is_trading_time() else ICON_PURPLE
            self._app.icon = icon_path

            self._app.menu.clear()
            
            # 服务状态区域
            self._app.menu["📊 Naja 管理平台"] = None
            status_text = "🟢 运行中" if self._get_running_pid() else "🔴 已停止"
            self._app.menu[status_text] = None
            self._app.menu[f"📍 端口: {port}"] = None
            self._app.menu["sep0"] = rumps.separator
            
            # 常用页面区域 - 使用 add 方法创建子菜单
            common_pages = rumps.MenuItem("📈 常用页面")
            common_pages.add(rumps.MenuItem("🔥 市场热点", callback=self._on_open_page("/market")))
            common_pages.add(rumps.MenuItem("⚡ 交易中心", callback=self._on_open_page("/awakening")))
            common_pages.add(rumps.MenuItem("🧠 认知系统", callback=self._on_open_page("/cognition")))
            common_pages.add(rumps.MenuItem("📜 系统日志", callback=self._on_open_page("/logstream")))
            common_pages.add(rumps.MenuItem("⚙️ 系统状态", callback=self._on_open_page("/health")))
            self._app.menu.add(common_pages)
            
            # 管理页面区域 - 使用 add 方法创建子菜单
            admin_tools = rumps.MenuItem("🔧 管理工具")
            admin_tools.add(rumps.MenuItem("📋 策略管理", callback=self._on_open_page("/strategyadmin")))
            admin_tools.add(rumps.MenuItem("📊 信号管理", callback=self._on_open_page("/signaladmin")))
            admin_tools.add(rumps.MenuItem("📁 数据源管理", callback=self._on_open_page("/dsadmin")))
            admin_tools.add(rumps.MenuItem("📅 任务管理", callback=self._on_open_page("/taskadmin")))
            self._app.menu.add(admin_tools)
            
            self._app.menu["sep1"] = rumps.separator
            
            # 主功能区域
            self._app.menu.add(rumps.MenuItem("🌐 打开 Web", callback=self._on_open_web))
            self._app.menu.add(rumps.MenuItem("📄 打开日志", callback=self._on_open_logs))
            self._app.menu.add(rumps.MenuItem("🔄 刷新", callback=self._on_refresh))
            self._app.menu.add(rumps.MenuItem("☁️ 从服务器同步", callback=self._on_sync_from_server))
            self._app.menu["sep2"] = rumps.separator
            
            # --- 开始：24 小时时间线风格菜单 ---
            try:
                if self._timeline_events and self._timeline_events.get("success", False):
                    # 统计条
                    stats = self._timeline_events.get('stats', {})
                    cn_count = stats.get('cn_events', 0)
                    us_count = stats.get('us_events', 0)
                    news_count = stats.get('high_score_news', 0)
                    jin10_count = stats.get('jin10_news', 0)
                    
                    stats_menu = rumps.MenuItem(f"⏰ 全球市场时间线 | 🇨🇳 {cn_count} | 🇺🇸 {us_count} | 📰 {news_count} | 📌 {jin10_count}")
                    stats_menu.set_callback(self._on_open_page("/market"))
                    self._app.menu.add(stats_menu)
                    
                    # 添加一键总结按钮
                    self._app.menu.add(rumps.MenuItem("✨ 一键总结当前时间线", callback=self._on_one_click_summary))
                    
                    events = self._timeline_events.get('list', [])
                    last_date = None
                    
                    # 最多显示 20 条，避免菜单太长
                    display_events = events[:20]
                    
                    for event in display_events:
                        try:
                            event_date = event.get('date', '')
                            event_time = event.get('time', '')
                            event_type = event.get('type', '')
                            title = event.get('title', '')
                            url = event.get('url', '')
                            change = event.get('change', '')
                            
                            # 日期分隔
                            if event_date != last_date:
                                self._app.menu.add(rumps.MenuItem(f"{'─'*30}"))
                                self._app.menu.add(rumps.MenuItem(f"📅 {event_date}"))
                                last_date = event_date
                            
                            # 事件菜单项
                            if event_type == 'cn_event':
                                menu_text = f"{event_time} 🇨🇳 {change} {title}"
                                callback = self._on_open_page("/market")
                            elif event_type == 'us_event':
                                menu_text = f"{event_time} 🇺🇸 {change} {title}"
                                callback = self._on_open_page("/market")
                            elif event_type == 'high_score_news':
                                score = event.get('score', 0)
                                stars = '⭐' * min(5, int(score * 5 + 0.5))
                                menu_text = f"{event_time} 📰 {stars} {title}"
                                callback = self._on_open_page("/cognition")
                            elif event_type == 'jin10_news':
                                menu_text = f"{event_time} 📌 {title}"
                                
                                def make_callback(news_url):
                                    def callback(sender):
                                        if news_url:
                                            import webbrowser
                                            webbrowser.open(news_url)
                                    return callback
                                
                                callback = make_callback(url) if url else None
                            else:
                                menu_text = f"{event_time} {title}"
                                callback = None
                            
                            menu_item = rumps.MenuItem(menu_text, callback=callback)
                            self._app.menu.add(menu_item)
                        except Exception as e:
                            logger.error(f"添加时间线事件失败: {e}")
                else:
                    self._app.menu.add(rumps.MenuItem("⏰ 暂无时间线数据"))
            except Exception as e:
                logger.error(f"构建时间线菜单失败: {e}")
                self._app.menu.add(rumps.MenuItem("⚠️ 时间线加载失败"))
            
            self._app.menu["sep3"] = rumps.separator
            self._app.menu["重启服务"] = rumps.MenuItem("🔄 重启服务", callback=self._on_reload)
            self._app.menu["退出"] = rumps.MenuItem("❌ 退出", callback=self._on_quit)

        except Exception as e:
            logger.error(f"更新菜单失败: {e}")
            import traceback
            traceback.print_exc()
            # 尝试恢复菜单到最小状态
            try:
                self._app.menu.clear()
                self._app.menu["📊 Naja 管理平台"] = None
                self._app.menu["⚠️ 菜单更新失败"] = None
                self._app.menu["sep0"] = rumps.separator
                self._app.menu["重启服务"] = rumps.MenuItem("🔄 重启服务", callback=self._on_reload)
                self._app.menu["退出"] = rumps.MenuItem("❌ 退出", callback=self._on_quit)
            except Exception as restore_e:
                logger.error(f"恢复菜单失败: {restore_e}")
    
    def _on_open_page(self, path):
        """打开指定页面"""
        def callback(sender):
            logger.info(f"托盘菜单触发打开页面: {path}")
            port = _get_naja_port()
            try:
                import webbrowser
                webbrowser.open(f"http://localhost:{port}{path}")
            except Exception as e:
                logger.error(f"打开浏览器失败: {e}")
        return callback

    def start(self):
        if not self.is_available():
            logger.warning("菜单栏托盘在非 macOS 系统上不可用")
            return

        if self._app is not None:
            logger.info("托盘已启动")
            return

        try:
            import rumps

            initial_icon = ICON_GREEN if _is_trading_time() else ICON_PURPLE
            self._app = rumps.App("Naja", icon=initial_icon)
            self._build_menu()

            rumps.timer(interval=30)(self._on_timer)(self._app)

            self._app.run()
        except Exception as e:
            logger.error(f"启动托盘失败: {e}")

    def _on_timer(self, _sender):
        self._build_menu()

    def stop(self):
        import rumps
        if self._app:
            rumps.quit_application()
            self._app = None

    def update_data(self):
        self._build_menu()


_tray_instance: Optional[MenuBarTray] = None


def get_tray() -> MenuBarTray:
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = MenuBarTray()
    return _tray_instance


def start_tray():
    tray = get_tray()
    if tray.is_available():
        tray.start()
    else:
        logger.warning("菜单栏托盘不可用（需要 macOS 和 rumps 库）")


def stop_tray():
    tray = get_tray()
    tray.stop()
