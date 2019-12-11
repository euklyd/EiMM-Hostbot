from sqlalchemy import Column, Date, Integer
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class EmojiCount(Base):
    __tablename__ = 'EmojiCount'
    emoji_id = Column(Integer, primary_key=True)
    server_id = Column(Integer, primary_key=True)
    date = Column(Date, primary_key=True)
    user_id = Column(Integer, primary_key=True)
    count = Column(Integer)

    def __repr__(self):
        return (
            f'<EmojiCount emoji_id={self.emoji_id}, server_id={self.server_id}, user_id={self.user_id}'
            f'date={self.date}>, count={self.count}'
        )