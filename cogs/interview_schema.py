from typing import Iterable

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy import ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Server(Base):
    __tablename__ = 'Server'
    id = Column(Integer, primary_key=True)
    sheet_name = Column(String, unique=True)
    default_question = Column(String)
    answer_channel = Column(Integer)
    back_channel = Column(Integer)
    limit = Column(DateTime)  # time since someone's last interview (start date) to be reinterviewed
    reinterviews_allowed = Column(Boolean)
    active = Column(Boolean)  # are interviews open for new questions / voting
    manager_role_id = Column(Integer)

    # I'm typing the relationships manually, since type hinting is getting messed up elsewhere without it.
    interviews = relationship('Interview', back_populates='server')  # type: Iterable[Interview]
    votes = relationship('Vote', back_populates='server')  # type: Iterable[Vote]
    opt_outs = relationship('OptOut', back_populates='server')  # type: Iterable[OptOut]

    def __repr__(self):
        return (
            f'<Server id={self.id}, answer_channel={self.answer_channel}, back_channel={self.back_channel}, '
            f'sheet_name={self.sheet_name}>, default_question={self.default_question}, limit={self.limit}, '
            f'reinterviews_allowed={self.reinterviews_allowed}, active={self.active}>'
        )


class Interview(Base):
    """
    All the data for a single given interview week.
    """
    __tablename__ = 'Interview'
    id = Column(Integer, primary_key=True)  # auto-incremented primary key
    # NOTE: (server_id, interviewee_id) is not a unique keypair, as people can be re-interviewed
    server_id = Column(Integer, ForeignKey('Server.id'))
    interviewee_id = Column(Integer)
    start_time = Column(DateTime)  # use utc timezone internally
    sheet_name = Column(String)  # what page of the sheet
    questions_asked = Column(Integer)
    questions_answered = Column(Integer)
    # NOTE: the "current" column could probably be removed in favor of just using the most recent timestamp
    current = Column(Boolean)  # "True" indicates the current interview
    op_channel_id = Column(Integer)
    op_message_id = Column(Integer)
    # TODO: oh god there's so much more
    #  later edit: is there??? i think it may be good now

    server = relationship('Server', back_populates='interviews')  # type: Server
    askers = relationship('Asker', back_populates='interview')  # type: Iterable[Asker]

    def __repr__(self):
        # TODO: update
        return (
            f'<Interview id={self.id}, server_id={self.server_id}, interviewee_id={self.interviewee_id}, '
            f'start_time={self.start_time}, sheet_name={self.sheet_name}, questions_asked={self.questions_asked}, '
            f'questions_answered={self.questions_answered}, current={self.current}>'
        )


class Vote(Base):
    __tablename__ = 'Vote'
    server_id = Column(Integer, ForeignKey('Server.id'), primary_key=True)
    voter_id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime)  # use utc timezone internally

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


class Asker(Base):
    # TODO: refactor
    __tablename__ = 'Asker'
    # server_id = Column(Integer, ForeignKey('Server.id'), primary_key=True)
    interview_id = Column(Integer, ForeignKey('Interview.id'), primary_key=True)
    asker_id = Column(Integer, primary_key=True)
    num_questions = Column(Integer)

    interview = relationship('Interview', back_populates='askers')  # type: Interview

    def __repr__(self):
        return f'<Asker interview_id={self.interview_id}, asker_id={self.asker_id}, num_questions={self.num_questions}'


# TODO: reorganize InterviewMeta into a one(server)-to-many(metas), with a "current" boolean flag field
#  to mark the current one. Also, merge IntervieweeStats in with that.
# NOTE: could refactor TotalQuestions into a meta-per-asker table rather than *just* questions asked
