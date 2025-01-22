from tornado import gen
from deva import Stream, httpx, sync,Deva,print,log
from collections import defaultdict
from newspaper import Article
from tornado.ioloop import IOLoop
from concurrent.futures import ThreadPoolExecutor
from requests_html import HTMLResponse
import asyncio

"""
这是一个浏览器模块，提供了浏览器流对象和相关的功能。
浏览器的 tab 方法，tab 里的异步网络请求，
tab 调用浏览器的函数处理 response 生成  page，
tab 将page 发送给浏览器的 page_stream
用户基于 page_stream做个性化处理，
page_stream默认会将 page 缓存在浏览器里，
tab 在请求网络前，先判断缓存，缓存存在就获取缓存，缓存不存在时才去发起请求。
打开新tab是 异步发起网络请求的。可以同时打开多个 tab发起多个请求，不会阻塞程序的执行。
访问tab.page时，会立即同步返回内容，如果缓存里有直接返回缓存，如果缓存没有，立即同步执行网络请求。


浏览器模块的工作原理:

1. 请求机制
- Tab 对象支持两种请求模式:
  - 同步模式: 通过 page 属性直接获取缓存响应,或者发起同步网络请求，会阻塞等待网络请求完成
  - 异步模式: 默认创建对象是，会异步请求网络，保存数据到缓存，另外通过 refresh() 方法发起异步请求,也不会阻塞主线程

2. 缓存机制
- Browser 对象维护一个 LRU 缓存,用于存储请求响应
- 缓存大小可配置,默认为 5000 条
- 当缓存满时会移除最早的缓存项
- Tab 请求时优先从缓存获取,无缓存时才发起网络请求

3. 自动刷新机制
- Tab 支持定期自动刷新,默认不会自动刷新
- 可通过 refresh_interval 参数配置刷新间隔
- 每次请求完成后会自动安排下一次刷新
- 设置 refresh_interval=0 时禁用自动刷新

4. Tab 管理
- Browser 维护所有打开的 Tab 列表
- 支持通过 URL 创建和关闭 Tab
- 关闭 Tab 时会:
  - 停止自动刷新
  - 从 Tab 列表移除
  - 清除相关缓存
  - 释放内存资源

5. 全局实例
- 模块提供全局 Browser 实例
- 可通过 browser.tab 或者 tab快速创建新标签页
- tabs 属性可获取所有打开的标签页列表

**用例**

0. 使用全局快捷方式
    ```python
    from deva.browser import tab, browser, tabs
    from deva import *
    
    # 使用全局 tab 方法创建标签页并搜索内容
    tab('http://secsay.com').page.html.search('<title>{}</title>')
    
    # 查看当前打开的所有标签页
    print(tabs)
    
    # 使用全局 browser 实例创建标签页
    browser.tab('http://example.com')
    ```

1. 创建浏览器实例
    ```
    browser = Browser(cache_size=5)
    ```
    这里创建了一个浏览器实例，设置了缓存大小为 5。

2. 创建一个新的 tab 并请求 URL
    ```
    tab1 = browser.tab("http://secsay.com")
    res = tab1.page
    res.content>>print
    ```
    这里创建了一个新的 tab，并请求了 URL "http://secsay.com"。然后，打印了响应的内容。

3. 刷新 tab
    ```
    response2 = tab1.refresh()
    print("Refreshed response:", response2)
    ```
    这里刷新了 tab1，并打印了刷新后的响应内容。

4. 打开另一个 tab
    ```
    tab2 = browser.tab("http://baidu.com")
    response2 = tab2.page
    print("Response from http://baidu.com:", response2)
    ```
    这里打开了另一个 tab，并请求了 URL "http://baidu.com"。然后，打印了响应的内容。

5. 关闭 tab
    ```
    tab('http://secsay.com').close()
    ```
    这里关闭了 URL 为 "http://secsay.com" 的 tab。

6. 运行 Deva
    ```
    Deva.run()
    ```
    这里启动了 Deva 的事件循环，开始处理所有的异步任务。

**日志示例**

在运行上述代码时，可能会在日志中看到以下信息：
    ```
    2025-01-04 22:44:34.131748 : 后台发起异步请求http://secsay.com
    2025-01-04 22:44:34.134947 : 为http://secsay.com安排定期刷新
    2025-01-04 22:44:36.504692 : 后台完成异步请求http://secsay.com
    2025-01-04 22:44:36.504819 : 为http://secsay.com安排定期刷新
    ```
    这些日志信息显示了浏览器模块在后台处理请求和刷新任务的过程。
"""

class DotDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)
    
    def __setattr__(self, key, value):
        self[key] = value

class Browser(Stream):
    """浏览器流对象，内置缓存功能。

    缓存是一个字典对象，key 是 url，value 是 response 对象。
    """

    def __init__(self, cache_size=30, **kwargs):
        """
        初始化浏览器对象，用于管理多个tab的浏览和缓存。

        例子：browser.tab("http://baidu.com").page>>print

        参数:
            cache_size: 缓存大小，即最多保存的响应对象数量，默认为30。
            **kwargs: 其他参数，传递给父类的初始化方法。
        """
        super().__init__(ensure_io_loop=True,**kwargs)
        self.log = Stream()
        self.cache = defaultdict(lambda: None)
        self.cache_size = cache_size
        self.page_stream = Stream() # 使用page_stream流来挂载其他处理插件
        self.tabs = set()  # 使用 set 保存 tab 对象

        self.page_stream.sink(self._add_to_cache)

    def tab(self, url, refresh_interval=0):  # 默认不自动刷新
        """创建一个 tab 对象，用于处理 URL 请求，并提供定时刷新功能。
        每个 tab 获得网络 response 后，先解析成 page
        然后将 page 发送到浏览器的 page_stream,方便后续用户在 page_stream上处理 page


        参数:
            url: 要请求的 URL
            refresh_interval: 定时刷新时间，单位为秒，默认为0，不执行定时刷新任务

        返回:
            Tab 对象
        """
        # 检查是否已存在相同的 tab
        for existing_tab in self.tabs:
            if str(existing_tab) == url:
                existing_tab.refresh_interval = refresh_interval  # 更新已存在的 tab 的刷新间隔
                return existing_tab  # 返回已存在的 tab
        new_tab = Tab(self, url, refresh_interval)
        self.tabs.add(new_tab)  # 添加新 tab 到 set
        
        return new_tab

    def emit(self, x, asynchronous=False):
        return self.tab(x)
    
    def _add_to_cache(self, page):
        """将响应添加到缓存中。"""
        try:
            if len(self.cache) >= self.cache_size:
                # 安全移除最早的缓存项
                if self.cache:
                    oldest_key = next(iter(self.cache), None)
                    if oldest_key:
                        self.cache.pop(oldest_key)
            
            if page and page.url:
                self.cache[page.url] = page
        except Exception as e:
            f'缓存写入失败: {str(e)}' >> self.browser.log

    def __repr__(self):
        return f"Browser(cache_size={self.cache_size}, tabs={len(self.tabs)})"

    def extract_text_from_html(self, html_content):
        """使用 boilerpy3 从 HTML 内容中提取新闻正文。

        参数:
            html_content: HTML 内容字符串

        返回:
            str: 提取的新闻正文文本
        """
        from boilerpy3 import extractors
        extractor = extractors.ArticleExtractor()
        try:
            text = extractor.get_content(html_content)
            return text
        except Exception as e:
            print(f"提取文本时出错: {str(e)}")
            return ""
        
    def create_article(self,response):
        if not response or not hasattr(response, 'html') or not response.html:
            return None
        # 根据响应头判断网页语言
        # 从HTML内容中提取语言信息
        
        try:
            from bs4 import BeautifulSoup
            html_content = response.html.html if response.html.html else ''
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 添加默认值
            lang = 'zh'
            try:
                html_tag = soup.find('html')
                if html_tag and html_tag.get('lang'):
                    lang = html_tag['lang']
                else:
                    meta_lang = soup.find('meta', attrs={'http-equiv': 'Content-Language'})
                    if meta_lang:
                        lang = meta_lang.get('content', 'zh')
                
                if 'zh' in lang:
                    lang = 'zh'
                else:
                    lang = 'en'
            except:
                pass
            article = Article(response.url, language=lang)
            article.set_html(html_content)
            article.config.MAX_SUMMARY_SENT = 3  # 限制摘要句子数量
            article.parse()
            if not article.text:
                article.text = self.extract_text_from_html(response.html.html)

        except Exception as e:
            f'文章解析失败: {str(e)}' >> self.log
            return None
            # 使用文章正文生成摘要
        from bs4 import BeautifulSoup

