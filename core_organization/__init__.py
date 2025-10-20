from .handler import handler

from importlib.metadata import version

__version__ = version("sck-core-organization")

__all__ = ["handler"]
