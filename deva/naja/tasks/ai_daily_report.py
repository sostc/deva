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
    # 使用一些公开的微信公众号聚合服务
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


def execute() -> dict:
    """
    主执行函数 - 晚间定时运行 v2.0
    """
    log.info("[AI_Report_v2] 开始生成AI晚报...")

    try:
        # 1. 抓取各来源数据
        papers = fetch_arxiv_papers("cs.AI", max_results=5)
        models = fetch_huggingface_trending()
        repos = fetch_github_trending("machine-learning")
        news = fetch_ai_news()
        tweets = fetch_twitter_ai_news()
        invest_news = fetch_ai_investment_news()
        wechat = fetch_wechat_ai_articles()

        # 2. 生成简报
        report = format_report_v2(
            papers, models, repos, news,
            tweets, invest_news, wechat
        )
        log.info(f"[AI_Report_v2] 简报已生成，长度: {len(report)}")

        # 3. 保存到文件
        today = datetime.now().strftime("%Y%m%d_%H%M")
        report_path = os.path.expanduser(f"~/.naja/ai_reports/{today}_v2.txt")
        try:
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)
            log.info(f"[AI_Report_v2] 简报已保存: {report_path}")
        except Exception as e:
            log.warning(f"[AI_Report_v2] 保存失败: {e}")

        # 4. 推送到手机
        phone = "+8618626880688"
        sent = send_imessage(phone, report)
        if sent:
            log.info("[AI_Report_v2] 简报已推送到手机")
        else:
            log.warning("[AI_Report_v2] 推送失败")

        # 5. 提取因果知识并注入Naja（深思熟虑版）
        knowledge_count = 0
        validating_count = 0
        try:
            from deva.naja.tasks.ai_knowledge_injector import AIKnowledgeInjector, send_notification
            injector = AIKnowledgeInjector()

            # 合并所有新闻用于知识提取
            all_news = news + invest_news
            evaluation_result = injector.extract_and_evaluate_knowledge(all_news)

            # 注入评估后的知识
            counts = injector.inject_knowledge(evaluation_result)
            knowledge_count = counts.get("new", 0)
            validating_count = counts.get("validating", 0)

            # 生成洞察并追加到报告
            knowledge_status = injector.get_knowledge_for_trading()
            insight_text = f"""
🧠 Naja知识库状态:
  📝 观察期: {knowledge_status['observing_count']}条（不参与决策）
  ⏳ 验证中: {knowledge_status['validating_count']}条（低权重参考）
  ✅ 正式上岗: {knowledge_status['qualified_count']}条（可参与决策）
"""
            report += insight_text

            # 更新保存的报告
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)

            log.info(f"[AI_Report_v2] 知识统计: 新增{knowledge_count}, 验证中{validating_count}")

            # 如果有重大更新，发送通知给爸爸
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
            "pushed": sent
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
