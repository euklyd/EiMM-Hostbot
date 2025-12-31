from sqlalchemy import Column, Date, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ScryfallText(Base):
    __tablename__ = "ScryfallText"
    scryfall_id = Column(String, primary_key=True)
    cache_time = Column(Date)
    text = Column(String)
