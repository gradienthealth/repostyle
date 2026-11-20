"""Plumbing rules: one setting forced through many files.

RS073 flags a layer class that builds a first-party collaborator out of its own
forwarded constructor parameters, or builds one that takes a port, so every
setting the collaborator needs is re-declared on each class above it. RS074
flags one first-party class constructed in two modules from the same long run
of `keyword=value` pairs, so a new setting has to be threaded through both.
Both are whole-package rules that resolve a call to the class it constructs
through the shared index in `_class_index`.
"""

from __future__ import annotations

import ast
import itertools
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from repostyle._shared import (
    _relative_to_pyproject,
    _repostyle_table,
    _string_list,
    find_config_file,
)
from repostyle.rules._class_index import (
    ClassFacts,
    PackageIndex,
    build_index,
    methods,
)
from repostyle.rules._forwarding import ForwardingAnalysis
from repostyle.rules._violation import (
    RS_FORWARDED_COLLABORATOR,
    RS_PARALLEL_CONSTRUCTION,
    Violation,
)

COLLABORATOR_LAYER_GLOBS_KEY = "collaborator-layer-globs"
DEFAULT_COLLABORATOR_LAYER_GLOBS: tuple[str, ...] = ("*/application/**", "*/domain/**")
PARALLEL_CONSTRUCTION_MIN_PAIRS_KEY = "parallel-construction-min-pairs"
DEFAULT_PARALLEL_CONSTRUCTION_MIN_PAIRS = 8
_MIN_FORWARDED_PARAMS = 2
_LISTED_NAMES = 6


def check_forwarded_collaborator(
    files: Sequence[tuple[Path, str]],
) -> Iterator[tuple[Path, Violation]]:
    """Flags a layer class that builds a collaborator it should be handed.

    A class under the `collaborator-layer-globs` paths (default
    `*/application/**` and `*/domain/**`) fires when it constructs a
    first-party class from another module and either of these holds:

    - Two or more parameters of its own `__init__` are used only to be passed
      unchanged, directly or through the `self` attribute they are stored on,
      into that one class's constructor.
    - That class's constructor takes a port, a first-party `Protocol`.

    Such a class re-declares its collaborator's settings and defaults, so a new
    setting is threaded through every class above the one that reads it. The
    collaborator belongs in the constructor, built once by the composition
    root. A class fires once, naming the collaborator with the most forwarded
    parameters. Callees resolve by simple name and an ambiguous name is
    skipped, so the rule under- rather than over-reports.
    """
    if not files:
        return
    analysis = ForwardingAnalysis(build_index(files))
    table = _repostyle_table(find_config_file(files[0][0]))
    globs = _string_list(table, COLLABORATOR_LAYER_GLOBS_KEY) or (
        DEFAULT_COLLABORATOR_LAYER_GLOBS
    )
    for facts in analysis.index.classes.values():
        relative = _relative_to_pyproject(facts.path, find_config_file(facts.path))
        if not any(fnmatch(relative, glob) for glob in globs):
            continue
        if built := _built_collaborators(facts, analysis):
            yield facts.path, _collaborator_violation(facts, built, analysis)


def check_parallel_construction(
    files: Sequence[tuple[Path, str]],
) -> Iterator[tuple[Path, Violation]]:
    """Flags one class constructed in two modules from the same settings.

    A call fires when another non-test module constructs the same resolvable
    first-party class from at least `parallel-construction-min-pairs` identical
    `keyword=value` pairs, eight by default. Two copies of one long
    construction drift apart as settings are added, so the construction belongs
    in one builder both callers use. Test modules are exempt.
    """
    if not files:
        return
    index = build_index(files)
    table = _repostyle_table(find_config_file(files[0][0]))
    configured = table.get(PARALLEL_CONSTRUCTION_MIN_PAIRS_KEY)
    min_pairs = (
        configured
        if isinstance(configured, int) and configured > 0
        else DEFAULT_PARALLEL_CONSTRUCTION_MIN_PAIRS
    )
    sites = _construction_sites(index, min_pairs)
    by_target: dict[str, list[_ConstructionSite]] = {}
    for site in sites:
        by_target.setdefault(site.target, []).append(site)
    for group in by_target.values():
        for site, other in itertools.permutations(group, 2):
            shared = len(site.pairs & other.pairs)
            if site.path != other.path and shared >= min_pairs:
                site.record_partner(other, shared)
    for site in sites:
        if site.best is not None:
            yield site.path, site.violation()


@dataclass
class _BuiltCollaborator:
    """One first-party class a layer class constructs, and why it fires."""

    target: ClassFacts
    """The constructed class."""
    methods: set[str] = field(default_factory=set)
    """The methods holding the constructor calls."""
    params: list[str] = field(default_factory=list)
    """The constructor parameters forwarded only into the call."""
    ports: list[str] = field(default_factory=list)
    """The ports the constructed class's constructor takes."""


