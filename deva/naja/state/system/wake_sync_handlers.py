"""
WakeSyncHandlers - 各组件的唤醒同步实现

包括：
1. AIDailyReportWakeSync - AI日报同步
2. NewsFetcherWakeSync - 新闻获取同步
3. GlobalMarketScannerWakeSync - 全球市场扫描同步
4. DailyReviewWakeSync - 盘后复盘同步
5. PortfolioPriceWakeSync - 持仓价格同步

优先级设计（数字越小优先级越高）：
1. PortfolioPriceWakeSync - 持仓价格（影响风控和决策）
2. NewsFetcherWakeSync - 新闻（实时性要求高）
3. GlobalMarketScannerWakeSync - 全球市场（持续监控）
4. DailyReviewWakeSync - 盘后复盘（需要在正确时间执行）
5. AIDailyReportWakeSync - AI日报（一天一次，不急）
"""

import os
import logging
import time
from datetime import datetime, timedelta, time as dtime
from typing import Dict, Any, Tuple
from deva.naja.register import SR

log = logging.getLogger(__name__)


class AIDailyReportWakeSync:
    """
    AI日报同步器

    判断逻辑：
    1. 凌晨 0-7点：前一天的新闻陆续出来 → 同步昨天的
    2. 白天 8-20点：检查昨天是否执行，没执行就同步
    3. 晚上 20点后：今天的任务可能刚错过 → 同步今天的
    """

    @property
    def name(self) -> str:
        return "AI_Daily_Report"

    @property
    def description(self) -> str:
        return "AI日报同步（每天定时生成AI新闻摘要）"

    @property
    def priority(self) -> int:
        return 5

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要同步"""
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

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取同步时间范围"""
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

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行同步"""
        try:
            from deva.naja.tasks.ai_daily_report import execute as run_ai_daily_report

            log.info(f"[WakeSync] AI日报开始同步: {start} ~ {end}")

            result = run_ai_daily_report()

            if result and result.get("success"):
                return {
                    "success": True,
                    "message": "AI日报同步成功",
                    "details": result
                }
            else:
                return {
                    "success": False,
                    "message": f"AI日报同步失败: {result.get('error', '未知错误')}",
                    "details": result
                }

        except Exception as e:
            log.error(f"[WakeSync] AI日报同步异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"AI日报同步异常: {str(e)}",
                "details": {}
            }


class NewsFetcherWakeSync:
    """
    新闻获取同步器

    判断逻辑：检查新闻获取记录，如果超过一定时间没有获取则同步
    使用金十重要新闻 API 获取历史新闻
    """

    JIN10_IMPORTANT_API = "https://flash-api.jin10.com/get_flash_list"

    @property
    def name(self) -> str:
        return "News_Fetcher"

    @property
    def description(self) -> str:
        return "新闻获取同步（从金十重要新闻获取历史快讯）"

    @property
    def priority(self) -> int:
        return 2

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要同步"""
        try:
            from deva.naja.radar.news_fetcher import RadarNewsFetcher
            fetcher = RadarNewsFetcher()

            if not hasattr(fetcher, '_last_fetch_time'):
                log.info("[WakeSync] NewsFetcher: 无法获取上次获取时间，跳过")
                return False

            last_fetch = fetcher._last_fetch_time
            if not last_fetch:
                return True

            now = datetime.now()
            if isinstance(last_fetch, (int, float)):
                last_fetch = datetime.fromtimestamp(last_fetch)

            gap = (now - last_fetch).total_seconds()
            log.info(f"[WakeSync] NewsFetcher: 距上次获取 {gap/3600:.2f} 小时")

            return gap > 3600

        except Exception as e:
            log.warning(f"[WakeSync] NewsFetcher: 检查失败 - {e}")
            return False

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取同步时间范围"""
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

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行同步 - 使用金十重要新闻 API"""
        try:
            import requests
            import asyncio
            from dataclasses import dataclass
            from typing import Optional, List

            log.info(f"[WakeSync] NewsFetcher开始同步: {start} ~ {end}")

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
                        log.warning(f"[WakeSync] NewsFetcher: 获取列表失败 - {e}")
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
                    log.warning(f"[WakeSync] NewsFetcher: 获取详情失败 {news.url}: {e}")
                    return news

            async def publish_to_radar(news: Jin10NewsItem):
                """发布新闻到雷达系统"""
                try:
                    from deva.naja.events import get_event_bus
                    from deva.naja.events.text_events import TextFetchedEvent

                    event = TextFetchedEvent(
                        text=news.content,
                        title="",
                        source="radar_news",
                        url=news.url,
                        timestamp=time.time(),
                        keywords=[],
                        topics=[],
                        sentiment=0.5,
                        stock_codes=[],
                    )
                    get_event_bus().publish(event)

                    log.info(f"[WakeSync] NewsFetcher: 已发布到雷达 {news.content[:50]}...")

                except Exception as e:
                    log.warning(f"[WakeSync] NewsFetcher: 发布到雷达失败: {e}")

            async def main_async():
                news_list = await fetch_news_list_async()
                log.info(f"[WakeSync] NewsFetcher: 获取到 {len(news_list)} 条新闻")

                if not news_list:
                    return {"success": False, "message": "未获取到新闻", "details": {}}

                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                })

                fetched_detail_count = 0
                published_count = 0
                for news in news_list:
                    if news.content and len(news.content) > 100:
                        log.debug(f"[WakeSync] NewsFetcher: 新闻 {news.id} 内容已完整，跳过详情获取")
                    else:
                        detail = await fetch_news_detail_async(session, news)
                        if detail:
                            fetched_detail_count += 1

                    await publish_to_radar(news)
                    published_count += 1
                    await asyncio.sleep(0.5)

                return {
                    "success": True,
                    "message": f"同步成功，获取并发布 {published_count} 条新闻（详情获取 {fetched_detail_count} 条）",
                    "details": {
                        "count": published_count,
                        "detail_count": fetched_detail_count,
                        "first_news": news_list[0].content[:100] if news_list else "",
                        "last_news": news_list[-1].content[:100] if news_list else "",
                    }
                }

            return asyncio.run(main_async())

        except Exception as e:
            log.error(f"[WakeSync] NewsFetcher同步异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"新闻获取同步异常: {str(e)}",
                "details": {}
            }


