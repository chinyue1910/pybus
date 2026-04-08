from datetime import datetime
from typing import cast
from sqlalchemy import event, true, DDL, Connection
from sqlalchemy.orm import ORMExecuteState, with_loader_criteria, Session
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.schema import SchemaItem

from .mixins import OperationMixin, SoftDeleteMixin
from .base import Base


@event.listens_for(Base.metadata, "before_create")
def before_create(target: SchemaItem, connection: Connection, **kw: object):  # pyright: ignore[reportUnusedParameter]
    if connection.dialect.name == "postgresql":
        pg_trgm_ddl = DDL("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        _ = connection.execute(pg_trgm_ddl)


@event.listens_for(Session, "before_flush", propagate=True)
def before_flush(session: Session, flush_context, instances):  # pyright: ignore[reportUnusedParameter, reportUnknownParameterType, reportMissingParameterType]
    for obj in session.deleted:
        if isinstance(obj, SoftDeleteMixin):
            session.expunge(obj)
            obj.deleted_at = datetime.now()
            session.add(obj)

    for obj in session.new:
        if isinstance(obj, OperationMixin):
            user_id = session.info.get("user_id", None)
            obj.created_by_id = user_id if user_id else obj.created_by_id
            obj.updated_by_id = user_id if user_id else obj.updated_by_id

    for obj in session.dirty:
        if isinstance(obj, OperationMixin):
            user_id = session.info.get("user_id", None)
            obj.updated_by_id = user_id if user_id else obj.updated_by_id


@event.listens_for(Session, "do_orm_execute")
def do_orm_execute(orm_execute_state: ORMExecuteState):
    skip_filter = cast(bool, orm_execute_state.execution_options.get("skip_filter", False))

    def _soft_delete_criteria(cls: type) -> ColumnElement[bool]:
        if hasattr(cls, "deleted_at"):
            return getattr(cls, "deleted_at").is_(None)
        return true()

    if orm_execute_state.is_select and not skip_filter:
        orm_execute_state.statement = orm_execute_state.statement.options(
            with_loader_criteria(
                entity_or_base=SoftDeleteMixin,
                where_criteria=_soft_delete_criteria,
                include_aliases=True,
                propagate_to_loaders=True,
            ),
        )
