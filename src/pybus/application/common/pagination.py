from pydantic import BaseModel, Field


class PaginationQuery(BaseModel):
    page: int = Field(default=1)
    size: int = Field(default=10)
