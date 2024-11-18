from deva.utils.whooshalchemy import IndexService
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, Text, create_engine
from sqlalchemy.orm.session import sessionmaker
from deva import *


"""基于SQLAlchemy和Whoosh的全文搜索示例

本示例演示如何使用SQLAlchemy和Whoosh实现数据库的全文搜索功能。

主要功能:
1. 使用SQLAlchemy定义数据模型和数据库操作
2. 使用Whoosh建立全文索引
3. 支持多字段联合搜索
4. 支持模糊搜索和精确匹配

基本用例:
---------
# 创建数据库和表
engine = create_engine('sqlite:///cpiplog.db')
Base.metadata.create_all(engine)

# 创建会话
Session = sessionmaker(bind=engine)
session = Session()

# 配置索引
config = {"WHOOSH_BASE": "/tmp/whoosh"}
index_service = IndexService(config=config, session=session)
index_service.register_class(CpipLog)

# 添加数据
log = CpipLog(tel='18626880688', lib_name='tensorflow', loginfo='installlog')
session.add(log)
session.commit()

# 搜索数据
# 方式1:获取第一条结果
CpipLog.search_query('tensorflow') >> first >> print

# 方式2:获取所有结果
CpipLog.search_query('tensorflow') >> ls >> print
"""

engine = create_engine('sqlite:///cpiplog.db')
Base = declarative_base()

class CpipLog(Base):
    __tablename__ = 'cpiplog'
    __table_args__ = {'extend_existing': True}
    __searchable__ = ['tel', 'lib_name', 'loginfo']  # 这些字段将被索引

    id = Column(Integer, primary_key=True)
    tel = Column(Text)
    lib_name = Column(Text)
    loginfo = Column(Text)

    def __repr__(self):
        return '{0}(tel={1},lib_name={2})'.format(self.__class__.__name__, self.tel, self.lib_name)


Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()
config = {"WHOOSH_BASE": "/tmp/whoosh"}  # 索引存储的位置
index_service = IndexService(config=config, session=session)
index_service.register_class(CpipLog)


log = CpipLog(tel='18626880688', lib_name='tensorflow', loginfo='istalllog')
session.add(log)
session.commit()


CpipLog.search_query('tensorflow') >> first >> print

CpipLog.search_query('tensorflow') >> ls >> print
