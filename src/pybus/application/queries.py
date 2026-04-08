import uuid
from typing import TypeVar

from pydantic import BaseModel, Field

TResult = TypeVar("TResult")


class Query[TResult](BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)


class PaginationQuery(BaseModel):
    page: int = Field(default=1)
    size: int = Field(default=10)
