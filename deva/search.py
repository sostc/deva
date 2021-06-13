import os
import time

from .pipe import passed
from .core import Stream
from .utils.simhash import Simhash, SimhashIndex

from whoosh.fields import Schema, TEXT, ID
import whoosh.index
from whoosh.writing import AsyncWriter
from whoosh.qparser import MultifieldParser

from jieba.analyse import ChineseAnalyzer
import jieba
import jieba.analyse

import numpy as np


@Stream.register_api()
class IndexStream(Stream):
    """
    所有输入都会被强制转化成str,并进行中文索引
    """

    def __init__(self, index_path='./whoosh/_search_index',
                 log=passed, **kwargs):
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
        self.update(x)
        # return super().emit(x, asynchronous=asynchronous)

    def update(self, x):
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
        _id, content = x.popitem()
        _id = str(_id)
        content = str(content)
        aindex = AsyncWriter(self.index, delay=0.0001)
        aindex.update_document(content=content, id=_id)
        aindex.commit()

    def search(self, query, limit=10):
        search = self.index.searcher()
        fields = set(self.index.schema._fields.keys())
        parser = MultifieldParser(list(fields), self.index.schema)
        q = parser.parse(query)
        return (i for i in search.refresh().search(q, limit=limit))

    def get_tags(self, content):
        tags = jieba.analyse.extract_tags(content, topK=20, withWeight=0)
        if tags == []:
            return [content]
        else:
            return tags

    def get_features(self, content):
        tags = jieba.analyse.extract_tags(content, topK=20, withWeight=1)
        if tags == []:
            return [content]
        else:
            return tags

    def ask(self, question):
        ll = []
        tags = self.get_tags(question)
        features = self.get_features(question)
        for i in tags:
            l = self.search(i, limit=30) >> ls
            ll.extend(l)

        data = enumerate(ll) >> ls >> dict@P
        if len(data) == 1:
            return data[0]['content']

        objs = [(str(k), Simhash(features)) for k, v in data.items()]
        if objs == []:
            return None

        _index = SimhashIndex(objs)
        obj_id, distance = _index.get_near_dups(Simhash(features))
        # ,data.values()|pmap(lambda x:x['content'])|unique@P|ls
        return data[int(obj_id)]['content'].replace('\u3000\u3000', '\n')
#         except Exception as e:
#             return e
