from tornado import gen
from deva import Stream, httpx, sync,Deva,print,log
from collections import defaultdict

"""
这是一个浏览器模块，提供了浏览器流对象和相关的功能。
浏览器流对象内置了缓存功能，可以保存请求的响应内容，避免重复请求。
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


class Browser(Stream):
    """浏览器流对象，内置缓存功能。

    缓存是一个字典对象，key 是 url，value 是 response 对象。
    """

    def __init__(self, cache_size=30, **kwargs):
        super().__init__(ensure_io_loop=True,**kwargs)
        self.cache = defaultdict(lambda: None)
        self.cache_size = cache_size
        self.tabs = set()  # 使用 set 保存 tab 对象

    def tab(self, url, refresh_interval=0):  # 默认不自动刷新
        """创建一个 tab 对象，用于处理 URL 请求，并提供定时刷新功能。
        相同的 url 使用相同的 tab 对象来执行任务。

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
    
    def _add_to_cache(self, url, response):
        """将响应添加到缓存中。

        参数:
            url: 请求的 URL
            response: 响应对象
        """
        if len(self.cache) >= self.cache_size:
            # 移除最早的缓存项
            self.cache.pop(next(iter(self.cache)))
        self.cache[url] = response

class Tab:
    """Tab 对象，用于处理单个 URL 请求，并提供定期刷新功能，每次请求完成后安排下一个定期刷新任务。"""

    def __init__(self, browser, url, refresh_interval=7200):  # 默认刷新间隔为 2 小时
        self.browser = browser
        self.url = url
        self.refresh_interval = refresh_interval  # 定期刷新时间，单位为秒
        if self.url not in self.browser.cache:
            self._schedule_request()
        self._schedule_refresh()

    def _callback(self,x):
        self.browser._add_to_cache(self.url, x.result())
        f'后台完成异步请求{self.url}'>>log
        #任务完成后，安排下一次 tab 的自动刷新
        self._schedule_refresh()

    def _schedule_request(self):
        """安排异步请求，用于获取 URL 的响应内容。"""
        f'后台发起异步请求{self.url}'>>log
        futs = gen.convert_yielded(httpx(self.url))
        self.browser.loop.add_future(futs,self._callback)
        

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
        f'为{self.url}安排定期刷新'>>log

    @property
    def page(self):
        """获取 URL 的响应内容。

        如果缓存中存在，则直接返回缓存内容。
        如果缓存中不存在，则进行同步请求并缓存结果。

        返回:
            response: 响应对象
        """
        if self.url in self.browser.cache:
            '浏览器里有已经打开的 tab，立即返回内容'>>log
            return self.browser.cache[self.url]
        else:
            '浏览器里没有成功完全打开状态的 tab，立即同步网络请求'>>log
            response = sync(self.browser.loop, lambda :httpx(self.url))
            self.browser._add_to_cache(self.url, response)
            '请求完成，返回内容'>>log
            return response

    def refresh(self):
        """手动刷新 URL 的响应内容。

        忽略缓存内容，重新发起异步请求，并且保存数据到缓存。

        返回:
            response: 响应对象
        """
        self._schedule_request()

        return self
    
    def __str__(self):
        return self.url  # 返回 URL

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
        del self
        '已删除 tab 对象'>>log

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