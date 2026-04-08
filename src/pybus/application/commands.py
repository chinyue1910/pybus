import uuid
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class Command(BaseModel):
    _registry: ClassVar[dict[str, type["Command"]]] = {}

    id: uuid.UUID = Field(default_factory=uuid.uuid4)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._registry[cls.__name__] = cls

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "Command":
        target_cls = cls._registry.get(cls.__name__, cls)
        return target_cls.model_validate(data)
