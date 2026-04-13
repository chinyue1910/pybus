import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field, PrivateAttr

from .mixins import BusinessRuleValidationMixin

if TYPE_CHECKING:
    from .events import DomainEvent


class Entity(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)


class AggregateRoot(Entity, BusinessRuleValidationMixin, ABC):
    _version: int = PrivateAttr(default=0)
    _events: list["DomainEvent"] = PrivateAttr(default_factory=list)

    def register_event(self, event: "DomainEvent"):
        self._events.append(event)

    def collect_events(self) -> list["DomainEvent"]:
        events = self._events[:]
        self._events.clear()
        return events

    @classmethod
    def rebuild(cls, events: list["DomainEvent"]) -> Self:
        self = object.__new__(cls)
        cls.__init__(self)
        self.load(events)
        return self

    def load(self, events: list["DomainEvent"]):
        for event in events:
            self.apply(event)
            self._version += 1

    @abstractmethod
    def apply(self, event: "DomainEvent"):
        pass
