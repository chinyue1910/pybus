import inspect
from collections.abc import Awaitable, Callable, Generator
from contextlib import AsyncExitStack
from functools import partial
from logging import Logger
from types import TracebackType, UnionType
from typing import Annotated, Any, TypeVar, cast, get_args, get_origin, overload
from dependency_injector import containers
from dependency_injector.wiring import inject, Provide
from ..config.container import Container
import uuid

from celery import Celery

from ..application import ApplicationModule
from ..application.commands import Command
from ..application.queries import PaginationQuery, Query
from ..domain.events import DomainEvent
from ..infrastructure.logging import logger

TResult = TypeVar("TResult")
TDependency = TypeVar("TDependency")


class DependencyOverridesProvider:
    def __init__(self, overrides: dict[Callable[..., Any], Callable[..., Any]]) -> None:
        self.dependency_overrides: dict[Callable[..., Any], Callable[..., Any]] = overrides


class TransactionContext:
    def __init__(
        self,
        handlers_iterator: Callable[
            [Command | Query[Any] | DomainEvent],
            Generator[Callable[..., Awaitable[Any]], None, None],
        ],
        container: containers.Container,
    ):
        self._handlers_iterator: Callable[
            [Command | Query[Any] | DomainEvent],
            Generator[Callable[..., Awaitable[Any]], None, None],
        ] = handlers_iterator
        self._container: containers.Container = container

        self.correlation_id: uuid.UUID = uuid.uuid4()
        self.metadata: dict[str, Any] = {}

        self._solved_dependencies: dict[type | str, Any] = {}
        self._dependency_cache: dict[tuple[Callable[..., Any], tuple[str]], Any] = {}
        self._on_enter_transaction_context: (
            Callable[["TransactionContext"], Awaitable[None]] | None
        ) = None
        self._on_publish_scheduled_event: Callable[[DomainEvent], Awaitable[None]] | None = None
        self._on_exit_transaction_context: (
            Callable[["TransactionContext", BaseException | None], Awaitable[None]] | None
        ) = None
        self._middlewares: list[
            Callable[["TransactionContext", Callable[[], Awaitable[Any]]], Awaitable[Any]]
        ] = []

    def configure(
        self,
        on_enter_transaction_context: Callable[["TransactionContext"], Awaitable[None]]
        | None = None,
        on_publish_scheduled_event: Callable[[DomainEvent], Awaitable[None]] | None = None,
        on_exit_transaction_context: Callable[
            ["TransactionContext", BaseException | None], Awaitable[None]
        ]
        | None = None,
        middlewares: list[
            Callable[["TransactionContext", Callable[[], Awaitable[Any]]], Awaitable[Any]]
        ]
        | None = None,
    ) -> None:
        self._on_enter_transaction_context = on_enter_transaction_context
        self._on_publish_scheduled_event = on_publish_scheduled_event
        self._on_exit_transaction_context = on_exit_transaction_context
        self._middlewares = middlewares or []

    def set_dependency(self, key: type[TDependency] | str, value: TDependency) -> None:
        self._solved_dependencies[key] = value

    def get_dependency(self, key: type[TDependency] | str) -> TDependency:
        return self._solved_dependencies[key]

    async def __aenter__(self) -> "TransactionContext":
        if self._on_enter_transaction_context:
            await self._on_enter_transaction_context(self)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._on_exit_transaction_context:
            await self._on_exit_transaction_context(self, exc_val)

    async def _proxy_handler_dependency(
        self,
        handler: Callable[..., Awaitable[TResult | tuple[int, TResult]]]
        | Callable[..., Awaitable[None]],
    ):
        sinature = inspect.signature(handler)
        new_params: list[inspect.Parameter] = []
        for param in sinature.parameters.values():
            if param.annotation in self._dependencies:
                new_param = param.replace(annotation=self._dependencies[param.annotation])
                new_params.append(new_param)

        forced_session_param = inspect.Parameter(
            name="__forced_session",
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=Annotated[DataBaseSession, Depends(get_generic_session)],
        )

        if "__forced_session" not in [p.name for p in new_params]:
            new_params.append(forced_session_param)

        new_sinature = sinature.replace(parameters=new_params)

        async def proxy(*args: object, **kwargs: object) -> TResult | tuple[int, TResult] | None:
            return await handler(*args, **kwargs)

        proxy.__signature__ = new_sinature  # pyright: ignore[reportFunctionMemberAccess]
        return proxy

    async def _resolve_parameters(
        self,
        handler: Callable[..., Awaitable[TResult]]
        | Callable[..., Awaitable[tuple[int, TResult]]]
        | Callable[..., Awaitable[None]],
        message: Command | Query[TResult] | DomainEvent,
        pagination: PaginationQuery | None = None,
    ) -> dict[str, object]:
        proxy_handler = await self._proxy_handler_dependency(handler)
        dependant: Dependant = get_dependant(path="message", call=proxy_handler)
        if dependant.call is None or not callable(dependant.call):
            raise HTTPException(
                detail=f"Handler {proxy_handler} is not callable",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        async with AsyncExitStack() as stack:
            solved_result = await solve_dependencies(
                request=self.active_request,
                dependant=dependant,
                dependency_overrides_provider=self._dependency_overrides_provider,
                dependency_cache=self._dependency_cache,
                async_exit_stack=stack,
                embed_body_fields=True,
            )

            if len(solved_result.errors) > 0:
                error_details = "\n".join([str(error) for error in solved_result.errors])
                logger.info(f"Dependency resolution errors: {error_details}")

            self._dependency_cache = solved_result.dependency_cache

            if "__forced_session" in solved_result.values:
                database_session = cast(DataBaseSession, solved_result.values["__forced_session"])
                database_session.connection.info["user_id"] = (
                    getattr(self.active_request.state, "current_user_id")
                    if hasattr(self.active_request.state, "current_user_id")
                    else None
                )
                self._solved_dependencies[DataBaseSession] = database_session

            sinature = inspect.signature(handler)
            parameters: dict[str, object] = {}
            for name, param in sinature.parameters.items():
                annotation = param.annotation

                if annotation == inspect.Parameter.empty:
                    continue

                if get_origin(annotation) is UnionType and any(
                    issubclass(arg, PaginationQuery) for arg in get_args(annotation)
                ):
                    parameters[name] = pagination
                    continue

                if isinstance(annotation, type) and issubclass(
                    annotation, (Command, Query, DomainEvent)
                ):
                    parameters[name] = message
                    continue

                if annotation in self._solved_dependencies:
                    parameters[name] = self._solved_dependencies[annotation]
                    continue

                if name in self._solved_dependencies:
                    parameters[name] = self._solved_dependencies[name]
                    continue

                if name in solved_result.values:
                    parameters[name] = solved_result.values[name]
                    continue

            return parameters

    @overload
    async def call(
        self,
        handler: Callable[..., Awaitable[None]],
        message: Command,
        pagination: None = None,
    ) -> None: ...

    @overload
    async def call(
        self,
        handler: Callable[..., Awaitable[TResult]],
        message: Query[TResult],
        pagination: None = None,
    ) -> TResult: ...

    @overload
    async def call(
        self,
        handler: Callable[..., Awaitable[tuple[int, TResult]]],
        message: Query[TResult],
        pagination: PaginationQuery,
    ) -> tuple[int, TResult]: ...

    @overload
    async def call(
        self,
        handler: Callable[..., Awaitable[None]],
        message: DomainEvent,
        pagination: None = None,
    ) -> None: ...

    async def call(
        self,
        handler: Callable[..., Awaitable[None]]
        | Callable[..., Awaitable[TResult]]
        | Callable[..., Awaitable[tuple[int, TResult]]],
        message: Command | Query[TResult] | DomainEvent,
        pagination: PaginationQuery | None = None,
    ) -> TResult | tuple[int, TResult] | None:
        parameters = await self._resolve_parameters(handler, message, pagination)

        call_next = partial(handler, **parameters)

        for middleware in self._middlewares:
            call_next = partial(middleware, self, call_next)

        return await call_next()

    async def execute_command(self, command: Command) -> None:
        try:
            for handler in self._handlers_iterator(command):
                return await self.call(handler, command)
        except Exception as ex:
            logger.error(f"Executing command {command} failed with error: {ex}")
            raise

        raise Exception(f"No handler found for command: {command}")

    @overload
    async def execute_query(self, query: Query[TResult], pagination: None = None) -> TResult: ...

    @overload
    async def execute_query(
        self, query: Query[TResult], pagination: PaginationQuery
    ) -> tuple[int, TResult]: ...

    async def execute_query(
        self,
        query: Query[TResult],
        pagination: PaginationQuery | None = None,
    ) -> TResult | tuple[int, TResult]:
        try:
            for handler in self._handlers_iterator(query):
                return await self.call(handler, query, pagination)
        except Exception as ex:
            logger.error(f"Executing query {query} failed with error: {ex}")
            raise

        raise Exception(f"No handler found for query: {query}")

    @inject
    async def publish_event(
        self, message: DomainEvent, celery_app: Celery = Provide[Container.celery_app]
    ) -> None:
        message.correlation_id = self.correlation_id

        _ = celery_app.send_task(
            name="ddd_bridge_task",
            kwargs={
                **message.model_dump(
                    include={
                        "id",
                        "correlation_id",
                        "aggregate_id",
                        "aggregate_type",
                        "event_type",
                        "occurred_on",
                        "version",
                        "created_by_id",
                    }
                ),
                **message.payload,
            },
        )

        try:
            for handler in self._handlers_iterator(message):
                await self.call(handler, message)
        except Exception as ex:
            logger.error(f"Publishing event {message} failed with error: {ex}")
            raise


class Application(ApplicationModule):
    def __init__(self, name: str, container: containers.Container):
        super().__init__(name=name)
        self._container: containers.Container = container
        self._on_enter_transaction_context: (
            Callable[[TransactionContext], Awaitable[None]] | None
        ) = None
        self._on_publish_scheduled_event: Callable[[DomainEvent], Awaitable[None]] | None = None
        self._on_exit_transaction_context: (
            Callable[[TransactionContext, BaseException | None], Awaitable[None]] | None
        ) = None
        self._transaction_middleware: list[
            Callable[[TransactionContext, Callable[[], Awaitable[Any]]], Awaitable[Any]]
        ] = []

    @overload
    async def execute(self, message: Command, pagination: None = None) -> None: ...

    @overload
    async def execute(self, message: Query[TResult], pagination: None = None) -> Any: ...

    @overload
    async def execute(
        self, message: Query[TResult], pagination: PaginationQuery
    ) -> tuple[int, TResult]: ...

    async def execute(
        self,
        message: Command | Query[TResult],
        pagination: PaginationQuery | None = None,
    ) -> TResult | tuple[int, TResult] | None:
        async with self.transaction_context() as ctx:
            if isinstance(message, Command):
                return await ctx.execute_command(message)

            return await ctx.execute_query(message, pagination)

    def on_enter_transaction_context(self, func: Callable[[TransactionContext], Awaitable[None]]):
        self._on_enter_transaction_context = func
        return func

    def on_publish_scheduled_event(self, func: Callable[[DomainEvent], Awaitable[None]] | None):
        if func is None:
            self._on_publish_scheduled_event = None
            return None

        self._on_publish_scheduled_event = func
        return func

    def on_exit_transaction_context(
        self, func: Callable[[TransactionContext, BaseException | None], Awaitable[None]]
    ):
        self._on_exit_transaction_context = func
        return func

    def transaction_middleware(
        self,
        func: Callable[[TransactionContext, Callable[[], Awaitable[Any]]], Awaitable[Any]],
    ):
        self._transaction_middleware.append(func)
        return func

    def transaction_context(self) -> TransactionContext:
        ctx = TransactionContext(handlers_iterator=self.get_handlers, container=self._container)
        ctx.set_dependency(Logger, logger)
        ctx.configure(
            on_enter_transaction_context=self._on_enter_transaction_context,
            on_publish_scheduled_event=self._on_publish_scheduled_event,
            on_exit_transaction_context=self._on_exit_transaction_context,
            middlewares=self._transaction_middleware,
        )
        return ctx
