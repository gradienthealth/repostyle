"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import Example, RuleDoc
from repostyle.rules._violation import (
    RS_BULLET_ITEM_CASING,
    RS_NONSTANDARD_DASH,
    RS_OVER_BROAD_EXCEPT,
)
from repostyle.rules.error_handling import STRUCTURAL_BUILTINS

RULE_DOCS_PART: dict[str, RuleDoc] = {
    RS_OVER_BROAD_EXCEPT: RuleDoc(
        name="over-broad-except",
        summary=(
            "An `except` tuple does not reach past the failure it was written "
            "for, into the structural builtins."
        ),
        rationale=(
            "`AttributeError`, `TypeError`, `KeyError`, `IndexError`, "
            "`NameError`, and `UnboundLocalError` each say a value was not the "
            "shape the code assumed, which is what a bug looks like from the "
            "outside. A handler that takes in two of them at once, or one of "
            "them beside a declared exception -- any name the builtins do not "
            "define, whether from the stdlib, a third-party package, or this "
            "project -- cannot tell the failure it was written for from a typo "
            "in the same block, and that declared exception is already the "
            "callee's error contract, so the builtins beside it are covering "
            "something else. The fix is almost never in the handler: shrink a "
            "`try` that covers more statements than the handler was written "
            "for, so what raises the builtins sits outside it, or convert the "
            "failure where it arises so the callee raises one named error. "
            "Left alone are a "
            "handler ending in a `raise`, since a boundary converting what it "
            "caught into one named failure is the fix rather than the smell; a "
            "single structural builtin, which is routinely deliberate; and the "
            "value-and-environment errors (`ValueError`, `OSError`, and their "
            "kin) that report something the code handled correctly and does not "
            "control. ruff's `BLE001` covers only a bare `except Exception`, so "
            "a tuple of concrete builtins is a genuine gap."
        ),
        examples=(
            Example(
                bad=(
                    "try:\n"
                    "    return has_uncompressed_length(dataset)\n"
                    "except (PayloadError, AttributeError, TypeError, KeyError):\n"
                    "    return False"
                ),
                good=(
                    "try:\n"
                    "    return has_uncompressed_length(dataset)\n"
                    "except PayloadError:\n"
                    "    return False"
                ),
                note=(
                    "The builtins came from `int(dataset.Rows)` inside the "
                    "callee. Reading that attribute through a helper that "
                    "raises `PayloadError` leaves the handler one type wide."
                ),
            ),
            Example(
                bad="except (KeyError, TypeError):\n    return None",
                good=(
                    "except (KeyError, TypeError) as exc:\n"
                    "    raise ParseError('response missing a field') from exc"
                ),
                note=(
                    "The second remedy, for where the callee cannot be "
                    "changed: a handler whose last statement is a `raise` is a "
                    "boundary converting a wide failure into one named error, "
                    "so it is exempt and the callers above it catch only "
                    "`ParseError`. Raising on one branch and falling through "
                    "on another still swallows, so only the closing statement "
                    "counts."
                ),
            ),
        ),
        reference=tuple(sorted(STRUCTURAL_BUILTINS)),
    ),
    RS_BULLET_ITEM_CASING: RuleDoc(
        name="bullet-item-casing",
        summary=(
            "A bulleted list holding a multi-sentence item opens every item "
            "with a capital letter."
        ),
        rationale=(
            "A list item running more than one sentence is prose, and prose "
            "opens with a capital; once one item in a list is such prose, a "
            "lowercase sibling makes the list read in two registers at once. "
            "The rule therefore asks for consistency per list: a list with any "
            "multi-sentence item is sentence-cased throughout, while a list "
            "whose items are all single-sentence fragments may stay lowercase, "
            "since a fragment continues the sentence that introduced the list. "
            "This is RS047's opening-capital convention carried to bulleted "
            "lists, and like RS047 it exempts an item opening with a backtick "
            "span, a dotted path, a distinctive-shaped identifier, a digit, or "
            "any other non-letter. Not auto-fixable: capitalizing a leading "
            "word that is really a lowercase code name would corrupt it, so "
            "the opener is left to review."
        ),
        examples=(
            Example(
                bad="- the thing. Does a foo.\n- the other thing",
                good="- The thing. Does a foo.\n- The other thing.",
                note=(
                    "The first item runs two sentences, so the whole list is "
                    "sentence-cased. A list of one-sentence fragments (`- the "
                    "thing`) may stay lowercase."
                ),
            ),
        ),
    ),
    RS_NONSTANDARD_DASH: RuleDoc(
        name="nonstandard-dash",
        summary=(
            "Docstring and comment prose sets a clause off with the house "
            "sentence dash, the spaced `--`, not an em dash, en dash, or "
            "single hyphen."
        ),
        rationale=(
            "Prose reaches for a sentence dash in several shapes -- an em "
            "dash, spaced or glued, an en dash, a spaced single hyphen, a "
            "glued double hyphen -- and each writer picks one by local "
            "precedent, so files drift apart. The house standardizes on the "
            "spaced double hyphen: it is unambiguous ASCII (an em dash, an en "
            "dash, and a hyphen-minus render nearly alike in many editors, so "
            "drift among them is invisible), it cannot be mistaken for a "
            "bullet marker or a minus sign, and it greps trivially. The check "
            "masks backtick spans and URLs, leaves an unspaced en-dash range "
            "(`RS013–RS016`) alone, and requires letters around a "  # noqa: RUF001
            "hyphen form, so arithmetic, negative numbers, CLI flags, and bullet "
            "markers never fire. Auto-fixable: `--fix` rewrites each flagged "
            "dash to the spaced `--`."
        ),
        examples=(
            Example(
                bad="# resolves the config -- falling back to defaults",
                good="# resolves the config -- falling back to defaults",
            ),
            Example(
                bad='"""Returns the lease - or `None` when expired."""',
                good='"""Returns the lease -- or `None` when expired."""',
                note=(
                    "A spaced single hyphen between letters is doing dash "
                    "work; `3 - 5` and `n - 1` are left alone."
                ),
            ),
        ),
    ),
}
