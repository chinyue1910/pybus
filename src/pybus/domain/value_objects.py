from typing import Any, BinaryIO, ClassVar, override

from pydantic import BaseModel, ConfigDict, Field


class ValueObject(BaseModel):
    _registry: ClassVar[dict[str, type["ValueObject"]]] = {}

    value_type: str = Field(init=False, description="值對象類型")

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


class FileObject(ValueObject):
    filename: str
    content_type: str
    size: int
    stream: BinaryIO

    def to_bytes(self) -> bytes:
        _ = self.stream.seek(0)
        return self.stream.read()

    def __post_init__(self):
        if self.size > 2 * 1024 * 1024:
            raise ValueError("File size exceeds the maximum limit of 2MB")
