from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy import Boolean, Column, Integer, String, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from typing import Iterable, List

import enum

Base = declarative_base()


class WalrusState(enum.Enum):
    SETUP = enum.auto()
    ONGOING = enum.auto()
    SCORING = enum.auto()
    COMPLETE = enum.auto()


class Walrus(Base):
    __tablename__ = "Walrus"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    host_id = Column(Integer)
    state = Column(Enum(WalrusState))
    categories = relationship("Category", back_populates="walrus")  # type: List[Category]
    # submissions = relationship("Submission", back_populates="walrus")  # type: List[Submission]

    # def __repr__(self):
    #     return f"<Server id={self.id}, name={self.name}, sheet={self.sheet}>"


class Category(Base):
    __tablename__ = "Category"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    walrus_id = Column(Integer, ForeignKey("Walrus.id"))

    walrus = relationship("Walrus", back_populates="categories")
    submissions = relationship("Submission", back_populates="category")
    __table_args__ = (UniqueConstraint("name", "walrus_id"),)


class Submission(Base):
    __tablename__ = "Submission"
    id = Column(Integer, primary_key=True)
    link = Column(String)
    submitter_id = Column(Integer)
    # walrus_id = Column(Integer, ForeignKey("Walrus.id"))
    category_id = Column(Integer, ForeignKey("Category.id"))

    # walrus = relationship("Walrus", back_populates="submissions")
    category = relationship("Category", back_populates="submissions")
    scores = relationship("Score", back_populates="submission")
    __table_args__ = (UniqueConstraint("submitter_id", "category_id"),)


class Score(Base):
    __tablename__ = "Score"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    score = Column(Integer)
    submission_id = Column(Integer, ForeignKey("Submission.id"))

    submission = relationship("Submission", back_populates="scores")
