# Created by 1e0n in 2013
from __future__ import division, unicode_literals

import re
import sys
import hashlib
import logging
import numbers
import collections
from itertools import groupby

"""
SimHash 文本相似度计算工具

这个模块提供了基于 SimHash 算法的文本相似度计算功能。主要包含两个核心类：
- Simhash: 计算文本的 simhash 值
- SimhashIndex: 构建 simhash 索引用于快速相似文本检索

主要功能：
1. 文本去重
2. 相似文本检测
3. 文本指纹生成
4. 高效相似度索引

基本用例:
---------
# 计算两个文本的相似度
>>> text1 = "今天天气真不错"
>>> text2 = "今天天气很好"
>>> hash1 = Simhash(text1)
>>> hash2 = Simhash(text2)
>>> distance = hash1.distance(hash2)  # 获取汉明距离

# 批量文本去重
>>> texts = [
...     ("doc1", "Python编程入门"),
...     ("doc2", "Python编程教程"), 
...     ("doc3", "Java开发实战")
... ]
>>> objs = [(id, Simhash(text)) for id, text in texts]
>>> index = SimhashIndex(objs, k=3)  # k是相似度阈值
>>> # 查找与新文本相似的文档
>>> new_hash = Simhash("Python编程指南")
>>> similar_id, distance = index.get_near_dups(new_hash)

高级用例:
---------
# 自定义分词
>>> s = Simhash("文本内容", reg=r'[\u4e00-\u9fff]+')

# 使用特征权重
>>> features = {
...     "Python": 5,  # 重要特征权重更高
...     "编程": 3,
...     "入门": 1
... }
>>> s = Simhash(features)

注意事项：
1. 默认使用64位指纹，可通过参数f调整
2. 相似度阈值k的选择会影响检索效果
3. 大规模数据建议优化存储结构
"""

basestring = str
unicode = str
long = int


def _hashfunc(x):
    return int(hashlib.md5(x).hexdigest(), 16)


class Simhash(object):
    """SimHash算法实现类.

    SimHash是一种用于计算文本相似度的算法,可以将文本转换为固定长度的指纹。
    主要用于文本去重、相似文本检测等场景。

    参数
    ----------
    value : str, Simhash, Iterable 或 int
        要计算simhash的内容:
        - str: 文本字符串
        - Simhash: 另一个Simhash对象
        - Iterable: 特征序列
        - int: 直接指定hash值
    f : int, 可选
        生成的指纹维度,默认64位
    reg : str 或 re.Pattern, 可选
        用于分词的正则表达式,默认匹配中英文字符
    hashfunc : callable, 可选
        自定义hash函数,接收utf-8字符串,返回整数
    log : Logger, 可选
        日志对象

    示例
    --------
    >>> # 计算文本的simhash
    >>> s1 = Simhash('你好世界')
    >>> s2 = Simhash('世界你好')
    >>> s1.distance(s2)  # 计算相似度
    3
    
    >>> # 使用特征序列
    >>> features = ['你好', '世界']
    >>> s3 = Simhash(features)

    >>> # 自定义hash函数
    >>> def my_hash(x):
    ...     return int(hashlib.sha1(x).hexdigest(), 16)
    >>> s4 = Simhash('hello', hashfunc=my_hash)

    参见
    --------
    distance : 计算两个simhash的汉明距离
    """

    def __init__(
        self, value, f=64, reg=r'[\w\u4e00-\u9fcc]+', hashfunc=None, log=None
    ):
        """
        `f` is the dimensions of fingerprints

        `reg` is meaningful only when `value` is basestring and describes
        what is considered to be a letter inside parsed string. Regexp
        object can also be specified (some attempt to handle any letters
        is to specify reg=re.compile(r'\w', re.UNICODE))

        `hashfunc` accepts a utf-8 encoded string and returns a unsigned
        integer in at least `f` bits.
        """

        self.f = f
        self.reg = reg
        self.value = None

        if hashfunc is None:
            self.hashfunc = _hashfunc
        else:
            self.hashfunc = hashfunc

        if log is None:
            self.log = logging.getLogger("simhash")
        else:
            self.log = log

        if isinstance(value, Simhash):
            self.value = value.value
        elif isinstance(value, basestring):
            self.build_by_text(unicode(value))
        elif isinstance(value, collections.Iterable):
            self.build_by_features(value)
        elif isinstance(value, numbers.Integral):
            self.value = value
        else:
            raise Exception('Bad parameter with type {}'.format(type(value)))

    def _slide(self, content, width=4):
        return [content[i:i + width] for i in range(max(len(content) - width + 1, 1))]

    def _tokenize(self, content):
        content = content.lower()
        content = ''.join(re.findall(self.reg, content))
        ans = self._slide(content)
        return ans

    def build_by_text(self, content):
        features = self._tokenize(content)
        features = {k: sum(1 for _ in g) for k, g in groupby(sorted(features))}
        return self.build_by_features(features)

    def build_by_features(self, features):
        """
        `features` might be a list of unweighted tokens (a weight of 1
                   will be assumed), a list of (token, weight) tuples or
                   a token -> weight dict.
        """
        v = [0] * self.f
        masks = [1 << i for i in range(self.f)]
        if isinstance(features, dict):
            features = features.items()
        for f in features:
            if isinstance(f, basestring):
                h = self.hashfunc(f.encode('utf-8'))
                w = 1
            else:
                assert isinstance(f, collections.Iterable)
                h = self.hashfunc(f[0].encode('utf-8'))
                w = f[1]
            for i in range(self.f):
                v[i] += w if h & masks[i] else -w
        ans = 0
        for i in range(self.f):
            if v[i] > 0:
                ans |= masks[i]
        self.value = ans

    def distance(self, another):
        assert self.f == another.f
        x = (self.value ^ another.value) & ((1 << self.f) - 1)
        ans = 0
        while x:
            ans += 1
            x &= x - 1
        return ans


