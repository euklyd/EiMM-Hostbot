from sqlalchemy import Boolean, Column, Date, Integer, String
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
            f'date={self.date}, count={self.count}>'
        )


class EventEmoji(Base):
    __tablename__ = "EventEmoji"
    emoji_id = Column(Integer, primary_key=True)
    server_id = Column(Integer, primary_key=True)
    date = Column(Date)
    owner_id = Column(Integer)
    event = Column(String)
    active = Column(Boolean)

    def __repr__(self):
        return (
            f'<EventEmoji emoji_id={self.emoji_id}, server_id={self.server_id}, owner_id={self.owner_id}'
            f'date={self.date}, event={self.event}, active={self.active}>'
        )
