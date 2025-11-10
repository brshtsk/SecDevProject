from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user
from app.crud import crud_ideas
from app.database import get_db
from app.http_client import SafeHttpClient, injected_get_http_client

router = APIRouter(tags=["ideas"])

# Валидация / нормализация
_MAX_TITLE_LEN = 120
_MAX_DESC_LEN = 2000
_MIN_TITLE_LEN = 3


def _clean_str(v: str) -> str:
    v = v.strip()
    # Схлопываем подряд идущие пробелы
    v = " ".join(v.split())
    return v


def _validate_idea_input(idea):
    # title
    title = _clean_str(idea.title)
    if len(title) < _MIN_TITLE_LEN or len(title) > _MAX_TITLE_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Длина title должна быть от {_MIN_TITLE_LEN} до {_MAX_TITLE_LEN} символов",
        )
    # description
    desc = _clean_str(idea.description)
    if len(desc) > _MAX_DESC_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Длина description не более {_MAX_DESC_LEN} символов",
        )
    # Перезаписываем нормализованные значения
    idea.title = title
    idea.description = desc
    return idea


@router.get("/ideas", response_model=List[schemas.IdeaWithScore])
def read_ideas_with_scores(
    skip: int = Query(0, ge=0, le=1000),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Получение списка идей с рейтингом"""
    return crud_ideas.get_ideas_with_scores(db, skip=skip, limit=limit)


@router.get("/ideas/{idea_id}", response_model=schemas.Idea)
def read_idea(idea_id: int, db: Session = Depends(get_db)):
    """Получение конкретной идеи по ID"""
    db_idea = crud_ideas.get_idea(db, idea_id=idea_id)
    if db_idea is None:
        raise HTTPException(status_code=404, detail="Идея не найдена")
    return db_idea


@router.post("/ideas", response_model=schemas.Idea, status_code=status.HTTP_201_CREATED)
def create_idea(
    idea: schemas.IdeaCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    idea = _validate_idea_input(idea)
    """Создание новой идеи"""
    return crud_ideas.create_idea(db=db, idea=idea, owner_id=current_user.id)


@router.put("/ideas/{idea_id}", response_model=schemas.Idea)
def update_idea(
    idea_id: int,
    idea: schemas.IdeaCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    idea = _validate_idea_input(idea)
    """Обновление существующей идеи"""
    db_idea = crud_ideas.update_idea(
        db, idea_id=idea_id, idea=idea, current_user_id=current_user.id
    )
    if db_idea is None:
        raise HTTPException(
            status_code=404, detail="Идея не найдена или вы не владелец"
        )
    return db_idea


@router.delete("/ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_idea(
    idea_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Удаление идеи"""
    success = crud_ideas.delete_idea(
        db, idea_id=idea_id, current_user_id=current_user.id
    )
    if not success:
        raise HTTPException(
            status_code=404, detail="Идея не найдена или вы не владелец"
        )


@router.post("/ideas/{idea_id}/vote", response_model=dict)
def vote_for_idea(
    idea_id: int,
    vote: schemas.VoteCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Голосование за идею. Варианты: 'за', 'против', 'воздержаться'."""
    db_idea = crud_ideas.get_idea(db, idea_id=idea_id)
    if db_idea is None:
        raise HTTPException(status_code=404, detail="Идея не найдена")

    crud_ideas.vote_idea(
        db=db, idea_id=idea_id, user_id=current_user.id, vote_value=vote.value
    )
    return {"status": "success", "message": f"Голос '{vote.value.value}' учтен"}


@router.get("/external/ping")
async def external_ping(
    url: str = Query(..., description="Полный URL для проверки"),
    client: SafeHttpClient = Depends(injected_get_http_client),
):
    """
    Демонстрационный вызов безопасного HTTP‑клиента.
    Возвращает статус и первые байты тела.
    """
    try:
        resp = await client.request("GET", url, headers={"Accept": "text/plain"})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка внешнего запроса: {e}")
    text_snippet = resp.text[:200] if resp.text else ""
    return {
        "url": url,
        "status_code": resp.status_code,
        "snippet": text_snippet,
        "length": len(resp.content),
    }
