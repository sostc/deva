"""
AI 技术简报任务 v2.0
每天晚间自动抓取 AI/LLM + AI投资 领域的最新进展，生成结构化简报
同时提取因果知识，注入Naja系统
"""

import requests
import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# 消息推送函数
def send_imessage(phone: str, text: str):
    """发送iMessage"""
    try:
        import subprocess
        cmd = [
            'osascript', '-e',
            f'''tell application "Messages"
                send "{text.replace('"', '\\"')}" to buddy "{phone}"
            end tell'''
        ]
        subprocess.run(cmd, capture_output=True, timeout=10)
        return True
    except Exception as e:
        log.warning(f"iMessage发送失败: {e}")
        return False


def fetch_arxiv_papers(category: str = "cs.AI", max_results: int = 5) -> List[Dict]:
    """获取arXiv最新论文"""
    try:
        url = f"http://export.arxiv.org/api/query?search_query=cat:{category}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return []

        papers = []
        content = resp.text
        entries = content.split("<entry>")
        for entry in entries[1:max_results+1]:
            title_start = entry.find("<title>") + 7
            title_end = entry.find("</title>", title_start)
            title = entry[title_start:title_end].strip().replace("\n", " ")

            summary_start = entry.find("<summary>") + 9
            summary_end = entry.find("</summary>", summary_start)
            summary = entry[summary_start:summary_end].strip()[:200]

            if title and not title.startswith("["):
                papers.append({
                    "title": title,
                    "summary": summary + "..." if len(summary) >= 200 else summary,
                    "source": "arXiv"
                })
        return papers[:max_results]
    except Exception as e:
        log.warning(f"arXiv获取失败: {e}")
        return []


def fetch_huggingface_trending() -> List[Dict]:
    """获取HuggingFace热门模型"""
    try:
        url = "https://huggingface.co/api/models?sort=downloads&direction=-1&limit=5"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        models = []
        for item in resp.json()[:5]:
            models.append({
                "name": item.get("id", "unknown"),
                "downloads": item.get("downloads", 0),
                "likes": item.get("likes", 0),
                "source": "HuggingFace"
            })
        return models
    except Exception as e:
        log.warning(f"HuggingFace获取失败: {e}")
        return []


def fetch_github_trending(topic: str = "machine-learning") -> List[Dict]:
    """获取GitHub Trending"""
    try:
        url = f"https://api.github.com/search/repositories?q=topic:{topic}+pushed:>2024-01-01&sort=stars&order=desc&per_page=5"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        repos = []
        for item in resp.json().get("items", [])[:5]:
            repos.append({
                "name": item.get("full_name", "unknown"),
                "description": item.get("description", "")[:100],
                "stars": item.get("stargazers_count", 0),
                "source": "GitHub"
            })
        return repos
    except Exception as e:
        log.warning(f"GitHub获取失败: {e}")
        return []


def fetch_ai_news() -> List[Dict]:
    """获取AI新闻（从Hacker News）"""
    try:
        url = "https://hacker-news.firebaseio.com/v0/beststories.json"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []

        story_ids = resp.json()[:15]
        news = []
        for sid in story_ids:
            story_url = f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
            story_resp = requests.get(story_url, timeout=10)
            if story_resp.status_code == 200:
                story = story_resp.json()
                title = story.get("title", "")
                ai_keywords = ["AI", "LLM", "GPT", "Claude", "model", "neural", "deep learning", "machine learning", "openai", "anthropic"]
                if any(k.lower() in title.lower() for k in ai_keywords):
                    news.append({
                        "title": title,
                        "url": story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                        "score": story.get("score", 0),
                        "source": "HackerNews"
                    })
                    if len(news) >= 3:
                        break
        return news
    except Exception as e:
        log.warning(f"HN获取失败: {e}")
        return []


