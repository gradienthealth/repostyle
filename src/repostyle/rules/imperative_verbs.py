"""RS034's imperative-verb vocabulary and conjugation.

Kept separate from the docstring-form checks in `docstrings.py`: this data
(which bare-infinitive verbs to recognize, and how each conjugates) is a
distinct "vocabulary" concern from the AST-walking check that consumes it, and
this module's own top-level `IMPERATIVE_VERB_CONJUGATIONS` needs `conjugate`
defined above it, a constraint the `_effective_conjugations` in `docstrings.py`
(which also calls `conjugate`) cannot satisfy from within the same file without
an ordering conflict.
"""

from __future__ import annotations

import re

# Bare-infinitive verbs commonly seen opening a docstring summary, matched
# case-sensitively (a docstring summary always capitalizes its first word) with
# a trailing `\b`, so `Returned` or `Returning` does not false-match `Return`.
#
# Base list adapted from pydocstyle's own `imperatives.txt` (the word list
# behind ruff/pydocstyle's D401, which checks the opposite convention -- a
# docstring opening should be imperative, not descriptive). MIT licensed;
# Copyright (c) 2012 GreenSteam, 2014-2020 Amir Rachum, 2020 Sambhav Kothari.
# https://github.com/PyCQA/pydocstyle/blob/master/src/pydocstyle/data/imperatives.txt
#
# A common-noun reading is a real risk for many of these (`Check`, `Report`,
# `Format`, `Handle`, `Set`, `Group`, `Flag`, `Filter`, ...); pydocstyle's own
# comment on that file accepts the risk wholesale rather than excluding every
# homograph, since blacklisting them would itself false-positive on their many
# genuinely correct imperative uses. This list takes the same trade-off,
# reinforced for `Check`, `Report`, `Format`, `Handle`, and `Set` by a survey
# of gradienthealth's other Python repos (dicom-ingestor, fhir-ingestor) that
# independently found real imperative-mood openings for each with no
# noun-phrase false positive. `Route` carries the same risk but is not itself a
# pydocstyle entry; it stays in the list solely on that survey's evidence.
#
# A handful of pydocstyle's entries are dropped anyway because the noun reading
# dominates in this codebase's own domain rather than software generally:
# `List` (Python's `list`), `Query` (a database query), `Post` (an HTTP
# `POST`), `Test` (a test-heavy repo), `Import` (a FHIR/DICOM import job),
# `View` (a database view), `Map` (a `dict`-like map), `Store` (a data store),
# `Log` (a log record), `Process` (a process id or pipeline step), and `Match`
# (a regex match object). `Partial`, `Rollback`, and `Init` are dropped as not
# real standalone verbs (`functools.partial`, the two-word phrasal "roll back",
# and an abbreviation, respectively).
IMPERATIVE_VERBS: tuple[str, ...] = (
    "Accept",
    "Access",
    "Add",
    "Adjust",
    "Advance",
    "Aggregate",
    "Allow",
    "Append",
    "Apply",
    "Archive",
    "Assert",
    "Assign",
    "Attempt",
    "Authenticate",
    "Authorize",
    "Block",
    "Break",
    "Build",
    "Cache",
    "Calculate",
    "Call",
    "Cancel",
    "Capture",
    "Change",
    "Check",
    "Clean",
    "Clear",
    "Close",
    "Collect",
    "Combine",
    "Commit",
    "Compare",
    "Compute",
    "Configure",
    "Confirm",
    "Connect",
    "Construct",
    "Consume",
    "Control",
    "Convert",
    "Copy",
    "Count",
    "Cover",
    "Create",
    "Customize",
    "Declare",
    "Decode",
    "Decorate",
    "Decrement",
    "Decrypt",
    "Define",
    "Delegate",
    "Delete",
    "Deprecate",
    "Derive",
    "Describe",
    "Detect",
    "Determine",
    "Disable",
    "Discover",
    "Dispatch",
    "Display",
    "Dispose",
    "Do",
    "Download",
    "Drain",
    "Drop",
    "Dump",
    "Emit",
    "Empty",
    "Enable",
    "Encapsulate",
    "Encode",
    "Encrypt",
    "End",
    "Ensure",
    "Enter",
    "Enumerate",
    "Establish",
    "Evaluate",
    "Examine",
    "Execute",
    "Exit",
    "Expand",
    "Expect",
    "Export",
    "Extend",
    "Extract",
    "Feed",
    "Fetch",
    "Fill",
    "Filter",
    "Finalize",
    "Find",
    "Finish",
    "Fire",
    "Fix",
    "Flag",
    "Flatten",
    "Force",
    "Format",
    "Forward",
    "Generate",
    "Get",
    "Give",
    "Go",
    "Group",
    "Handle",
    "Hash",
    "Have",
    "Help",
    "Hold",
    "Identify",
    "Implement",
    "Increment",
    "Indicate",
    "Initialise",
    "Initialize",
    "Initiate",
    "Input",
    "Insert",
    "Instantiate",
    "Intercept",
    "Invoke",
    "Iterate",
    "Join",
    "Keep",
    "Launch",
    "Lease",
    "Listen",
    "Load",
    "Look",
    "Make",
    "Manage",
    "Manipulate",
    "Mark",
    "Merge",
    "Mock",
    "Modify",
    "Monitor",
    "Move",
    "Normalize",
    "Note",
    "Obtain",
    "Omit",
    "Open",
    "Output",
    "Override",
    "Overwrite",
    "Package",
    "Pad",
    "Parse",
    "Pass",
    "Perform",
    "Persist",
    "Pick",
    "Plot",
    "Poll",
    "Populate",
    "Prepare",
    "Print",
    "Probe",
    "Produce",
    "Provide",
    "Publish",
    "Pull",
    "Put",
    "Raise",
    "Read",
    "Reconcile",
    "Record",
    "Redirect",
    "Refer",
    "Refresh",
    "Register",
    "Release",
    "Reload",
    "Remove",
    "Rename",
    "Render",
    "Renew",
    "Replace",
    "Reply",
    "Report",
    "Represent",
    "Request",
    "Require",
    "Reset",
    "Resolve",
    "Restore",
    "Retrieve",
    "Return",
    "Roll",
    "Round",
    "Route",
    "Run",
    "Sample",
    "Sanitize",
    "Save",
    "Scan",
    "Search",
    "Select",
    "Send",
    "Serialise",
    "Serialize",
    "Serve",
    "Set",
    "Show",
    "Sign",
    "Signal",
    "Simulate",
    "Skip",
    "Sleep",
    "Sort",
    "Source",
    "Specify",
    "Spin",
    "Split",
    "Start",
    "Step",
    "Stop",
    "Strip",
    "Submit",
    "Subscribe",
    "Sum",
    "Survive",
    "Swap",
    "Sync",
    "Synchronise",
    "Synchronize",
    "Take",
    "Tear",
    "Time",
    "Transform",
    "Translate",
    "Transmit",
    "Truncate",
    "Try",
    "Turn",
    "Tweak",
    "Unblock",
    "Update",
    "Upload",
    "Upsert",
    "Use",
    "Validate",
    "Verify",
    "Wait",
    "Walk",
    "Wrap",
    "Write",
    "Yield",
)
# Every verb above conjugates by the suffix rule below except a genuine stem
# change (`Have`), so the mapping is derived rather than hand-typed -- a future
# addition needs only the infinitive.
_IRREGULAR_CONJUGATIONS: dict[str, str] = {"Have": "Has"}
_ES_CONJUGATION_SUFFIXES = ("s", "x", "z", "ch", "sh", "o")