class GlobalMarketScannerWakeSync:
    """
    全球市场扫描同步器

    判断逻辑：检查市场扫描记录，如果超过一定时间没有扫描则同步
    """

    @property
    def name(self) -> str:
        return "Global_Market_Scanner"

    @property
    def description(self) -> str:
        return "全球市场扫描同步（监控全球主要市场行情）"

    @property
    def priority(self) -> int:
        return 3

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要同步"""
        try:
            from deva.naja.radar.global_market_scanner import GlobalMarketScanner
            scanner = GlobalMarketScanner()

            if not hasattr(scanner, '_last_scan_time'):
                log.info("[WakeSync] GlobalMarketScanner: 无法获取上次扫描时间，跳过")
                return False

            last_scan = scanner._last_scan_time
            if not last_scan:
                return True

            now = datetime.now()
            if isinstance(last_scan, (int, float)):
                last_scan = datetime.fromtimestamp(last_scan)

            gap = (now - last_scan).total_seconds()
            log.info(f"[WakeSync] GlobalMarketScanner: 距上次扫描 {gap/3600:.2f} 小时")

            return gap > 3600

        except Exception as e:
            log.warning(f"[WakeSync] GlobalMarketScanner: 检查失败 - {e}")
            return False

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取同步时间范围"""
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

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行同步"""
        try:
            from deva.naja.radar.global_market_scanner import GlobalMarketScanner

            log.info(f"[WakeSync] GlobalMarketScanner开始同步: {start} ~ {end}")

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
                    "message": "全球市场扫描同步成功",
                    "details": result
                }
            else:
                return {
                    "success": False,
                    "message": f"全球市场扫描同步失败: {result.get('error', '未知错误')}",
                    "details": result
                }

        except Exception as e:
            log.error(f"[WakeSync] GlobalMarketScanner同步异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"全球市场扫描同步异常: {str(e)}",
                "details": {}
            }


class DailyReviewWakeSync:
    """
    盘后复盘同步器

    支持 A股和美股复盘：
    - A股盘后：15:30 后（北京时间）
    - 美股盘后：04:00/05:00 后（北京时间）

    判断逻辑：
    1. 检查今天是否已复盘
    2. 如果当前处于收盘后时段，则触发复盘
    3. 两个市场独立判断
    """

    @property
    def name(self) -> str:
        return "Daily_Review"

    @property
    def description(self) -> str:
        return "盘后复盘同步（A股+美股收盘后自动复盘）"

    @property
    def priority(self) -> int:
        return 4

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要同步"""
        try:
            from deva.naja.strategy.daily_review_scheduler import get_daily_review_scheduler

            scheduler = get_daily_review_scheduler()
            tc = SR('trading_clock')

            now = datetime.now()

            # 检查 A股
            if now.weekday() < 5:  # 非周末
                if not scheduler._check_already_replayed_today(market='a_share', phase='post_market'):
                    current_phase = tc.cn_phase
                    if current_phase == 'post_market' or (current_phase == 'closed' and now.time() >= dtime(15, 30)):
                        log.info("[WakeSync] DailyReview: A股满足复盘条件")
                        return True

            # 检查美股
            if not scheduler._check_already_replayed_today(market='us_share', phase='post_market'):
                us_phase = tc.us_phase
                us_hour = now.hour
                is_us_post_market_time = us_hour >= 4
                if us_phase == 'post_market' or (us_phase == 'closed' and is_us_post_market_time):
                    log.info("[WakeSync] DailyReview: 美股满足复盘条件")
                    return True

            log.info("[WakeSync] DailyReview: 两个市场都不满足复盘条件，跳过")
            return False

        except Exception as e:
            log.warning(f"[WakeSync] DailyReview: 检查失败 - {e}")
            return False

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取同步时间范围"""
        now = datetime.now()
        start = now - timedelta(hours=24)
        end = now
        return start, end

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行同步"""
        try:
            from deva.naja.strategy.daily_review_scheduler import get_daily_review_scheduler

            log.info(f"[WakeSync] DailyReview开始同步")

            scheduler = get_daily_review_scheduler()
            results = []

            # A股复盘
            try:
                scheduler.trigger_manual_replay(market='a_share', phase='post_market')
                results.append("A股复盘已触发")
            except Exception as e:
                results.append(f"A股复盘失败: {e}")

            # 美股复盘
            try:
                scheduler.trigger_manual_replay(market='us_share', phase='post_market')
                results.append("美股复盘已触发")
            except Exception as e:
                results.append(f"美股复盘失败: {e}")

            return {
                "success": True,
                "message": " | ".join(results),
                "details": {"replays": results}
            }

        except Exception as e:
            log.error(f"[WakeSync] DailyReview同步异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"盘后复盘同步异常: {str(e)}",
                "details": {}
            }


