import uuid
from typing import overload, override

from pybus.domain.entities import AggregateRoot, Entity
from pybus.domain.events import DomainEvent
from pybus.domain.repositories import GenericRepository


class InMemoryRepository(GenericRepository[Entity]):
    def __init__(self) -> None:
        self.objects: dict[uuid.UUID, Entity] = {}

    @override
    async def get_by_id(self, entity_id: uuid.UUID, skip_filter: bool = False) -> Entity | None:
        return self.objects.get(entity_id, None)

    @override
    async def get_by_ids(
        self, entity_ids: list[uuid.UUID], skip_filter: bool = False
    ) -> list[Entity]:
        return [self.objects[entity_id] for entity_id in entity_ids if entity_id in self.objects]

    @overload
    async def get_all(
        self, page: None = None, size: None = None, skip_filter: bool = False
    ) -> list[Entity]: ...

    @overload
    async def get_all(
        self, page: int = 1, size: int = 10, skip_filter: bool = False
    ) -> tuple[int, list[Entity]]: ...

    @override
    async def get_all(
        self, page: int | None = None, size: int | None = None, skip_filter: bool = False
    ) -> list[Entity] | tuple[int, list[Entity]]:
        items = list(self.objects.values())
        if page is not None and size is not None:
            start = (page - 1) * size
            end = start + size
            return (len(items), items[start:end])

        return items

    @override
    async def get_event_history(self, entity_id: uuid.UUID) -> list[DomainEvent]:
        entity = self.objects.get(entity_id, None)
        if entity is not None and isinstance(entity, AggregateRoot):
            return [event for event in entity.collect_events()]
        return []

    @override
    async def add(self, entity: Entity):
        self.objects[entity.id] = entity

    @override
    async def persist(self, entity: Entity): ...

    @override
    async def persist_all(self): ...

    @override
    async def collect_events(self) -> list[DomainEvent]:
        return [
            event
            for entity in self.objects.values()
            if isinstance(entity, AggregateRoot)
            for event in entity.collect_events()
        ]

    @override
    async def remove(self, entity: Entity):
        del self.objects[entity.id]

    @override
    async def restore(self, entity: Entity):
        self.objects[entity.id] = entity

    @override
    async def save_domain_events(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for entity in self.objects.values():
            if isinstance(entity, AggregateRoot):
                events.extend(entity.collect_events())
        return events
