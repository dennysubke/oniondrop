"""OnionDrop application package."""

__version__ = "0.2.0"
__all__ = ["create_app", "__version__"]


def create_app(*args, **kwargs):
    from .web import create_app as factory

    return factory(*args, **kwargs)
