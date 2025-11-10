from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.domain import VoteType


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

    ideas = relationship("Idea", back_populates="owner")
    votes = relationship("Vote", back_populates="user")


class Idea(Base):
    __tablename__ = "ideas"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="ideas")
    votes = relationship("Vote", back_populates="idea")


class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, index=True)
    value = Column(Enum(VoteType), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    idea_id = Column(Integer, ForeignKey("ideas.id"))

    user = relationship("User", back_populates="votes")
    idea = relationship("Idea", back_populates="votes")
