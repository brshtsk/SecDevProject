from typing import List

from pydantic import BaseModel

from app.domain import VoteType


class VoteBase(BaseModel):
    value: VoteType


class VoteCreate(VoteBase):
    pass


class Vote(VoteBase):
    id: int
    user_id: int
    idea_id: int

    class Config:
        from_attributes = True


class IdeaBase(BaseModel):
    title: str
    description: str = None


class IdeaCreate(IdeaBase):
    pass


class Idea(IdeaBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True


class IdeaWithScore(Idea):
    score: int
    up_votes: int
    down_votes: int
    abstain_votes: int


class UserBase(BaseModel):
    username: str
    email: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    is_active: bool
    ideas: List[Idea] = []

    class Config:
        from_attributes = True
