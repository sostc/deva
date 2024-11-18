"""WhooshAlchemy - SQLAlchemy模型的全文搜索扩展

为SQLAlchemy模型添加Whoosh全文搜索功能。基于Flask-whooshalchemy修改,
支持但不强制要求Flask。

主要功能:
1. 自动为SQLAlchemy模型创建全文索引
2. 支持多字段联合搜索
3. 支持中文分词
4. 支持模糊搜索和精确匹配

基本用例:
---------
# 创建数据模型
class Post(db.Model):
    __searchable__ = ['title', 'content']  # 需要索引的字段
    
    id = Column(Integer, primary_key=True)
    title = Column(String)
    content = Column(Text)

# 配置索引
config = {"WHOOSH_BASE": "/path/to/index"}
index_service = IndexService(config=config)
index_service.register_class(Post)

# 搜索
Post.search_query('关键词') >> first >> print  # 获取第一条结果
Post.search_query('关键词') >> ls >> print     # 获取所有结果

:copyright: (c) 2012 by Stefane Fermigier
:copyright: (c) 2012 by Karl Gyllstrom
:license: BSD
"""

from __future__ import absolute_import, print_function, unicode_literals

import os

from six import text_type

import sqlalchemy
import whoosh.index
from sqlalchemy import event
from sqlalchemy.orm.session import Session
from whoosh.fields import Schema
from whoosh.qparser import MultifieldParser


class IndexService(object):
    """SQLAlchemy模型的索引服务类

    该类用于管理SQLAlchemy模型的Whoosh全文索引,提供索引的创建、更新和搜索功能。

    参数:
    -------
    config : dict, 可选
        配置字典,包含索引存储路径等配置项
    session : Session, 可选
        SQLAlchemy会话对象
    whoosh_base : str, 可选
        索引文件存储的根目录,默认为'whoosh_indexes'

    示例:
    -------
    # 创建索引服务
    config = {"WHOOSH_BASE": "/tmp/whoosh"}
    index_service = IndexService(config=config)

    # 注册模型类
    index_service.register_class(Post)

    # 使用自定义会话
    session = Session()
    index_service = IndexService(session=session)
    """

    def __init__(self, config=None, session=None, whoosh_base=None):
        self.session = session
        if not whoosh_base and config:
            whoosh_base = config.get("WHOOSH_BASE")
        if not whoosh_base:
            whoosh_base = "whoosh_indexes"  # Default value
        self.whoosh_base = whoosh_base
        self.indexes = {}
        from jieba.analyse import ChineseAnalyzer

        self.analyzer = ChineseAnalyzer

        event.listen(Session, "before_commit", self.before_commit)
        event.listen(Session, "after_commit", self.after_commit)

    def register_class(self, model_class):
        """
        Registers a model class, by creating the
        necessary Whoosh index if needed.
        """

        index_path = os.path.join(self.whoosh_base, model_class.__name__)

        schema, primary = self._get_whoosh_schema_and_primary(model_class)

        if whoosh.index.exists_in(index_path):
            index = whoosh.index.open_dir(index_path)
        else:
            if not os.path.exists(index_path):
                os.makedirs(index_path)
            index = whoosh.index.create_in(index_path, schema)

        self.indexes[model_class.__name__] = index
        model_class.search_query = Searcher(model_class, primary, index,
                                            self.session)
        return index

    def index_for_model_class(self, model_class):
        """
        Gets the whoosh index for this model, creating one if it does
         not exist.in creating one, a schema is created based on the
         fields of the model.Currently we only support primary
        key -> whoosh.ID, and sqlalchemy.TEXT
        -> whoosh.TEXT, but can add more later. A dict of
        model -> whoosh index
        is added to the ``app`` variable.
        """
        index = self.indexes.get(model_class.__name__)
        if index is None:
            index = self.register_class(model_class)
        return index

    def _get_whoosh_schema_and_primary(self, model_class):
        schema = {}
        primary = None
        for field in model_class.__table__.columns:
            if field.primary_key:
                schema[field.name] = whoosh.fields.ID(stored=True, unique=True)
                primary = field.name
            if field.name in model_class.__searchable__:
                if type(field.type) in (sqlalchemy.types.Text,
                                        sqlalchemy.types.UnicodeText):
                    schema[field.name] = whoosh.fields.TEXT(
                        analyzer=self.analyzer())

        return Schema(**schema), primary

    def before_commit(self, session):
        self.to_update = {}

        for model in session.new:
            model_class = model.__class__
            if hasattr(model_class, '__searchable__'):
                self.to_update.setdefault(model_class.__name__, []).append(
                    ("new", model))

        for model in session.deleted:
            model_class = model.__class__
            if hasattr(model_class, '__searchable__'):
                self.to_update.setdefault(model_class.__name__, []).append(
                    ("deleted", model))

        for model in session.dirty:
            model_class = model.__class__
            if hasattr(model_class, '__searchable__'):
                self.to_update.setdefault(model_class.__name__, []).append(
                    ("changed", model))

    def after_commit(self, session):
        """
        Any db updates go through here. We check if any of these models have
        ``__searchable__`` fields, indicating they need to be indexed. With
        these we update the whoosh index for the model. If no index exists,
         it will be created here; this could impose a penalty on the
         initial commit of a model.
        """

        for typ, values in self.to_update.items():
            model_class = values[0][1].__class__
            index = self.index_for_model_class(model_class)
            with index.writer() as writer:
                primary_field = model_class.search_query.primary
                searchable = model_class.__searchable__

                for change_type, model in values:
                    # delete everything. stuff that's updated or inserted will
                    # get added as a new doc. Could probably replace this with
                    # a whoosh update.

                    writer.delete_by_term(
                        primary_field, text_type(getattr(model,
                                                         primary_field)))

                    if change_type in ("new", "changed"):
                        attrs = dict((key, getattr(model, key))
                                     for key in searchable)
                        attrs[primary_field] = text_type(
                            getattr(model, primary_field))
                        writer.add_document(**attrs)

        self.to_update = {}


class Searcher(object):
    """搜索器类,用于执行全文搜索

    该类会被赋值给Model类的search_query属性,提供全文搜索功能。
    支持多字段联合搜索、分页查询等功能。

    参数:
    -------
    model_class : class
        SQLAlchemy模型类
    primary : str
        主键字段名
    index : whoosh.index.Index
        Whoosh索引对象
    session : Session, 可选
        SQLAlchemy会话对象

    示例:
    -------
    # 基本搜索
    Post.search_query('关键词')  # 搜索所有字段

    # 限制返回数量
    Post.search_query('关键词', limit=10)  # 只返回前10条

    # 分页查询
    Post.search_query('关键词', pagenum=2, pagelen=20)  # 第2页,每页20条
    """

    def __init__(self, model_class, primary, index, session=None):
        self.model_class = model_class
        self.primary = primary
        self.index = index
        self.session = session
        self.searcher = index.searcher()
        fields = set(index.schema._fields.keys()) - set([self.primary])
        self.parser = MultifieldParser(list(fields), index.schema)

    def __call__(self, query, limit=20, pagenum=1, pagelen=20):
        session = self.session
        # 使用Flask时,从模型类的query属性获取session
        if not session:
            session = self.model_class.query.session

        if not pagenum:
            results = self.index.searcher().search(self.parser.parse(query),
                                                   limit=limit)
        else:
            results = self.index.searcher().search_page(
                self.parser.parse(query),
                pagenum=pagenum,
                pagelen=pagelen
            )

        keys = [x[self.primary] for x in results]
        primary_column = getattr(self.model_class, self.primary)
        return session.query(self.model_class).filter(primary_column.in_(keys))