@dataclass
class _ConstructionSite:
    """One keyword-heavy constructor call of a resolvable first-party class."""

    path: Path
    """The module holding the call."""
    relative: str
    """That module's config-relative path."""
    call: ast.Call
    """The constructor call."""
    target: str
    """The constructed class."""
    pairs: frozenset[tuple[str, str]]
    """The call's `keyword=value` pairs, each value as its AST dump."""
    best: tuple[_ConstructionSite, int] | None = None
    """The other module's call sharing the most pairs, and that count."""

    def record_partner(self, other: _ConstructionSite, shared: int) -> None:
        """Records `other` as the best match when it shares more pairs."""
        if self.best is None or shared > self.best[1]:
            self.best = (other, shared)

    def violation(self) -> Violation:
        """Builds the finding, reported on this call."""
        assert self.best is not None
        other, shared = self.best
        return Violation(
            self.call.lineno,
            self.call.col_offset + 1,
            RS_PARALLEL_CONSTRUCTION,
            f"'{self.target}' is built here and at {other.relative}:"
            f"{other.call.lineno} from the same {shared} keyword=value pairs; "
            f"build it once in a function both callers use, so a new setting "
            f"lands in one place; see "
            f"`repostyle explain {RS_PARALLEL_CONSTRUCTION}`",
        )


def _built_collaborators(
    facts: ClassFacts, analysis: ForwardingAnalysis
) -> list[_BuiltCollaborator]:
    """Lists the constructed classes that fire for one class, strongest first.

    A class defined in the owner's own module is left out, since a class and
    the helper it builds beside it form one unit.
    """
    index = analysis.index
    built: dict[str, _BuiltCollaborator] = {}
    for method in methods(facts.node):
        for node in ast.walk(method):
            if not isinstance(node, ast.Call):
                continue
            target = index.resolve(node, facts.path)
            if target is None or target.path == facts.path:
                continue
            entry = built.setdefault(target.node.name, _BuiltCollaborator(target))
            entry.methods.add(method.name)
    for param, forwards in analysis.forwarded_params(facts.node.name).items():
        if (entry := built.get(forwards[0].target)) is not None:
            entry.params.append(param)
    for entry in built.values():
        entry.ports = index.port_names(entry.target)
    firing = [
        entry
        for entry in built.values()
        if len(entry.params) >= _MIN_FORWARDED_PARAMS or entry.ports
    ]
    return sorted(firing, key=lambda entry: (-len(entry.params), -len(entry.ports)))


def _collaborator_violation(
    owner: ClassFacts, built: list[_BuiltCollaborator], analysis: ForwardingAnalysis
) -> Violation:
    """Builds a class's finding from its strongest collaborator."""
    first, name = built[0], owner.node.name
    target = first.target.node.name
    where = ", ".join(f"'{method}'" for method in sorted(first.methods))
    reasons = []
    if len(first.params) >= _MIN_FORWARDED_PARAMS:
        depth = max(analysis.chain_depth(name, p, frozenset()) for p in first.params)
        reasons.append(
            f"from the forwarded parameters {_listed(first.params)} "
            f"(forwarding chain depth {depth})"
        )
    if first.ports:
        noun = "port" if len(first.ports) == 1 else "ports"
        reasons.append(f"and its constructor takes the {noun} {_listed(first.ports)}")
    others = ""
    if len(built) > 1:
        others = f"; it builds {_listed([b.target.node.name for b in built[1:]])} too"
    return Violation(
        owner.node.lineno,
        owner.node.col_offset + 1,
        RS_FORWARDED_COLLABORATOR,
        f"'{name}' builds '{target}' in {where} {' '.join(reasons)}{others}; "
        f"accept each built collaborator in the constructor (or a factory when "
        f"it needs per-call state such as a cost budget), let the composition "
        f"root build it, and delete the forwarded parameters and the defaults "
        f"they re-declare; see the repostyle:structural-refactor skill and "
        f"`repostyle explain {RS_FORWARDED_COLLABORATOR}`",
    )


def _construction_sites(index: PackageIndex, min_pairs: int) -> list[_ConstructionSite]:
    """Collects the keyword-heavy constructor calls of resolvable classes."""
    sites: list[_ConstructionSite] = []
    for path, tree, relative in index.sources:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.keywords) < min_pairs:
                continue
            target = index.resolve(node, path)
            if target is None:
                continue
            pairs = frozenset(
                (keyword.arg, ast.dump(keyword.value))
                for keyword in node.keywords
                if keyword.arg is not None
            )
            sites.append(
                _ConstructionSite(path, relative, node, target.node.name, pairs)
            )
    return sites


def _listed(names: Sequence[str]) -> str:
    """Quotes up to six names and counts the rest."""
    listed = ", ".join(f"'{name}'" for name in names[:_LISTED_NAMES])
    extra = len(names) - _LISTED_NAMES
    return listed + (f" and {extra} more" if extra > 0 else "")