# 清理 HTML 标签
        article.text = BeautifulSoup(article.text, "html.parser").get_text()

# 确保内容足够长
        if len(article.text) < 50:  # 设置最小长度限制
            print("文章内容太短，无法生成摘要")
            article.summary = ""

        # article.nlp()  # 生成摘要质量较差
        # 使用sumy生成摘要
        try:
            from sumy.parsers.plaintext import PlaintextParser
            from sumy.nlp.tokenizers import Tokenizer
            from sumy.summarizers.lsa import LsaSummarizer
            from sumy.nlp.stemmers import Stemmer
            from sumy.utils import get_stop_words

            

# 将清理后的文本传入 summarizer
            # 根据网页语言选择合适的语言参数
            language = 'chinese' if lang == 'zh' else 'english'
            parser = PlaintextParser.from_string(article.text, Tokenizer(language))
            stemmer = Stemmer(language)
            summarizer = LsaSummarizer(stemmer)
            summarizer.stop_words = get_stop_words(language)
            
            # 生成3句话的摘要
            summary = []
            for sentence in summarizer(parser.document, 3):
                summary.append(str(sentence))
            article.summary = '\n'.join(summary)
            return article
        except Exception as e:
            print(f"生成摘要时出错: {str(e)}")
            article.summary = ""
        return article