class SimhashIndex(object):
    """SimHash索引类.

    用于构建和管理SimHash值的索引,支持快速查找相似内容。
    通过将SimHash值分段建立倒排索引,实现高效的相似度检索。

    参数
    ----------
    objs : list of (obj_id, simhash)
        要建立索引的对象列表,每个元素为(对象ID, SimHash对象)的元组
    f : int, 可选
        SimHash的位数,默认64位
    k : int, 可选
        相似度阈值,两个SimHash的汉明距离小于k时认为相似,默认24
    log : Logger, 可选
        日志对象,默认使用simhash logger

    示例
    --------
    >>> # 创建SimHash对象
    >>> s1 = Simhash('如何更好地学习Python')
    >>> s2 = Simhash('Python学习方法和技巧') 
    >>> s3 = Simhash('Python入门教程')
    
    >>> # 构建索引
    >>> objs = [('doc1', s1), ('doc2', s2), ('doc3', s3)]
    >>> index = SimhashIndex(objs, k=10)  # 汉明距离阈值为10
    
    >>> # 查找相似文档
    >>> s = Simhash('Python基础学习')
    >>> dups = index.get_near_dups(s)  # 返回相似文档ID列表

    注意
    -------
    - k值的选择会影响查找的精度和效率
    - 索引会占用一定内存,数据量大时需要注意内存使用
    """

    def __init__(self, objs, f=64, k=24, log=None):
        """
        `objs` is a list of (obj_id, simhash)
        obj_id is a string, simhash is an instance of Simhash
        `f` is the same with the one for Simhash
        `k` is the tolerance
        """
        self.k = k
        self.f = f
        count = len(objs)

        if log is None:
            self.log = logging.getLogger("simhash")
        else:
            self.log = log

        self.log.info('Initializing %s data.', count)

        self.bucket = collections.defaultdict(set)

        for i, q in enumerate(objs):
            if i % 10000 == 0 or i == count - 1:
                self.log.info('%s/%s', i + 1, count)

            self.add(*q)

    def get_near_dups(self, simhash):
        """
        `simhash` is an instance of Simhash
        return a list of obj_id, which is in type of str
        """
        assert simhash.f == self.f

        ans = dict()

        for key in self.get_keys(simhash):
            dups = self.bucket[key]
            self.log.debug('key:%s', key)
            if len(dups) > 200:
                self.log.warning('Big bucket found. key:%s, len:%s', key, len(dups))

            for dup in dups:
                sim2, obj_id = dup.split(',', 1)
                sim2 = Simhash(long(sim2, 16), self.f)

                distance = simhash.distance(sim2)
                if distance <= self.k:
                    ans[obj_id] = distance

        min_d = min(ans, key=ans.get)
        return min_d, ans[min_d]

    def add(self, obj_id, simhash):
        """
        `obj_id` is a string
        `simhash` is an instance of Simhash
        """
        assert simhash.f == self.f

        for key in self.get_keys(simhash):
            v = '%x,%s' % (simhash.value, obj_id)
            self.bucket[key].add(v)

    def delete(self, obj_id, simhash):
        """
        `obj_id` is a string
        `simhash` is an instance of Simhash
        """
        assert simhash.f == self.f

        for key in self.get_keys(simhash):
            v = '%x,%s' % (simhash.value, obj_id)
            if v in self.bucket[key]:
                self.bucket[key].remove(v)

    @property
    def offsets(self):
        """
        You may optimize this method according to <http://www.wwwconference.org/www2007/papers/paper215.pdf>
        """
        return [self.f // (self.k + 1) * i for i in range(self.k + 1)]

    def get_keys(self, simhash):
        for i, offset in enumerate(self.offsets):
            if i == (len(self.offsets) - 1):
                m = 2 ** (self.f - offset) - 1
            else:
                m = 2 ** (self.offsets[i + 1] - offset) - 1
            c = simhash.value >> offset & m
            yield '%x:%x' % (c, i)

    def bucket_size(self):
        return len(self.bucket)

# 场景1: 网页去重
def deduplicate_webpages(urls_and_contents):
    """网页去重示例"""
    index = SimhashIndex([], k=3)
    unique_pages = []
    
    for url, content in urls_and_contents:
        hash = Simhash(content)
        try:
            # 尝试找相似页面
            similar_id, distance = index.get_near_dups(hash)
            print(f"发现相似页面: {url} 与 {similar_id}, 距离: {distance}")
        except:
            # 未找到相似页面，添加到索引
            index.add(url, hash)
            unique_pages.append((url, content))
    return unique_pages

# 场景2: 文本聚类
def cluster_texts(texts, threshold=3):
    """相似文本聚类示例"""
    clusters = {}
    index = SimhashIndex([], k=threshold)
    
    for text_id, text in texts:
        hash = Simhash(text)
        try:
            similar_id, _ = index.get_near_dups(hash)
            # 添加到已有簇
            clusters[similar_id].append(text_id)
        except:
            # 创建新簇
            clusters[text_id] = [text_id]
            index.add(text_id, hash)
    return clusters
