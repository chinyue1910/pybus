from typing import Self, override

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ..session import DataBaseSession
from .events import *  # noqa: F403


class SqlAlchemySession(DataBaseSession):
    def __init__(self, engine: Engine) -> None:
        self._engine: Engine = engine
        self._session: Session | None = None

    @property
    @override
    def connection(self) -> Session:
        if self._session:
            return self._session
        raise ValueError("Session is not initialized")

    @override
    def commit(self) -> None:
        if self._session:
            self._session.commit()

    @override
    def rollback(self) -> None:
        if self._session:
            self._session.rollback()

    @override
    def close(self) -> None:
        if self._session:
            self._session.close()

    @override
    def __aenter__(self) -> Self:
        self._session = Session(self._engine, expire_on_commit=False)
        return self
