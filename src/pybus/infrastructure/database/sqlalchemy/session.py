from typing import override

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ..session import DataBaseSession
from .events import *  # noqa: F403


class SqlAlchemySession(DataBaseSession):
    def __init__(self, engine: Engine) -> None:
        self._engine: Engine = engine
        self._session: Session = Session(self._engine, expire_on_commit=False)

    @property
    @override
    def connection(self) -> Session:
        return self._session

    @override
    def commit(self) -> None:
        self._session.commit()

    @override
    def rollback(self) -> None:
        self._session.rollback()

    @override
    def close(self) -> None:
        self._session.close()
