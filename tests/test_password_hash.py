from app.crud.crud_users import create_user, verify_password
from app.models import User
from app.schemas import UserCreate


def test_password_stored_as_argon2id(db_session):
    user_data = UserCreate(
        username="alice", email="a@example.com", password="S3cureP@ss!"
    )
    user: User = create_user(db_session, user_data)

    assert user.hashed_password.startswith("$argon2id$")
    # Формат: $argon2id$v=19$m=262144,t=3,p=1$<salt>$<hash>
    parts = user.hashed_password.split("$")
    params = parts[3]
    assert "m=262144" in params
    assert "t=3" in params
    assert "p=1" in params


def test_long_password_not_truncated(db_session):
    password_long = "p" * 120  # пароль > 72 символов
    user_data = UserCreate(
        username="bob", email="b@example.com", password=password_long
    )
    user: User = create_user(db_session, user_data)

    assert verify_password(password_long, user.hashed_password)
    assert not verify_password("p" * 119, user.hashed_password)
