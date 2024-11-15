import os
import time

from .pipe import passed, ls, P
from .core import Stream
from .utils.simhash import Simhash, SimhashIndex

from whoosh.fields import Schema, TEXT, ID
import whoosh.index
from whoosh.writing import AsyncWriter
from whoosh.qparser import MultifieldParser

from jieba.analyse import ChineseAnalyzer
import jieba
import jieba.analyse


@Stream.register_api()
class IndexStream(Stream):
    """基于 Whoosh 和结巴分词的中文全文搜索流处理类
    
    功能特性:
    1. 中文分词: 使用结巴分词进行中文文本分析
    2. 全文索引: 基于 Whoosh 引擎实现全文搜索
    3. 异步写入: 支持异步索引更新
    4. 相似度匹配: 使用 SimHash 算法进行文本相似度计算
    5. 关键词提取: 支持文本关键词和特征提取
    
    主要用法:
    1. 创建索引:
        index = IndexStream('./data/search_index')  # 指定索引存储路径
        
    2. 添加文档:
        # 单文档索引（自动使用时间戳作为ID）
        "这是一段要索引的中文文本" >> index
        
        # 指定ID的文档索引
        ("doc1", "这是带ID的文档") >> index
        
        # 批量索引
        {"doc2": "文档内容2", "doc3": "文档内容3"} >> index
        
    3. 搜索文档:
        # 基础搜索
        results = index.search("搜索关键词", limit=10)
        
    4. 智能问答:
        # 基于相似度的智能匹配
        answer = index.ask("你的问题")
        
    5. 关键词提取:
        # 提取文本关键词
        tags = index.get_tags("要分析的文本内容")
        
        # 提取带权重的特征词
        features = index.get_features("要分析的文本内容")
    
    参数说明:
        index_path (str): 索引文件存储路径，默认为 './whoosh/_search_index'
        log (Stream): 日志流对象，默认为 passed
    
    注意事项:
    1. 所有输入都会被强制转换为字符串后进行索引
    2. 索引更新采用异步方式，提高写入性能
    3. ask() 方法会结合关键词提取和相似度匹配，找到最相关的答案
    4. 搜索结果默认返回生成器，需要使用 ls 等方法转换为列表
    
    示例流式处理:
    ```python
    # 创建索引流并添加文档
    index = IndexStream()
    docs = [
        "中文文档1",
        ("doc2", "中文文档2"),
        {"doc3": "中文文档3"}
    ]
    docs >> index
    
    # 搜索并处理结果
    results = index.search("文档") >> ls
    
    # 智能问答
    question = "查找相关文档"
    answer = index.ask(question)
    ```
    """

    def __init__(self, index_path='./whoosh/_search_index',
                 log=passed, **kwargs):
        """初始化索引流对象

        Args:
            index_path (str): 索引文件存储路径,默认为'./whoosh/_search_index'
            log (Stream): 日志流对象,默认为passed
            **kwargs: 其他参数
        """
        self.log = log
        # 使用结巴中文分词path=ID (unique=True),content=TEXT
        self.analyzer = ChineseAnalyzer()
        self.schema = Schema(content=TEXT(stored=True, analyzer=self.analyzer),
                             id=ID(unique=True, stored=True))
        self.index_path = index_path

        if whoosh.index.exists_in(self.index_path):
            self.index = whoosh.index.open_dir(self.index_path)
            'find exits index_path:' >> self.log
            # self.index >> self.log
        else:
            if not os.path.exists(self.index_path):
                os.makedirs(self.index_path)
                self.index = whoosh.index.create_in(
                    self.index_path, self.schema)
                'create new  index_path:' >> self.log
                # self.index >> self.log

        Stream.__init__(self, **kwargs)

    def emit(self, x, asynchronous=False):
        """发送数据到流

        Args:
            x: 要发送的数据
            asynchronous (bool): 是否异步,默认False
        """
        self.update(x)
        # return super().emit(x, asynchronous=asynchronous)

    def update(self, x):
        """更新索引数据

        Args:
            x: 要更新的数据,支持字典、元组或其他类型
        """
        x >> self.log
        if isinstance(x, dict):
            self._to_index(x)
        elif isinstance(x, tuple):
            key, value = x
            self._to_index({key: value})
        else:
            key = time.time()
            value = x
            self._to_index({key: value})

        self._emit(x)

    def _to_index(self, x):
        """添加数据到索引

        Args:
            x (dict): 要索引的数据字典
        """
        _id, content = x.popitem()
        _id = str(_id)
        content = str(content)
        aindex = AsyncWriter(self.index, delay=0.0001)
        aindex.update_document(content=content, id=_id)
        aindex.commit()

    def search(self, query, limit=10):
        """搜索索引内容

        Args:
            query (str): 搜索查询语句
            limit (int): 返回结果数量限制,默认10

        Returns:
            generator: 搜索结果生成器
        """
        search = self.index.searcher()
        fields = set(self.index.schema._fields.keys())
        parser = MultifieldParser(list(fields), self.index.schema)
        q = parser.parse(query)
        return (i for i in search.refresh().search(q, limit=limit))

    def get_tags(self, content):
        """提取文本关键词

        Args:
            content (str): 要分析的文本内容

        Returns:
            list: 关键词列表
        """
        tags = jieba.analyse.extract_tags(content, topK=20, withWeight=0)
        if tags == []:
            return [content]
        else:
            return tags

    def get_features(self, content):
        """提取带权重的特征词

        Args:
            content (str): 要分析的文本内容

        Returns:
            list: (词,权重)元组列表
        """
        tags = jieba.analyse.extract_tags(content, topK=20, withWeight=1)
        if tags == []:
            return [content]
        else:
            return tags

    def ask(self, question):
        """智能问答

        Args:
            question (str): 问题文本

        Returns:
            str: 最相关的答案内容
        """
        # 存储搜索结果的列表
        ll = []
        # 提取问题的关键词标签
        tags = self.get_tags(question)
        # 提取问题的特征词及权重
        features = self.get_features(question)
        # 对每个标签进行搜索,限制每个标签返回30条结果
        for i in tags:
            l = self.search(i, limit=30) >> ls
            ll.extend(l)

        # 将搜索结果转换为字典格式
        data = enumerate(ll) >> ls >> dict@P
        # 如果没有搜索结果则返回None
        if len(data) == 0:
            return None
        # 如果只有一条结果则直接返回内容
        if len(data) == 1:
            return data[0]['content']

        # 为每条结果生成simhash值用于相似度比较
        objs = [(str(k), Simhash(features)) for k, v in data.items()]
        if objs == []:
            return None

        # 构建simhash索引
        _index = SimhashIndex(objs)
        # 找到与问题特征最相似的结果
        obj_id, distance = _index.get_near_dups(Simhash(features))
        # 返回最相似结果的内容,并替换特殊空格字符
        try:
            return data[int(obj_id)]['content'].replace('\u3000\u3000', '\n')
        except Exception as e:
            return e