class Tab():
    """Tab 对象，用于处理单个 URL 请求，并提供定期刷新功能，每次请求完成后安排下一个定期刷新任务。"""

    def __init__(self, browser, url, refresh_interval=7200):  # 默认刷新间隔为 2 小时
        self.browser = browser
        self.url = url
        self._page = None
        self.refresh_interval = refresh_interval  # 定期刷新时间，单位为秒
        self._async_request_future = None  # 用于跟踪异步请求的 Future 对象

        if self.url not in self.browser.cache:
            self._schedule_request()
        self._schedule_refresh()

    def _callback(self, x):
        response = x.result()
        print(response)
        f'后台完成异步请求{self.url}' >> self.browser.log
        self.parse(response)
        self._schedule_refresh()

    def _schedule_request(self, retry_count=3):
        """安排异步请求，用于获取 URL 的响应内容。"""
        try:
            f'后台发起异步请求{self.url}' >> self.browser.log

            self._async_request_future = gen.convert_yielded(httpx(self.url, timeout=30))  # 添加超时
            self.browser.loop.add_future(self._async_request_future, self._callback)
        except Exception as e:
            if retry_count > 0:
                f'请求失败，重试中...剩余重试次数: {retry_count}' >> self.browser.log
                self._schedule_request(retry_count - 1)
            else:
                f'请求失败: {str(e)}' >> self.browser.log
                self._page = None

    def _schedule_refresh(self):
        """安排定期刷新，用于定期更新 URL 的响应内容。"""
        # 如果刷新间隔值为 None 、False或者 0，则永远不执行定时刷新任务
        if not self.refresh_interval:
            return
        # 如果已经存在刷新定时器，先移除
        if hasattr(self, '_refresh_timer'):
            self.browser.loop.remove_timeout(self._refresh_timer)
        # 创建新的刷新定时器
        self._refresh_timer = self.browser.loop.call_later(self.refresh_interval, self._schedule_request)
        f'为{self.url}安排定期刷新'>>self.browser.log

    @property
    def sync_page(self):
        """获取 URL 的响应内容。

        如果缓存中存在，则直接返回缓存内容。
        如果缓存中不存在，则进行同步请求并缓存结果。

        返回:
            response: 响应对象
        """
        if self._page != None:
            '浏览器里有已经打开的 tab，立即返回内容' >> self.browser.log
            return self._page  
        else:
            '浏览器里没有成功完全打开状态的 tab，立即同步网络请求' >> self.browser.log
            self.url>>self.browser.log
            response = sync(self.browser.loop, lambda: httpx(self.url))
            '同步请求完成，返回内容' >> self.browser.log
            return self.parse(response)
            
    @property
    async def page(self):
        """获取 URL 的响应内容。

        如果缓存中存在，则直接返回缓存内容。
        如果缓存中不存在，则进行同步请求并缓存结果。

        返回:
            response: 响应对象
        """
        if self._page != None:
            '浏览器里有已经打开的 tab，立即返回内容' >> self.browser.log
            return self._page  
        else:
            '浏览器里没有成功完全打开状态的 tab，立即异步网络请求' >> self.browser.log
            self.url>>self.browser.log
            try:
            # 确保在异步上下文中执行
                response = await httpx(self.url)
                '异步请求完成，返回内容' >> self.browser.log
                
                
                # 将parse操作放入线程池执行
                try:
                    loop = asyncio.get_event_loop()
                    parsed_response = self.parse(response)
                    
                
                    return parsed_response
                except asyncio.TimeoutError:
                    f'页面解析超时: {self.url}' >> self.browser.log
                    return None
                except Exception as e:
                    f'页面解析失败: {str(e)}' >> self.browser.log
                    return None
                
            except Exception as e:
                f'网络请求失败: {str(e)}' >> self.browser.log
                return None
        
    @property
    async def article(self):
        """获取 URL 的文章内容。

        如果缓存中存在，则直接返回缓存的文章对象。
        如果缓存中不存在，则先获取页面内容并解析文章。

        返回:
            article: Article对象
        """
        page = await self.page
        return page.article

    def refresh(self):
        """手动刷新 URL 的响应内容。

        忽略缓存内容，重新发起异步请求，并且保存数据到缓存。

        返回:
            response: 响应对象
        """
        self._schedule_request()
        return self
    
    def parse(self, response):
        """
        处理网络返回的数据，生成 article 对象并存储到缓存中。

        这个方法将接收到的响应对象转换为 article 对象，并将其存储到浏览器的缓存中，以便后续使用。

        参数:
            response (object): 响应对象，包含了从网络请求中获取的数据。

        返回:
            self._page (object): 包含了文章对象的页面对象，用于存储和访问文章数据。
        """
        
        # 检查响应对象是否为正常的response类型
        if not isinstance(response, HTMLResponse):
            '非正常的响应对象' >> self.browser.log
            return None
        
        # 将响应对象存储到当前页面对象中
        self._page = response
        # 使用浏览器的方法创建文章对象
        self._page._article = self.browser.create_article(response)
        # 定义文章对象的属性列表
        if self._page._article:

            article_attributes = ['keywords', 'meta_keywords',
                               'tags', 'authors', 'publish_date', 
                               'summary', 'text', 'images', 'meta_data', 
                               'meta_description', 'title']
            # 使用DotDict将文章对象的属性转换为字典形式
            self._page.article = DotDict({
                attr: getattr(self._page._article, attr) 
                for attr in article_attributes})
        else:
            self._page.article = None
        # 将解析好的页面发到浏览器页面流中
        self.browser.page_stream.emit(self._page)
        # 返回当前页面对象
        return self._page
    
    def __str__(self):
        return self.url  # 返回 URL

    def __repr__(self):
        """返回 Tab 对象的有意义的表示形式，包含 URL 和摘要。"""
        # return f"Tab(url={self.url}, summary={self.page.article.title})"
        return f"Tab(url={self.url})"

    def close(self):
        """关闭 tab 对象，停止前面设定的定期刷新，并从浏览器的全局 tabs 中移除该对象，并释放内存。同时从缓存中删除数据。"""
        # 如果存在刷新定时器，则移除
        if hasattr(self, '_refresh_timer'):
            self.browser.loop.remove_timeout(self._refresh_timer)
        # 从浏览器的标签页列表中移除当前标签页
        self.browser.tabs.remove(self)
        # 从缓存中删除数据
        if self.url in self.browser.cache:
            del self.browser.cache[self.url]
        '已删除 tab 对象' >> self.browser.log
        del self
