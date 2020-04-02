from .pipe import passed
from .core import Stream
from whoosh.fields import Schema, TEXT
import whoosh.index
from whoosh.writing import AsyncWriter
from whoosh.qparser import MultifieldParser
import os


@Stream.register_api()
class IndexStream(Stream):
    """
    所有输入都会被强制转化成str,并进行中文索引
    """

    def __init__(self, index_path='./whoosh/_search_index', log=passed, **kwargs):
        self.log = log
        # take the stream specific kwargs out
        from jieba.analyse import ChineseAnalyzer
        # 使用结巴中文分词
        self.analyzer = ChineseAnalyzer()
        self.schema = Schema(content=TEXT(stored=True, analyzer=self.analyzer))
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
        self.sink(self._to_index)

    def _to_index(self, x):
        # implement search here
        x = str(x)
        x >> self.log
        aindex = AsyncWriter(self.index, delay=0.001)
        aindex.add_document(content=x)
        aindex.commit()

    def search(self, query, limit=10):
        search = self.index.searcher()
        fields = set(self.index.schema._fields.keys())
        parser = MultifieldParser(list(fields), self.index.schema)
        q = parser.parse(query)
        return (i['content'] for i in search.refresh().search(q, limit=limit))
