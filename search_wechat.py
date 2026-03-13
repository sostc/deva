import asyncio
from miku_ai import get_wexin_article

async def search_wechat_articles():
    articles = await get_wexin_article('决战 2050', 5)
    for article in articles:
        print(f"{article['title']} | {article['url']}")

if __name__ == "__main__":
    asyncio.run(search_wechat_articles())
