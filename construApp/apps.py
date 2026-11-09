from django.apps import AppConfig


class ConstruappConfig(AppConfig):
    name = 'construApp'

    def ready(self):
        from . import signals  # noqa: F401