def fetch_twitter_ai_news() -> List[Dict]:
    """获取Twitter/X AI相关动态（通过Nitter RSS）"""
    # 使用 Nitter 实例获取 Twitter 热门 AI 账号的最新推文
    nitter_instances = [
        "nitter.privacydev.net",
        "nitter.poast.org",
        "nitter.net"
    ]

    ai_accounts = [
        "ylecun",        # Yann LeCun
        "sama",          # Sam Altman
        "ylecun",        # Meta AI
        "GoogleDeepMind",
        "AnthropicAI",
    ]

    tweets = []
    for instance in nitter_instances:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            # 获取多个AI大V的最近推文
            for account in ai_accounts[:2]:  # 限制数量避免太慢
                url = f"https://{instance}/{account}/rss"
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'xml')
                    items = soup.find_all('item')[:3]
                    for item in items:
                        title = item.title.text if item.title else ""
                        if title and len(title) > 10:
                            tweets.append({
                                "account": account,
                                "content": title[:100],
                                "source": "Twitter"
                            })
                    if len(tweets) >= 6:
                        return tweets[:6]
            break  # 成功就退出
        except Exception as e:
            continue

    return tweets[:6]


def fetch_ai_investment_news() -> List[Dict]:
    """获取AI投资相关新闻"""
    investment_news = []

    sources = [
        # TechCrunch AI 相关
        {
            "name": "TechCrunch",
            "url": "https://techcrunch.com/tag/artificial-intelligence/feed/",
            "keywords": ["AI", "OpenAI", "Anthropic", "Nvidia", "Google", "Microsoft", "Meta"]
        },
        # VentureBeat AI
        {
            "name": "VentureBeat",
            "url": "https://venturebeat.com/category/ai/feed/",
            "keywords": ["AI", "LLM", "GPT", "funding", "investment", "startup"]
        }
    ]

    for source in sources:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(source["url"], headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'xml')
                items = soup.find_all('item')[:5]

                for item in items:
                    title = item.title.text if item.title else ""
                    link = item.link.text if item.link else ""

                    # 检查是否匹配关键词
                    if any(k.lower() in title.lower() for k in source["keywords"]):
                        investment_news.append({
                            "title": title[:80],
                            "source": source["name"],
                            "url": link
                        })
                        if len(investment_news) >= 5:
                            return investment_news
        except Exception as e:
            log.warning(f"{source['name']} 获取失败: {e}")
            continue

    return investment_news[:5]


def fetch_wechat_ai_articles() -> List[Dict]:
    """获取微信公众号AI相关文章（通过RSS服务）"""
    rss_sources = [
        {
            "name": "机器之心",
            "url": "https://rsshub.app/wechat/mp/jiqizhixin",
            "keywords": ["AI", "模型", "大模型", "LLM", "GPT"]
        },
        {
            "name": "量子位",
            "url": "https://rsshub.app/wechat/mp/liangziwei",
            "keywords": ["AI", "大模型", "ChatGPT", "英伟达", "OpenAI"]
        }
    ]

    articles = []
    for source in rss_sources:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(source["url"], headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'xml')
                items = soup.find_all('item')[:3]

                for item in items:
                    title = item.title.text if item.title else ""
                    if any(k.lower() in title.lower() for k in source["keywords"]):
                        articles.append({
                            "title": title[:60],
                            "source": source["name"]
                        })
        except Exception as e:
            log.warning(f"{source['name']} RSS获取失败: {e}")
            continue

    return articles[:4]


