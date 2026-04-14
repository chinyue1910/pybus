import uuid

from pydantic import BaseModel, Field


class Query[TResult](BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
