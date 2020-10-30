from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy import ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Server(Base):
    __tablename__ = 'Server'
    id = Column(Integer, primary_key=True)
    sheet_url = Column(String)
    answer_channel = Column(Integer)
    back_channel = Column(Integer)

    meta = relationship('Meta', back_populates='server', uselist=False)  # TODO: is uselist=False correct here? i think so
    votes = relationship('Vote', back_populates='server')
    opt_outs = relationship('OptOut', back_populates='server')
    total_questions = relationship('TotalQuestions', back_populates='server')
    interviewee_stats = relationship('IntervieweeStats', back_populates='server')

    def __repr__(self):
        return (
            f'<Server id={self.id}, answer_channel={self.answer_channel}, '
            f'back_channel={self.back_channel}, sheet={self.sheet_url}>'
        )


class Meta(Base):
    __tablename__ = 'Meta'
    server_id = Column(Integer, ForeignKey('Server.id'), primary_key=True)
    interviewee_id = Column(Integer)
    start_time = Column(DateTime)  # use utc timezone internally
    num_questions = Column(Integer)
    # TODO: oh god there's so much more
    limit = Column(DateTime)
    reinterviews_allowed = Column(Boolean)
    active = Column(Boolean)

    server = relationship('Server', back_populates='meta', uselist=False)

    def __repr__(self):
        return f'<Meta server_id={self.server_id}, interviewee_id={self.interviewee_id}, start_time={self.start_time}, num_questions={self.num_questions}>'


class Vote(Base):
    __tablename__ = 'Vote'
    server_id = Column(Integer, ForeignKey('Server.id'), primary_key=True)
    voter_id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime)  # # use utc timezone internally

    server = relationship('Server', back_populates='votes')

    def __repr__(self):
        return f'<Vote server_id={self.server_id}, voter_id={self.voter_id}, candidate_id={self.candidate_id}, timestamp={self.timestamp}>'


class OptOut(Base):
    __tablename__ = 'OptOut'
    server_id = Column(Integer, ForeignKey('Server.id'), primary_key=True)
    opt_id = Column(Integer, primary_key=True)

    server = relationship('Server', back_populates='opt_outs')

    def __repr__(self):
        return f'<OptOut server_id={self.server_id}, opt_id={self.opt_id}'


class TotalQuestions(Base):
    __tablename__ = 'TotalQuestions'
    server_id = Column(Integer, ForeignKey('Server.id'), primary_key=True)
    interviewee_id = Column(Integer, primary_key=True)
    asker_id = Column(Integer, primary_key=True)
    num_questions = Column(Integer)

    server = relationship('Server', back_populates='total_questions')

    def __repr__(self):
        return f'<TotalQuestions server_id={self.server_id}, interviewee_id={self.interviewee_id}, asker_id={self.asker_id}, num_questions={self.num_questions}'


class IntervieweeStats(Base):
    __tablename__ = 'IntervieweeStats'
    server_id = Column(Integer, ForeignKey('Server.id'), primary_key=True)
    interviewee_id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, primary_key=True)  # people will eventually be reinterviewed
    num_questions = Column(Integer)

    server = relationship('Server', back_populates='interviewee_stats')

    def __repr__(self):
        return f'<IntervieweeStats server_id={self.server_id}, interviewee_id={self.interviewee_id}, timestamp={self.timestamp}, num_questions={self.num_questions}'
