"""
Backfillers - 各组件的补执行实现

包括：
1. AIDailyReportBackfiller - AI日报补执行
2. NewsFetcherBackfiller - 新闻获取补执行
3. GlobalMarketScannerBackfiller - 全球市场扫描补执行
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple

log = logging.getLogger(__name__)


class AIDailyReportBackfiller:
    """
    AI日报补执行器

    判断逻辑：
    1. 凌晨 0-7点：前一天的新闻陆续出来 → 补昨天的
    2. 白天 8-20点：检查昨天是否执行，没执行就补
    3. 晚上 20点后：今天的任务可能刚错过 → 补今天的
    """

    @property
    def name(self) -> str:
        return "AI_Daily_Report"

    @property
    def description(self) -> str:
        return "AI日报补执行（每天定时生成AI新闻摘要）"

    def should_backfill(self, last_active: datetime) -> bool:
        """判断是否需要补执行"""
        now = datetime.now()
        current_hour = now.hour

        today_str = now.strftime("%Y%m%d")
        report_file_today = f"/Users/spark/.naja/ai_reports/{today_str}_v2.txt"

        yesterday = now - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y%m%d")
        report_file_yesterday = f"/Users/spark/.naja/ai_reports/{yesterday_str}_v2.txt"

        if 0 <= current_hour < 8:
            return not os.path.exists(report_file_yesterday)
        elif 8 <= current_hour < 20:
            return not os.path.exists(report_file_yesterday)
        else:
            return not os.path.exists(report_file_today)

    def get_backfill_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取补执行时间范围"""
        now = datetime.now()
        current_hour = now.hour

        if 0 <= current_hour < 8:
            target_date = now - timedelta(days=1)
        elif 8 <= current_hour < 20:
            target_date = now - timedelta(days=1)
        else:
            target_date = now

        start = target_date.replace(hour=20, minute=0, second=0, microsecond=0)
        end = now

        if end - start > timedelta(hours=max_hours):
            end = start + timedelta(hours=max_hours)

        return start, end

    def execute_backfill(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行补执行"""
        try:
            from deva.naja.tasks.ai_daily_report import execute as run_ai_daily_report

            log.info(f"[Backfill] AI日报开始补执行: {start} ~ {end}")

            result = run_ai_daily_report()

            if result and result.get("success"):
                return {
                    "success": True,
                    "message": "AI日报补执行成功",
                    "details": result
                }
            else:
                return {
                    "success": False,
                    "message": f"AI日报补执行失败: {result.get('error', '未知错误')}",
                    "details": result
                }

        except Exception as e:
            log.error(f"[Backfill] AI日报补执行异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"AI日报补执行异常: {str(e)}",
                "details": {}
            }


class NewsFetcherBackfiller:
    """
    新闻获取补执行器

    判断逻辑：检查新闻获取记录，如果超过一定时间没有获取则补执行
    使用金十重要新闻 API 获取历史新闻
    """

    JIN10_IMPORTANT_API = "https://flash-api.jin10.com/get_flash_list"

    @property
    def name(self) -> str:
        return "News_Fetcher"

    @property
    def description(self) -> str:
        return "新闻获取补执行（从金十重要新闻获取历史快讯）"

    def should_backfill(self, last_active: datetime) -> bool:
        """判断是否需要补执行"""
        try:
            from deva.naja.radar.news_fetcher import RadarNewsFetcher
            fetcher = RadarNewsFetcher()

            if not hasattr(fetcher, '_last_fetch_time'):
                log.info("[Backfill] NewsFetcher: 无法获取上次获取时间，跳过")
                return False

            last_fetch = fetcher._last_fetch_time
            if not last_fetch:
                return True

            now = datetime.now()
            if isinstance(last_fetch, (int, float)):
                last_fetch = datetime.fromtimestamp(last_fetch)

            gap = (now - last_fetch).total_seconds()
            log.info(f"[Backfill] NewsFetcher: 距上次获取 {gap/3600:.2f} 小时")

            return gap > 3600

        except Exception as e:
            log.warning(f"[Backfill] NewsFetcher: 检查失败 - {e}")
            return False

    def get_backfill_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取补执行时间范围"""
        now = datetime.now()

        try:
            from deva.naja.radar.news_fetcher import RadarNewsFetcher
            fetcher = RadarNewsFetcher()

            if hasattr(fetcher, '_last_fetch_time') and fetcher._last_fetch_time:
                last_fetch = fetcher._last_fetch_time
                if isinstance(last_fetch, (int, float)):
                    last_fetch = datetime.fromtimestamp(last_fetch)
                start = last_fetch
            else:
                start = now - timedelta(hours=max_hours)
        except:
            start = now - timedelta(hours=max_hours)

        end = now

        if end - start > timedelta(hours=max_hours):
            end = start + timedelta(hours=max_hours)

        return start, end

    def execute_backfill(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行补执行 - 使用金十重要新闻 API"""
        try:
            import requests
            import asyncio
            from dataclasses import dataclass
            from typing import Optional, List

            log.info(f"[Backfill] NewsFetcher开始补执行: {start} ~ {end}")

            @dataclass
            class Jin10NewsItem:
                id: str
                content: str
                url: str
                time: str
                source: str = "jin10"

            async def fetch_news_list_async() -> List[Jin10NewsItem]:
                """异步获取金十新闻列表"""
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Origin': 'https://www.jin10.com',
                    'Referer': 'https://www.jin10.com/',
                })

                all_news = []
                maxid = 0

                for _ in range(100):
                    try:
                        response = session.post(
                            self.JIN10_IMPORTANT_API,
                            json={
                                "channel": "-8200",
                                "maxid": maxid,
                                "category": "1",
                                "limit": 20
                            },
                            timeout=15
                        )

                        if response.status_code == 200:
                            data = response.json()
                            if data.get('status') == 200:
                                items = data.get('data', [])
                                if not items:
                                    break

                                for item in items:
                                    time_str = item.get('time', '')
                                    if time_str:
                                        try:
                                            item_time = datetime.fromtimestamp(float(time_str))
                                            if item_time < start:
                                                break
                                            if item_time <= end:
                                                news_url = item.get('url', '')
                                                if not news_url:
                                                    news_url = f"https://www.jin10.com/news/{item.get('id', '')}"
                                                all_news.append(Jin10NewsItem(
                                                    id=str(item.get('id', '')),
                                                    content=item.get('content', ''),
                                                    url=news_url,
                                                    time=time_str,
                                                ))
                                        except:
                                            pass

                                maxid = data.get('maxid', maxid + 20)

                                if item and time_str:
                                    try:
                                        last_item_time = datetime.fromtimestamp(float(time_str))
                                        if last_item_time < start:
                                            break
                                    except:
                                        pass
                            else:
                                break
                        else:
                            break

                    except Exception as e:
                        log.warning(f"[Backfill] NewsFetcher: 获取列表失败 - {e}")
                        await asyncio.sleep(1)

                return all_news

            async def fetch_news_detail_async(session: requests.Session, news: Jin10NewsItem) -> Optional[Jin10NewsItem]:
                """异步获取单条新闻详情"""
                try:
                    response = session.get(news.url, timeout=15)
                    if response.status_code == 200:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                        article = soup.find('div', class_='article-content')
                        if article:
                            news.content = article.get_text(strip=True)
                    return news
                except Exception as e:
                    log.warning(f"[Backfill] NewsFetcher: 获取详情失败 {news.url}: {e}")
                    return news

            async def publish_to_radar(news: Jin10NewsItem):
                """发布新闻到雷达系统"""
                try:
                    from deva.naja.radar.news_fetcher import RadarNewsFetcher, NewsItem
                    from deva.naja.cognition.attention_text_router import (
                        AttentionTextItem,
                        TextSource,
                    )

                    fetcher = RadarNewsFetcher()

                    news_item = NewsItem(
                        id=news.id,
                        content=news.content,
                        title="",
                        url=news.url,
                        source=news.source,
                    )

                    item = AttentionTextItem(
                        text=news_item.content,
                        title=news_item.title,
                        url=news_item.url,
                        source=TextSource.RADAR_NEWS,
                        metadata={
                            "news_id": news_item.id,
                            "original_source": news_item.source,
                            "backfill": True,
                        },
                    )

                    if hasattr(fetcher, '_text_pipeline') and fetcher._text_pipeline:
                        item = fetcher._text_pipeline.process(item)

                    if hasattr(fetcher, '_text_bus') and fetcher._text_bus:
                        fetcher._text_bus.publish(item)

                    log.info(f"[Backfill] NewsFetcher: 已发布到雷达 {news.content[:50]}...")

                except Exception as e:
                    log.warning(f"[Backfill] NewsFetcher: 发布到雷达失败: {e}")

            async def main_async():
                news_list = await fetch_news_list_async()
                log.info(f"[Backfill] NewsFetcher: 获取到 {len(news_list)} 条新闻")

                if not news_list:
                    return {"success": False, "message": "未获取到新闻", "details": {}}

                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                })

                published_count = 0
                for news in news_list:
                    await publish_to_radar(news)
                    published_count += 1
                    await asyncio.sleep(0.5)

                return {
                    "success": True,
                    "message": f"补执行成功，获取并发布 {published_count} 条新闻",
                    "details": {
                        "count": published_count,
                        "first_news": news_list[0].content[:100] if news_list else "",
                        "last_news": news_list[-1].content[:100] if news_list else "",
                    }
                }

            return asyncio.run(main_async())

        except Exception as e:
            log.error(f"[Backfill] NewsFetcher补执行异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"新闻获取补执行异常: {str(e)}",
                "details": {}
            }


class GlobalMarketScannerBackfiller:
    """
    全球市场扫描补执行器

    判断逻辑：检查市场扫描记录，如果超过一定时间没有扫描则补执行
    """

    @property
    def name(self) -> str:
        return "Global_Market_Scanner"

    @property
    def description(self) -> str:
        return "全球市场扫描补执行（监控全球主要市场行情）"

    def should_backfill(self, last_active: datetime) -> bool:
        """判断是否需要补执行"""
        try:
            from deva.naja.radar.global_market_scanner import GlobalMarketScanner
            scanner = GlobalMarketScanner()

            if not hasattr(scanner, '_last_scan_time'):
                log.info("[Backfill] GlobalMarketScanner: 无法获取上次扫描时间，跳过")
                return False

            last_scan = scanner._last_scan_time
            if not last_scan:
                return True

            now = datetime.now()
            if isinstance(last_scan, (int, float)):
                last_scan = datetime.fromtimestamp(last_scan)

            gap = (now - last_scan).total_seconds()
            log.info(f"[Backfill] GlobalMarketScanner: 距上次扫描 {gap/3600:.2f} 小时")

            return gap > 3600

        except Exception as e:
            log.warning(f"[Backfill] GlobalMarketScanner: 检查失败 - {e}")
            return False

    def get_backfill_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取补执行时间范围"""
        now = datetime.now()

        try:
            from deva.naja.radar.global_market_scanner import GlobalMarketScanner
            scanner = GlobalMarketScanner()

            if hasattr(scanner, '_last_scan_time') and scanner._last_scan_time:
                last_scan = scanner._last_scan_time
                if isinstance(last_scan, (int, float)):
                    last_scan = datetime.fromtimestamp(last_scan)
                start = last_scan
            else:
                start = now - timedelta(hours=max_hours)
        except:
            start = now - timedelta(hours=max_hours)

        end = now

        if end - start > timedelta(hours=max_hours):
            end = start + timedelta(hours=max_hours)

        return start, end

    def execute_backfill(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行补执行"""
        try:
            from deva.naja.radar.global_market_scanner import GlobalMarketScanner

            log.info(f"[Backfill] GlobalMarketScanner开始补执行: {start} ~ {end}")

            scanner = GlobalMarketScanner()

            if hasattr(scanner, 'scan_markets'):
                result = scanner.scan_markets()
            elif hasattr(scanner, 'fetch_market_data'):
                result = scanner.fetch_market_data()
            else:
                return {
                    "success": False,
                    "message": "GlobalMarketScanner没有可调用的扫描方法",
                    "details": {}
                }

            if result and result.get("success"):
                return {
                    "success": True,
                    "message": "全球市场扫描补执行成功",
                    "details": result
                }
            else:
                return {
                    "success": False,
                    "message": f"全球市场扫描补执行失败: {result.get('error', '未知错误')}",
                    "details": result
                }

        except Exception as e:
            log.error(f"[Backfill] GlobalMarketScanner补执行异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"全球市场扫描补执行异常: {str(e)}",
                "details": {}
            }


class MarketReplayBackfiller:
    """
    盘后复盘补执行器

    判断逻辑：
    1. 检查今天是否已复盘
    2. 如果当前处于收盘后时段（15:30后），则触发复盘
    3. 如果当前不是收盘后时段，记录状态，下次交易时钟触发时执行

    注意事项：
    - 复盘必须在收盘后才能执行
    - 盘后可以获取最后一个交易日的快照数据
    """

    @property
    def name(self) -> str:
        return "Market_Replay"

    @property
    def description(self) -> str:
        return "盘后复盘补执行（收盘后自动复盘当日行情）"

    def should_backfill(self, last_active: datetime) -> bool:
        """判断是否需要补执行"""
        try:
            from deva.naja.strategy.market_replay_scheduler import get_replay_scheduler
            from deva.naja.radar.trading_clock import get_trading_clock

            scheduler = get_replay_scheduler()
            tc = get_trading_clock()

            now = datetime.now()

            if now.weekday() >= 5:
                log.info("[Backfill] MarketReplay: 周末，跳过")
                return False

            if scheduler._check_already_replayed_today(phase='post_market'):
                log.info("[Backfill] MarketReplay: 今天已复盘，跳过")
                return False

            current_phase = tc.current_phase
            log.info(f"[Backfill] MarketReplay: 当前阶段={current_phase}")

            if current_phase == 'post_market':
                return True
            elif current_phase == 'closed':
                if now.time().hour >= 15 and now.time().minute >= 30:
                    return True
                else:
                    log.info("[Backfill] MarketReplay: 收盘后但未到15:30，跳过")
                    return False
            else:
                log.info(f"[Backfill] MarketReplay: 当前阶段{current_phase}不适合复盘，跳过")
                return False

        except Exception as e:
            log.warning(f"[Backfill] MarketReplay: 检查失败 - {e}")
            return False

    def get_backfill_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取补执行时间范围"""
        now = datetime.now()
        start = now - timedelta(hours=24)
        end = now
        return start, end

    def execute_backfill(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行补执行"""
        try:
            from deva.naja.strategy.market_replay_scheduler import get_replay_scheduler

            log.info(f"[Backfill] MarketReplay开始补执行")

            scheduler = get_replay_scheduler()

            if hasattr(scheduler, 'trigger_manual_replay'):
                success = scheduler.trigger_manual_replay(phase='post_market')
                if success:
                    return {
                        "success": True,
                        "message": "盘后复盘补执行触发成功",
                        "details": {}
                    }
                else:
                    return {
                        "success": False,
                        "message": "盘后复盘补执行触发失败",
                        "details": {}
                    }
            else:
                return {
                    "success": False,
                    "message": "MarketReplayScheduler没有trigger_manual_replay方法",
                    "details": {}
                }

        except Exception as e:
            log.error(f"[Backfill] MarketReplay补执行异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"盘后复盘补执行异常: {str(e)}",
                "details": {}
            }