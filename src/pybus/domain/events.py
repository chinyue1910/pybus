import uuid
from typing import Any, ClassVar, override
from datetime import datetime

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    _registry: ClassVar[dict[str, type["DomainEvent"]]] = {}

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    correlation_id: uuid.UUID | None = Field(default=None, title="執行 ID")
    aggregate_id: uuid.UUID = Field(title="聚合根 ID")
    aggregate_type: str = Field(title="聚合根類型")
    event_type: str = Field(init=False, title="事件類型")
    occurred_on: datetime = Field(default_factory=datetime.now, title="事件發生時間")
    version: int | None = Field(default=None, title="事件版本")
    created_by_id: uuid.UUID | None = Field(default=None, title="創建者 ID")

    @override
    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "event_type", self.__class__.__name__)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._registry[cls.event_type] = cls

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "DomainEvent":
        target_cls = cls._registry.get(data["event_type"], cls)
        return target_cls.model_validate(data)

    @property
    def payload(self) -> dict[str, Any]:
        return self.model_dump(
            exclude={
                "id",
                "correlation_id",
                "aggregate_id",
                "aggregate_type",
                "event_type",
                "occurred_on",
                "version",
                "created_by_id",
            }
        )
