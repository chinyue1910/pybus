from typing import Any, ClassVar, override

from pydantic import BaseModel, ConfigDict, Field


class ValueObject(BaseModel):
    _registry: ClassVar[dict[str, type["ValueObject"]]] = {}

    value_type: str = Field(init=False, title="值對象類型")

    @override
    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "value_type", self.__class__.__name__)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._registry[cls.value_type] = cls

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "ValueObject":
        target_cls = cls._registry.get(data["value_type"], cls)
        return target_cls.model_validate(data)

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
