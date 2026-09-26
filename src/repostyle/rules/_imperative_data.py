"""Imperative verb data used by the docstring summary rule."""

from repostyle.rules._imperative_verbs_a_m import VERBS as _VERBS_A_M
from repostyle.rules._imperative_verbs_n_z import VERBS as _VERBS_N_Z

IMPERATIVE_VERBS: tuple[str, ...] = _VERBS_A_M + _VERBS_N_Z
_IRREGULAR_CONJUGATIONS: dict[str, str] = {"Have": "Has"}
_ES_CONJUGATION_SUFFIXES = ("s", "x", "z", "ch", "sh", "o")
