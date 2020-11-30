from deva.utils.whooshalchemy import IndexService
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, Text, create_engine
from sqlalchemy.orm.session import sessionmaker
from deva import *

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


CpipLog.search_query('tensorflow') >> first

CpipLog.search_query('tensorflow') >> ls
