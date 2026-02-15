from django.apps import AppConfig


class ShopConfig(AppConfig):
    name = 'shop'
    def ready(self):
        # import signal handlers
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