def fetch_aibase_daily(max_retries: int = 3) -> Dict[str, Any]:
    """获取AIbase每日AI日报文章"""
    import re

    for attempt in range(max_retries):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            }

            resp = requests.get("https://news.aibase.com/zh/daily", headers=headers, timeout=15)
            if resp.status_code != 200:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                    continue
                return {"success": False, "error": f"HTTP {resp.status_code}"}

            html = resp.text

            article_links = re.findall(r'href="(/zh/daily/\d+)"', html)
            if not article_links:
                return {"success": False, "error": "未找到文章链接"}

            latest_link = f"https://news.aibase.com{article_links[0]}"
            article_id = re.search(r'/(\d+)$', article_links[0]).group(1)

            resp = requests.get(latest_link, headers=headers, timeout=15)
            if resp.status_code != 200:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                    continue
                return {"success": False, "error": f"文章获取失败 HTTP {resp.status_code}"}

            article_html = resp.text

            title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', article_html)
            title = title_match.group(1) if title_match else "未知标题"

            content_patterns = [
                r'<div[^>]*class="[^"]*prose[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*article[^"]*"[^>]*>(.*?)</div>',
                r'<article[^>]*>(.*?)</article>',
            ]
            content = ""
            for pattern in content_patterns:
                match = re.search(pattern, article_html, re.DOTALL)
                if match:
                    raw_content = match.group(1)
                    content = re.sub(r'<[^>]+>', ' ', raw_content)
                    content = re.sub(r'\s+', ' ', content).strip()
                    if len(content) > 100:
                        break

            if not content:
                text_matches = re.findall(r'提要[:：]\s*([^<]+)', article_html)
                if text_matches:
                    content = " | ".join(text_matches[:5])

            return {
                "success": True,
                "article_id": article_id,
                "title": title,
                "url": latest_link,
                "content": content[:2000] if content else "",
                "source": "AIbase"
            }

        except Exception as e:
            log.warning(f"AIbase获取失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
            else:
                return {"success": False, "error": str(e)}

    return {"success": False, "error": "重试次数耗尽"}


async def fetch_aibase_articles_list(
    days_back: int = 7,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> List[Dict[str, Any]]:
    """
    获取 AIbase 最近 N 天的日报文章列表

    Args:
        days_back: 回溯天数，默认7天
        headless:  是否无头模式
        timeout_ms: 超时时间

    Returns:
        文章列表，每项包含 article_id, title, url, publish_date
    """
    import asyncio as async_lib
    import re
    from playwright.async_api import async_playwright
    from datetime import datetime, timedelta

    articles = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
            )
            page = await context.new_page()

            log.info(f"正在获取 AIbase 日报列表 (最近{days_back}天)...")
            await page.goto(
                "https://news.aibase.com/zh/daily",
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            await async_lib.sleep(2)

            article_links = await page.query_selector_all('a[href*="/zh/daily/"]')
            log.info(f"找到 {len(article_links)} 个文章链接")

            cutoff_date = datetime.now().date() - timedelta(days=days_back)

            for link in article_links:
                try:
                    href = await link.get_attribute("href")
                    if not href or "/daily/" not in href:
                        continue

                    if not href.startswith("http"):
                        href = f"https://news.aibase.com{href}"

                    article_id = href.split("/")[-1]
                    title = await link.text_content()
                    title = title.strip() if title else ""

                    page2 = await context.new_page()
                    await page2.goto(href, wait_until="domcontentloaded", timeout=timeout_ms)
                    await page2.wait_for_load_state("networkidle", timeout=timeout_ms)
                    await async_lib.sleep(0.5)

                    page_text = await page2.content()
                    date_match = re.search(r'20\d{2}年(\d{1,2})月(\d{1,2})', page_text)
                    if date_match:
                        year = page_text[date_match.start():date_match.start()+4]
                        month = date_match.group(1).zfill(2)
                        day = date_match.group(2).zfill(2)
                        publish_date = f"{year}-{month}-{day}"
                        pub_date = datetime.strptime(publish_date, "%Y-%m-%d").date()

                        if pub_date >= cutoff_date:
                            articles.append({
                                "article_id": article_id,
                                "title": title,
                                "url": href,
                                "publish_date": publish_date,
                            })
                            log.info(f"  [{publish_date}] {title[:40]}...")

                    await page2.close()

                    if len(articles) >= days_back:
                        break

                except Exception as e:
                    log.warning(f"处理文章失败: {e}")
                    continue

            await browser.close()

    except Exception as e:
        log.warning(f"获取文章列表失败: {e}")

    return articles


async def fetch_aibase_daily_playwright(
    headless: bool = True,
    timeout_ms: int = 30000,
) -> Dict[str, Any]:
    """
    使用 Playwright 浏览器渲染获取 AIbase 每日文章

    Args:
        headless:    是否无头模式
        timeout_ms:  超时时间(ms)

    Returns:
        文章数据字典
    """
    import asyncio as async_lib
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
            )
            page = await context.new_page()

            log.info("正在打开 news.aibase.com/zh/daily ...")
            await page.goto(
                "https://news.aibase.com/zh/daily",
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )

            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            await async_lib.sleep(2)

            article_link = await page.query_selector('a[href*="/zh/daily/"]')
            if not article_link:
                log.warning("未找到文章链接")
                await browser.close()
                return {"success": False, "error": "未找到文章链接"}

            href = await article_link.get_attribute("href")
            if not href.startswith("http"):
                href = f"https://news.aibase.com{href}"

            article_id = href.split("/")[-1]
            log.info(f"找到最新文章: {href}")

            await page.goto(href, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            await async_lib.sleep(1)

            title_el = await page.query_selector("h1")
            title = await title_el.text_content() if title_el else "未知标题"

            page_text = await page.content()

            import re
            date_match = re.search(r'20\d{2}年(\d{1,2})月(\d{1,2})', page_text)
            if date_match:
                year = page_text[date_match.start():date_match.start()+4]
                month = date_match.group(1).zfill(2)
                day = date_match.group(2).zfill(2)
                publish_date = f"{year}-{month}-{day}"

            content_el = await page.query_selector("article, .prose, .article-content, [class*='content']")
            if content_el:
                content = await content_el.text_content()
                content = " ".join(content.split())[:2000]
            else:
                summary_points = await page.query_selector_all("[class*='summary'], [class*='highlight']")
                if summary_points:
                    content_parts = []
                    for sp in summary_points[:5]:
                        text = await sp.text_content()
                        if text:
                            content_parts.append(text.strip())
                    content = " | ".join(content_parts)
                else:
                    content = ""

            await browser.close()

            return {
                "success": True,
                "article_id": article_id,
                "title": title.strip(),
                "url": href,
                "content": content[:2000] if content else "",
                "source": "AIbase",
                "publish_date": publish_date
            }

    except Exception as e:
        log.warning(f"Playwright 抓取失败: {e}")
        return {"success": False, "error": str(e)}


def format_report_v2(
    papers: List[Dict],
    models: List[Dict],
    repos: List[Dict],
    news: List[Dict],
    tweets: List[Dict],
    invest_news: List[Dict],
    wechat: List[Dict]
) -> str:
    """格式化简报 v2"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    report = f"""🤖 AI 晚报 {today} {time_str}
━━━━━━━━━━━━━━━━━━━━━━

📚 论文精选 (arXiv cs.AI)
"""
    if papers:
        for i, p in enumerate(papers[:3], 1):
            report += f"  {i}. {p['title'][:70]}...\n"
    else:
        report += "  暂无新论文\n"

    report += """
🌟 热门模型 (HuggingFace)
"""
    if models:
        for i, m in enumerate(models[:3], 1):
            downloads = f"{m['downloads']:,}" if m['downloads'] else "N/A"
            report += f"  {i}. {m['name']} (↓{downloads})\n"
    else:
        report += "  暂无热门模型\n"

    report += """
⭐ 开源项目 (GitHub ML Trending)
"""
    if repos:
        for i, r in enumerate(repos[:3], 1):
            stars = f"{r['stars']:,}" if r['stars'] else "N/A"
            report += f"  {i}. {r['name']} ⭐{stars}\n"
    else:
        report += "  暂无热门项目\n"

    report += """
📰 AI热点 (Hacker News)
"""
    if news:
        for i, n in enumerate(news[:3], 1):
            report += f"  {i}. {n['title'][:55]} (↑{n['score']})\n"
    else:
        report += "  暂无热点\n"

    if tweets:
        report += """
🐦 AI大V动态 (Twitter/X)
"""
        for i, t in enumerate(tweets[:4], 1):
            report += f"  {i}. @{t['account']}: {t['content'][:50]}...\n"

    if invest_news:
        report += """
💰 AI投资要闻
"""
        for i, n in enumerate(invest_news[:4], 1):
            report += f"  {i}. [{n['source']}] {n['title']}\n"

    if wechat:
        report += """
📱 公众号精选
"""
        for i, w in enumerate(wechat[:3], 1):
            report += f"  {i}. [{w['source']}] {w['title']}\n"

    report += """
━━━━━━━━━━━━━━━━━━━━━━
🕐 Naja AI情报员 v2.0 自动生成"""

    return report


AIBASE_LEARNED_FILE = os.path.expanduser("~/.naja/aibase_learned.json")


def get_learned_dates() -> set:
    """获取已学习的日期"""
    try:
        with open(AIBASE_LEARNED_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get("learned_dates", []))
    except:
        return set()


def mark_date_learned(date_str: str):
    """标记日期已学习"""
    try:
        data = {"learned_dates": []}
        try:
            with open(AIBASE_LEARNED_FILE, 'r') as f:
                data = json.load(f)
        except:
            pass

        learned_dates = data.get("learned_dates", [])
        if date_str not in learned_dates:
            learned_dates.append(date_str)
        learned_dates = learned_dates[-30:]

        os.makedirs(os.path.dirname(AIBASE_LEARNED_FILE), exist_ok=True)
        with open(AIBASE_LEARNED_FILE, 'w') as f:
            json.dump({"learned_dates": learned_dates}, f)
    except Exception as e:
        log.warning(f"标记日期失败: {e}")


def execute() -> dict:
    """
    主执行函数 - 晚间定时运行 v2.0
    """
    import asyncio

    log.info("[AI_Report_v2] 开始生成AI晚报...")

    try:
        papers = fetch_arxiv_papers("cs.AI", max_results=5)
        models = fetch_huggingface_trending()
        repos = fetch_github_trending("machine-learning")
        news = fetch_ai_news()
        tweets = fetch_twitter_ai_news()
        invest_news = fetch_ai_investment_news()
        wechat = fetch_wechat_ai_articles()

        aibase_learned = False
        aibase_title = ""
        aibase_articles_learned = []

        today_str = datetime.now().strftime("%Y-%m-%d")
        learned_dates = get_learned_dates()
        log.info(f"[AI_Report_v2] 已学习日期: {learned_dates}")

        if today_str in learned_dates:
            log.info(f"[AI_Report_v2] 今日({today_str})已学习过，跳过")
        else:
            try:
                articles = asyncio.run(fetch_aibase_articles_list(days_back=7))
                if not articles:
                    aibase_result = asyncio.run(fetch_aibase_daily_playwright())
                    if aibase_result.get("success"):
                        publish_date = aibase_result.get("publish_date", "")
                        if publish_date == today_str:
                            articles = [aibase_result]
                        else:
                            log.info(f"[AI_Report_v2] 文章日期({publish_date})不是今天({today_str})，跳过")

                if articles:
                    for article in articles:
                        pub_date = article.get("publish_date", "")
                        if pub_date in learned_dates:
                            continue

                        log.info(f"[AI_Report_v2] 学习 {pub_date} 日报: {article.get('title', '')[:40]}...")
                        try:
                            from deva.naja.tasks.article_learner import learn_article_url
                            learn_result = learn_article_url(article["url"])
                            log.info(f"[AI_Report_v2] 深度学习完成，置信度: {learn_result.confidence:.2f}")
                            learned_dates.add(pub_date)
                            mark_date_learned(pub_date)
                            aibase_articles_learned.append({
                                "date": pub_date,
                                "title": article.get("title", "")[:50],
                            })
                            if pub_date == today_str:
                                aibase_title = article.get("title", "")
                        except Exception as e:
                            log.warning(f"[AI_Report_v2] 深度学习失败: {e}")
                else:
                    log.warning(f"[AI_Report_v2] 未获取到文章")

            except Exception as e:
                log.warning(f"[AI_Report_v2] AIbase处理失败: {e}")

        report = format_report_v2(
            papers, models, repos, news,
            tweets, invest_news, wechat
        )

        if aibase_title:
            report += f"\n\n📖 AIbase日报已深度学习:\n  • {aibase_title[:60]}...\n  ✅ 知识已进入Naja验证期"

        if aibase_articles_learned:
            if len(aibase_articles_learned) > 1:
                report += f"\n\n📚 补学习最近 {len(aibase_articles_learned)} 天日报:"
                for item in aibase_articles_learned:
                    report += f"\n  • [{item['date']}] {item['title'][:50]}..."

        log.info(f"[AI_Report_v2] 简报已生成，长度: {len(report)}")

        today = datetime.now().strftime("%Y%m%d_%H%M")
        report_path = os.path.expanduser(f"~/.naja/ai_reports/{today}_v2.txt")
        try:
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)
            log.info(f"[AI_Report_v2] 简报已保存: {report_path}")
        except Exception as e:
            log.warning(f"[AI_Report_v2] 保存失败: {e}")

        phone = "+8618626880688"
        sent = send_imessage(phone, report)
        if sent:
            log.info("[AI_Report_v2] 简报已推送到手机")
        else:
            log.warning("[AI_Report_v2] 推送失败")

        knowledge_count = 0
        validating_count = 0
        try:
            from deva.naja.tasks.ai_knowledge_injector import AIKnowledgeInjector, send_notification
            injector = AIKnowledgeInjector()

            all_news = news + invest_news
            evaluation_result = injector.extract_and_evaluate_knowledge(all_news)

            counts = injector.inject_knowledge(evaluation_result)
            knowledge_count = counts.get("new", 0)
            validating_count = counts.get("validating", 0)

            knowledge_status = injector.get_knowledge_for_trading()
            insight_text = f"""
🧠 Naja知识库状态:
  📝 观察期: {knowledge_status['observing_count']}条（不参与决策）
  ⏳ 验证中: {knowledge_status['validating_count']}条（低权重参考）
  ✅ 正式上岗: {knowledge_status['qualified_count']}条（可参与决策）
"""
            report += insight_text

            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)

            log.info(f"[AI_Report_v2] 知识统计: 新增{knowledge_count}, 验证中{validating_count}")

            notification = injector.generate_notification_text(evaluation_result)
            if notification:
                send_notification(notification)
                log.info("[AI_Report_v2] 已发送知识更新通知")
            else:
                log.info("[AI_Report_v2] 今日无重大更新，仅记录观察")

        except Exception as e:
            log.warning(f"[AI_Report_v2] 知识注入失败: {e}")

        return {
            "success": True,
            "report_length": len(report),
            "papers_count": len(papers),
            "models_count": len(models),
            "repos_count": len(repos),
            "news_count": len(news),
            "tweets_count": len(tweets),
            "invest_count": len(invest_news),
            "wechat_count": len(wechat),
            "knowledge_injected": knowledge_count,
            "pushed": sent,
            "aibase_learned": aibase_learned,
            "aibase_title": aibase_title,
            "aibase_articles_learned": aibase_articles_learned
        }

    except Exception as e:
        log.error(f"[AI_Report_v2] 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # 测试运行
    result = execute()
    print(json.dumps(result, ensure_ascii=False, indent=2))