class PortfolioPriceWakeSync:
    """
    持仓价格同步器

    功能：
    - 通知 MarketObserver 更新持仓股票的价格
    - 确保虚拟组合的持仓价格与市场同步

    设计理念：
    - 各组件自己拉取，WakeSync 只负责通知
    - 渐进式执行，不影响系统整体性能
    """

    @property
    def name(self) -> str:
        return "Portfolio_Price"

    @property
    def description(self) -> str:
        return "持仓价格同步（更新虚拟组合持仓的市场价格）"

    @property
    def priority(self) -> int:
        return 1

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要同步"""
        try:
            from deva.naja.bandit.market_observer import MarketDataObserver

            observer = MarketDataObserver()
            now = datetime.now()

            if not hasattr(observer, '_last_prices') or not observer._last_prices:
                log.info("[WakeSync] PortfolioPrice: 无缓存价格，需要同步")
                return True

            last_prices = observer._last_prices
            if not last_prices:
                return True

            gap = (now - last_active).total_seconds()
            log.info(f"[WakeSync] PortfolioPrice: 距上次活跃 {gap/3600:.2f} 小时")

            return gap > 300

        except Exception as e:
            log.warning(f"[WakeSync] PortfolioPrice: 检查失败 - {e}")
            return False

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取同步时间范围"""
        now = datetime.now()
        start = now - timedelta(hours=1)
        end = now
        return start, end

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行同步 - 通知各组件拉取"""
        try:
            from deva.naja.bandit.market_observer import MarketDataObserver
            import threading

            log.info(f"[WakeSync] PortfolioPrice开始同步")

            observer = MarketDataObserver()

            tracked_stocks = list(observer._tracked_stocks) if observer._tracked_stocks else []

            if not tracked_stocks:
                log.info("[WakeSync] PortfolioPrice: 无跟踪股票，跳过")
                return {
                    "success": True,
                    "message": "无跟踪股票",
                    "details": {"count": 0}
                }

            def async_fetch():
                """后台异步拉取价格"""
                try:
                    if hasattr(observer, '_fetch_prices_from_datasource'):
                        observer._fetch_prices_from_datasource()
                        log.info(f"[WakeSync] PortfolioPrice: 后台完成 {len(tracked_stocks)} 只股票价格更新")
                except Exception as e:
                    log.warning(f"[WakeSync] PortfolioPrice: 后台拉取失败 - {e}")

            thread = threading.Thread(target=async_fetch, daemon=True, name='portfolio-price-wake-sync')
            thread.start()

            log.info(f"[WakeSync] PortfolioPrice: 已触发后台同步，跟踪 {len(tracked_stocks)} 只股票")

            return {
                "success": True,
                "message": f"持仓价格同步已触发，后台异步执行",
                "details": {
                    "count": len(tracked_stocks),
                    "stocks": tracked_stocks[:10],
                    "async": True
                }
            }

        except Exception as e:
            log.error(f"[WakeSync] PortfolioPrice同步异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"持仓价格同步异常: {str(e)}",
                "details": {}
            }
