from sqlalchemy import Column, Date, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ScryfallText(Base):
    __tablename__ = 'ScryfallText'
    scryfall_id = Column(String, primary_key=True)
    cache_time = Column(Date)
    text = Column(String)
