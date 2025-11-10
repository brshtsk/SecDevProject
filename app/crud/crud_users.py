from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models, schemas


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    # Argon2: t=3, m=256MB, p=1
    argon2__type="ID",
    argon2__time_cost=3,
    argon2__memory_cost=262144,
    argon2__parallelism=1,
)


def create_user(db: Session, user: schemas.UserCreate):
    password = user.password or ""
    hashed_password = pwd_context.hash(password)
    db_user = models.User(
        username=user.username, email=user.email, hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(db: Session, user_id: int, password: str):
    user = get_user(db, user_id)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user
