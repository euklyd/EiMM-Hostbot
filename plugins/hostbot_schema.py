from sqlalchemy import ForeignKey
from sqlalchemy import Column, Integer, String

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class Server(Base):
    __tablename__ = 'Server'
    id       = Column(Integer, primary_key=True)
    roles    = relationship('Role', backref='A.id')
    channels = relationship('Channel', backref='A.id')


class Role(Base):
    __tablename__ = 'Role'
    id        = Column(Integer, primary_key=True)
    type      = Column(String)
    server_id = Column(Integer, ForeignKey='Server.id')


class Channel(Base):
    __tablename__ = 'Channel'
    id        = Column(Integer, primary_key=True)
    type      = Column(String)
    server_id = Column(Integer, ForeignKey='Server.id')
