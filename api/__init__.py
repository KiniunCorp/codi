"""FastAPI service package for CODI."""

from .server import AppConfig, app, create_app

__all__ = ["AppConfig", "app", "create_app"]
