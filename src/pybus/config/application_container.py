import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from logging import Logger
from typing import Any, TypeVar, overload

from celery import Celery
from dependency_injector import containers, providers

from ..application import ApplicationModule
from ..application.commands import Command
from ..application.queries import PaginationQuery, Query
from ..domain.events import DomainEvent
from ..domain.repositories import GenericRepository
from ..infrastructure.database.session import DataBaseSession
from ..infrastructure.logging import logger
from .transaction_container import DependencyProvider, TransactionContainer, TransactionContext

TResult = TypeVar("TResult")


def create_application(
    container: containers.DeclarativeContainer, modules: list[ApplicationModule]
) -> "Application":
    application = Application(name="pybus", container=container)

    for module in modules:
        application.include_module(module)

    @application.on_create_transaction_context
    def on_create_transaction_context() -> TransactionContext:  # pyright: ignore[reportUnusedFunction]
        return TransactionContext(
            DependencyProvider(
                TransactionContainer(
                    correlation_id=uuid.uuid4(),
                    session=container.database_session,
                    logger=logger,
                    celery_app=container.celery_app,
                )
            )
        )

    @application.on_enter_transaction_context
    async def on_enter_transaction_context(context: TransactionContext) -> None:  # pyright: ignore[reportUnusedFunction]
        context.set_dependency("publish_event", context.publish_event)

    @application.on_exit_transaction_context
    async def on_exit_transaction_context(  # pyright: ignore[reportUnusedFunction]
        context: TransactionContext, exc_val: BaseException | None
    ) -> None:
        session = context.get_dependency(DataBaseSession)
        if exc_val:
            session.rollback()
        else:
            session.commit()
        session.close()

    @application.transaction_middleware
    async def event_collector_middleware(  # pyright: ignore[reportUnusedFunction]
        context: TransactionContext, call_next: Callable[[], Awaitable[Any]]
    ) -> Any:
        result = await call_next()

        if isinstance(call_next, partial):
            repository_dependencies: list[GenericRepository[Any]] = [
                dependency
                for dependency in call_next.keywords.values()
                if isinstance(dependency, GenericRepository)
            ]

            domain_events = [
                domain_event
                for repository_dependency in repository_dependencies
                for domain_event in await repository_dependency.save_domain_events()
            ]

            for domain_event in domain_events:
                await context.publish_event(domain_event)

        return result

    return application


def create_celery_app() -> Celery:
    celery_app = Celery(name="pybus")
    celery_app.conf.update(broker_url="redis://redis:6379/0", result_backend="redis://redis:6379/0")
    celery_app.conf.update(timezone="Asia/Taipei", enable_utc=True)
    return celery_app


class ApplicationContainer(containers.DeclarativeContainer):
    application_modules: providers.Provider[list[ApplicationModule]] = providers.List()

    application: providers.Provider["Application"] = providers.Singleton(
        create_application, container=providers.Self(), modules=application_modules
    )

    celery_app: providers.Provider[Celery] = providers.Singleton(create_celery_app)

    database_session: providers.Provider[DataBaseSession] = providers.Dependency(
        instance_of=DataBaseSession
    )


class Application(ApplicationModule):
    def __init__(self, name: str, container: containers.Container):
        super().__init__(name=name)
        self._container: containers.Container = container
        self._on_create_transaction_context: Callable[[], TransactionContext] | None = None
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

    @overload
    async def execute(self, message: DomainEvent, pagination: None = None) -> None: ...

    async def execute(
        self,
        message: Command | Query[TResult] | DomainEvent,
        pagination: PaginationQuery | None = None,
    ) -> TResult | tuple[int, TResult] | None:
        async with self.transaction_context() as ctx:
            if isinstance(message, Command):
                return await ctx.execute_command(message)
            if isinstance(message, DomainEvent):
                return await ctx.execute_event(message)

            return await ctx.execute_query(message, pagination)

    def on_create_transaction_context(self, func: Callable[[], TransactionContext]):
        self._on_create_transaction_context = func
        return func

    def on_enter_transaction_context(self, func: Callable[[TransactionContext], Awaitable[None]]):
        self._on_enter_transaction_context = func
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
        if self._on_create_transaction_context:
            ctx = self._on_create_transaction_context()
        else:
            ctx = TransactionContext(
                DependencyProvider(
                    TransactionContainer(
                        correlation_id=uuid.uuid4(),
                        session=self._container.database_session,
                        logger=logger,
                        celery_app=self._container.celery_app,
                    )
                )
            )

        ctx.set_dependency(Logger, logger)
        ctx.configure(
            handlers_iterator=self.get_handlers,
            on_enter_transaction_context=self._on_enter_transaction_context,
            on_publish_scheduled_event=self._on_publish_scheduled_event,
            on_exit_transaction_context=self._on_exit_transaction_context,
            middlewares=self._transaction_middleware,
        )
        return ctx
