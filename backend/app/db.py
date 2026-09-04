from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

_settings = get_settings()
_engine = create_engine(
    _settings.database_url or f"sqlite:///{_settings.db_path()}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    # Import models so their tables are registered on SQLModel.metadata before create_all.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(_engine)


def get_session() -> Generator[Session, None, None]:
    with Session(_engine) as session:
        yield session


def new_session() -> Session:
    """For code that runs outside a request (background render threads): the request-
    scoped session from get_session() is closed once the HTTP response returns, so a
    background job needs its own session with its own lifetime."""
    return Session(_engine)
