"""Typed readers for values in the repostyle configuration table."""


def string_list(table: dict[str, object], key: str) -> tuple[str, ...]:
    """Returns the nonempty strings configured under `key`."""
    configured = table.get(key, ())
    if isinstance(configured, str):
        configured = (configured,)
    if not isinstance(configured, list | tuple):
        return ()
    return tuple(str(item) for item in configured if str(item))