# 全局浏览器实例,缓存大小为5000
_global_browser = Browser(cache_size=5000)

# 全局快捷方式,方便直接使用
browser = _global_browser  # 浏览器实例
tab = _global_browser.tab  # 直接创建新标签页的全局方法
tabs = _global_browser.tabs  # 所有标签页列表

def open_tabs_in_browser():
    """在默认浏览器中打开所有缓存的标签页内容"""
    import tempfile
    import webbrowser
    import os
    
    # 为每个缓存的响应创建临时HTML文件
    for url, response in _global_browser.cache.items():
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html') as f:
            f.write(response.text)
            webbrowser.open('file://' + f.name)
            '在浏览器中打开缓存页面:' + url>>log

# ... existing code ...

if __name__ == "__main__":
    from deva.browser import tab,browser,tabs
    from deva import *

    tab('http://secsay.com').page.html.search('<title>{}</title>')
    browser.page_stream.filter(lambda page:page.url=='http://baidu.com').map(lambda p:p.article>>log)
    tab('http://baidu.com')
    
    # 创建浏览器实例
    browser = Browser(cache_size=5)

    # 创建一个新的 tab 并请求 URL
    tab1 = browser.tab("http://secsay.com")
    res = tab1.page

    # 刷新 URL 的响应内容
    response2 = tab1.refresh()
    print("Refreshed response:", response2)

    # 请求另一个 URL
    tab2 = browser.tab("http://baidu.com")
    response3 = tab2.page
    print("Response from http://baidu.com:", response3)

    tab1 = tab('http://secsay.com')
    # 2025-01-04 22:44:34.131748 : 后台发起异步请求http://secsay.com
    # 2025-01-04 22:44:34.134947 : 为http://secsay.com安排定期刷新
    # 2025-01-04 22:44:36.504692 : 后台完成异步请求http://secsay.com
    # 2025-01-04 22:44:36.504819 : 为http://secsay.com安排定期刷新

    # 使用OpenAI API分析网页结构并提取XPath
    from deva import openai
    api_key = '919a795d-207b-4ccf-8fd4-83ee5a23e961'
    API_URL = "https://api.sambanova.ai/v1/"
    model = "Meta-Llama-3.1-8B-Instruct"
    
    # 获取网页内容
    html_content = tab1.page.text
    
    # 构建提示语
    prompt = f"""分析以下HTML内容，找出正文和标题的XPath路径:

{html_content}

请返回JSON格式:
{{
    "title_xpath": "标题的xpath路径",
    "content_xpath": "正文的xpath路径"
}}
"""

    # 调用OpenAI API获取分析结果
    result = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    ).choices[0].message.content

    # 解析返回的JSON
    import json
    xpath_info = json.loads(result)
    
    # 使用XPath提取内容
    title = tab1.page.html.xpath(xpath_info['title_xpath']).first.text
    content = tab1.page.html.xpath(xpath_info['content_xpath']).first.text

    f'标题: {title}'>>print
    f'正文: {content}'>>print

    tab('http://secsay.com').close()

    Deva.run()
# ... existing code ...