def conjugate(verb: str) -> str:
    """Conjugates a bare-infinitive `verb` to third-person singular."""
    if verb in _IRREGULAR_CONJUGATIONS:
        return _IRREGULAR_CONJUGATIONS[verb]
    if verb.endswith(_ES_CONJUGATION_SUFFIXES):
        return f"{verb}es"
    if len(verb) > 1 and verb.endswith("y") and verb[-2].lower() not in "aeiou":
        return f"{verb[:-1]}ies"
    return f"{verb}s"


IMPERATIVE_VERB_CONJUGATIONS: dict[str, str] = {
    verb: conjugate(verb) for verb in IMPERATIVE_VERBS
}
IMPERATIVE_OPENING_PATTERN = re.compile(
    r"^(" + "|".join(IMPERATIVE_VERB_CONJUGATIONS) + r")\b"
)


# The `explain RS034` card's reference table: only the conjugations a reader
# cannot derive by just appending `s` (an irregular stem, or the `-es`/`-ies`
# suffix rules), so it stays a quick reference at the list's full size instead
# of repeating ~200 mechanically obvious entries. Compares each conjugation
# against the plain-suffix default rather than re-deriving the branch
# conditions of `conjugate`, so the table cannot drift from what `conjugate`
# computes.
NON_TRIVIAL_CONJUGATIONS: dict[str, str] = {
    verb: conjugated
    for verb, conjugated in IMPERATIVE_VERB_CONJUGATIONS.items()
    if conjugated != f"{verb}s"
}
