import asyncio
from miku_ai import get_wexin_article

async def search_author_articles():
    # 搜索决战2050公众号的文章
    articles = await get_wexin_article('决战2050', 10)
    print("决战2050公众号文章列表：")
    print("=" * 80)
    for i, article in enumerate(articles, 1):
        print(f"{i}. {article['title']}")
        print(f"   URL: {article['url']}")
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(search_author_articles())
