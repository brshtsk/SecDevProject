from sqlalchemy.orm import Session
from sqlalchemy.sql import case, func

from app import models, schemas
from app.domain import VoteType


def get_idea(db: Session, idea_id: int):
    return db.query(models.Idea).filter(models.Idea.id == idea_id).first()


def get_ideas(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Idea).offset(skip).limit(limit).all()


def create_idea(db: Session, idea: schemas.IdeaCreate, owner_id: int):
    db_idea = models.Idea(**idea.dict(), owner_id=owner_id)
    db.add(db_idea)
    db.commit()
    db.refresh(db_idea)
    return db_idea


def update_idea(
    db: Session, idea_id: int, idea: schemas.IdeaCreate, current_user_id: int
):
    db_idea = get_idea(db, idea_id)
    if not db_idea or db_idea.owner_id != current_user_id:
        return None

    for key, value in idea.dict().items():
        setattr(db_idea, key, value)

    db.commit()
    db.refresh(db_idea)
    return db_idea


def delete_idea(db: Session, idea_id: int, current_user_id: int):
    db_idea = get_idea(db, idea_id)
    if not db_idea or db_idea.owner_id != current_user_id:
        return False

    db.delete(db_idea)
    db.commit()
    return True


def vote_idea(db: Session, idea_id: int, user_id: int, vote_value: VoteType):
    # Проверяем, есть ли уже голос от этого пользователя
    existing_vote = (
        db.query(models.Vote)
        .filter(models.Vote.user_id == user_id, models.Vote.idea_id == idea_id)
        .first()
    )

    if existing_vote:
        # Обновляем существующий голос
        existing_vote.value = vote_value
        db.commit()
        return existing_vote

    # Создаем новый голос
    db_vote = models.Vote(value=vote_value, user_id=user_id, idea_id=idea_id)
    db.add(db_vote)
    db.commit()
    db.refresh(db_vote)
    return db_vote


def get_ideas_with_scores(db: Session, skip: int = 0, limit: int = 100):
    # Запрос, который подсчитывает голоса для каждой идеи
    ideas_with_scores = (
        db.query(
            models.Idea,
            func.count(case((models.Vote.value == VoteType.UP, 1))).label("up_votes"),
            func.count(case((models.Vote.value == VoteType.DOWN, 1))).label(
                "down_votes"
            ),
            func.count(case((models.Vote.value == VoteType.ABSTAIN, 1))).label(
                "abstain_votes"
            ),
        )
        .outerjoin(models.Vote, models.Idea.id == models.Vote.idea_id)
        .group_by(models.Idea.id)
        .order_by(
            (
                func.count(case((models.Vote.value == VoteType.UP, 1)))
                - func.count(case((models.Vote.value == VoteType.DOWN, 1)))
            ).desc()
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    result = []
    for idea, up_votes, down_votes, abstain_votes in ideas_with_scores:
        idea_dict = schemas.Idea.model_validate(idea, from_attributes=True).model_dump()
        idea_dict["score"] = up_votes - down_votes  # Простой подсчёт: за минус против
        idea_dict["up_votes"] = up_votes
        idea_dict["down_votes"] = down_votes
        idea_dict["abstain_votes"] = abstain_votes
        result.append(schemas.IdeaWithScore(**idea_dict))

    return result
