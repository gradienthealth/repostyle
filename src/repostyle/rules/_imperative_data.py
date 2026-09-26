"""Imperative verb data used by the docstring summary rule."""

import tomllib
from importlib.resources import files


def _load_verbs() -> tuple[str, ...]:
    """Loads the bundled imperative-verb vocabulary."""
    resource = files("repostyle.rules").joinpath("imperative-verbs.toml")
    with resource.open("rb") as vocabulary_file:
        value = tomllib.load(vocabulary_file).get("verbs")
    if not isinstance(value, list) or not all(isinstance(verb, str) for verb in value):
        raise TypeError("imperative verb vocabulary must contain a string array")
    if len(value) != len(set(value)):
        raise ValueError("imperative verb vocabulary contains duplicates")
    return tuple(value)


IMPERATIVE_VERBS = _load_verbs()
_IRREGULAR_CONJUGATIONS: dict[str, str] = {"Have": "Has"}
_ES_CONJUGATION_SUFFIXES = ("s", "x", "z", "ch", "sh", "o")
