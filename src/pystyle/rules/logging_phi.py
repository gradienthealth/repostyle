"""PHI-safe logging rule: no `phi_safe` on an `exc_info` record"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from pystyle.rules._shared import _parse_python
from pystyle.rules._violation import RS_NO_PHI_SAFE_EXC_INFO, Violation

_LOGGING_CALL_NAMES = frozenset(
    {"debug", "info", "warning", "error", "critical", "exception", "log"}
)


def check_no_phi_safe_with_exc_info(path: Path, source: str) -> Iterator[Violation]:
    """A log record carrying `exc_info` may not be marked `phi_safe`

    The formatter renders the record's full exception chain, and
    third-party exception messages in the chain can embed identifiers
    (request URLs, query parameters, statement parameters), so no
    `exc_info`-bearing record can be certain to be PHI-free. Detected
    when a logging-style call (`.exception(...)`, or any level method
    with a truthy `exc_info=` argument) passes a literal `extra` (a dict
    display or `dict(...)` call) containing a `"phi_safe"` key.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _LOGGING_CALL_NAMES:
            continue
        extra = next((kw.value for kw in node.keywords if kw.arg == "extra"), None)
        if extra is None or not _extra_has_phi_safe(extra):
            continue
        if func.attr != "exception" and not _has_truthy_exc_info(node):
            continue
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_NO_PHI_SAFE_EXC_INFO,
            "record carries `exc_info`; the rendered exception chain cannot be "
            "certain PHI-free, so it must not be marked `phi_safe`",
        )


def _extra_has_phi_safe(extra: ast.expr) -> bool:
    if isinstance(extra, ast.Dict):
        return any(
            isinstance(key, ast.Constant) and key.value == "phi_safe"
            for key in extra.keys
        )
    if (
        isinstance(extra, ast.Call)
        and isinstance(extra.func, ast.Name)
        and extra.func.id == "dict"
    ):
        return any(kw.arg == "phi_safe" for kw in extra.keywords)
    return False


def _has_truthy_exc_info(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg != "exc_info":
            continue
        return not (
            isinstance(kw.value, ast.Constant) and kw.value.value in (False, None)
        )
    return False
