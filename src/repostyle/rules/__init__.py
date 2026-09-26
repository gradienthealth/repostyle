"""Repo-style lint rules not covered by off-the-shelf tools.

The package resolves its broad compatibility API lazily. Rule implementations
stay in focused modules while existing imports from `repostyle.rules` continue
to work.
"""

from importlib import import_module

from repostyle.rules._exports import EXPORT_MODULES, EXPORTED_NAMES

__all__ = EXPORTED_NAMES


def __getattr__(name: str) -> object:
    """Loads and caches a public rule symbol from its owning module."""
    module_name = EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Lists the package's lazy public API alongside its loaded globals."""
    return sorted(set(globals()) | set(__all__))
