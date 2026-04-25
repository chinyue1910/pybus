import uuid
from typing import Any

from pydantic import BaseModel, Field


class Query[TResult: Any](BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
