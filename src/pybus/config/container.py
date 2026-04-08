from celery import Celery
from dependency_injector import containers, providers

from ..application import ApplicationModule
from ..infrastructure import Application


def create_application(container: containers.DeclarativeContainer) -> ApplicationModule:
    return Application(name="pybus", container=container)


def create_celery_app() -> Celery:
    celery_app = Celery(name="pybus")
    celery_app.conf.update(broker_url="redis://redis:6379/0", result_backend="redis://redis:6379/0")
    celery_app.conf.update(timezone="Asia/Taipei", enable_utc=True)
    return celery_app


class Container(containers.DeclarativeContainer):
    application: providers.Provider[ApplicationModule] = providers.Singleton(
        create_application, container=providers.Self()
    )

    celery_app: providers.Provider[Celery] = providers.Singleton(create_celery_app)
