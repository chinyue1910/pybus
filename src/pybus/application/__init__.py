from collections import defaultdict
from collections.abc import AsyncGenerator, Awaitable, Generator
from typing import Any, Callable, TypeVar, overload

from ..domain.events import DomainEvent
from .commands import Command
from .queries import Query

TResult = TypeVar("TResult")
TInterface = TypeVar("TInterface")


class ApplicationModule:
    def __init__(self, name: str):
        self.name: str = name
        self._handlers: dict[
            type[Command | DomainEvent | Query[Any]],
            set[Callable[..., Awaitable[None] | Awaitable[Any]]],
        ] = defaultdict(set)
        self._sub_modules: set["ApplicationModule"] = set()
        self._dependencies: dict[
            type[Any], Callable[..., Awaitable[Any] | AsyncGenerator[Any]]
        ] = {}

    def include_module(self, module: "ApplicationModule"):
        self._sub_modules.add(module)

    def register_dependency(self, interface: type[TInterface]):
        def decorator(
            func: Callable[..., Awaitable[TInterface] | AsyncGenerator[TInterface]],
        ):
            self._dependencies[interface] = func
            return func

        return decorator

    def register_handler(self, message_type: type[Command | DomainEvent | Query[TResult]]):
        def decorator(
            func: Callable[..., Awaitable[None] | Awaitable[TResult]],
        ):
            self._handlers[message_type].add(func)
            return func

        return decorator

    @overload
    def _iterate_handlers(
        self, message: Command
    ) -> Generator[Callable[..., Awaitable[None]], None, None]: ...

    @overload
    def _iterate_handlers(
        self, message: Query[TResult]
    ) -> Generator[Callable[..., Awaitable[TResult]], None, None]: ...

    @overload
    def _iterate_handlers(
        self, message: DomainEvent
    ) -> Generator[Callable[..., Awaitable[None]], None, None]: ...

    def _iterate_handlers(
        self, message: Command | Query[TResult] | DomainEvent
    ) -> Generator[
        Callable[..., Awaitable[None]] | Callable[..., Awaitable[TResult]],
        None,
        None,
    ]:
        if type(message) in self._handlers:
            yield from self._handlers[type(message)]

        for sub_module in self._sub_modules:
            yield from sub_module._iterate_handlers(message)

    def get_handlers(
        self, message: Command | DomainEvent | Query[TResult]
    ) -> Generator[Callable[..., Awaitable[None]] | Callable[..., Awaitable[TResult]], None, None]:
        return self._iterate_handlers(message)
