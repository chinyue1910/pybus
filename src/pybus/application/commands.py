import uuid
from typing import Any, ClassVar, override

from pydantic import BaseModel, Field


class Command(BaseModel):
    _registry: ClassVar[dict[str, type["Command"]]] = {}

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    command_type: str = Field(init=False, title="命令類型")

    @override
    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "command_type", self.__class__.__name__)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._registry[cls.command_type] = cls

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "Command":
        target_cls = cls._registry.get(data["command_type"], cls)
        return target_cls.model_validate(data)
