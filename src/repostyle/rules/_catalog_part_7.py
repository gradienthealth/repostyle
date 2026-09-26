"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import Example, RuleDoc
from repostyle.rules._violation import (
    RS_ACRONYM_CASING_IN_PROSE,
    RS_DISFAVORED_GCP_TERM,
    RS_GCP_BARE_IDENTIFIER,
    RS_PRIVATE_IMPORT,
)
from repostyle.rules.naming import DISFAVORED_GCP_TERMS, GCP_COLLECTION_NOUNS

RULE_DOCS_PART: dict[str, RuleDoc] = {
    RS_ACRONYM_CASING_IN_PROSE: RuleDoc(
        name="acronym-casing-in-prose",
        summary=(
            "A known acronym in docstring or comment prose is written in its "
            "canonical casing (`IPv6`, not `ipv6`; `NAT`, not `Nat`)."
        ),
        rationale=(
            "RS001 holds an acronym to its canonical casing in a CapWords "
            "identifier; this holds the same acronym to the same casing in the "
            "prose beside it, where a miscased `ipv6` or `Nat` reads as an "
            "ordinary word. The canonical casing is not always uppercase -- "
            "`IPv6` is mixed-case -- so each acronym carries its own target "
            "casing, and `--fix` recases an occurrence in place. The resolved "
            "set shares RS001's `acronyms-extra`/`acronyms-exclude` config keys. "
            "The check stays mechanical by firing only on a whole-word token, "
            "so a substring (`ID` in `identify`, `NAT` in `nation`), a "
            "hyphenated compound (`fhir-ingestor`, a proper name whose lowercase "
            "is correct), and a dotted name (`baseline.json`, `json.loads`) are "
            "left alone, as is a token inside a backtick span or "
            "a URL, a commented-out statement, and an `Args:` entry's parameter "
            "caption. An acronym whose lowercased form is a common English word "
            "(`SMART` to `smart`) is dropped from prose to avoid rewriting the "
            "word, though a repo can reintroduce it through `acronyms-extra`. "
            "Ruff has no acronym-casing-in-prose check, so this is a genuine gap."
        ),
        examples=(
            Example(
                bad='"""Parses the ipv6 address the Nat gateway advertises."""',
                good='"""Parses the IPv6 address the NAT gateway advertises."""',
                note="The canonical casing is per-acronym: `IPv6` mixed, `NAT` upper.",
            ),
        ),
    ),
    RS_DISFAVORED_GCP_TERM: RuleDoc(
        name="disfavored-gcp-term",
        summary=(
            "A disfavored Google Cloud product or brand name in docstring or "
            "comment prose is written in its current form (`Cloud Storage`, "
            "not `GCS`; `Google Cloud`, not `GCP`)."
        ),
        rationale=(
            "Google retired `GCP` and `Google Cloud Platform` as the umbrella "
            "brand (circa 2022) in favor of `Google Cloud`, and each product "
            "has one canonical name (`Cloud Storage`, `Compute Engine`, "
            "`Pub/Sub`), so prose that mixes the old shorthand with the current "
            "name reads as two systems. The map is curated and matched only "
            "as a whole word, so a substring (`GCS` in `GCSError`), a term "
            "glued to a hyphen, and a dotted name (`gcs.upload`) are left "
            "alone; a term in code font (the "
            "identifier `gcp.storage`), inside a URL, or in an `Args:` "
            "parameter caption is blanked before the scan and likewise "
            "skipped, and `--fix` rewrites the rest in place. Only unambiguous "
            "substitutions are mapped; a bare `Storage` "
            "or `Monitoring` is too often an ordinary English word to rewrite "
            "mechanically, so it is left to review. Ruff has no equivalent, and "
            "codespell catches misspellings, not brand-name substitutions."
        ),
        examples=(
            Example(
                bad='"""Uploads the study to a GCS bucket in GCP."""',
                good=(
                    '"""Uploads the study to a Cloud Storage bucket in Google Cloud."""'
                ),
                note=(
                    "Fix every disfavored term in the file; the reference is "
                    "the full map."
                ),
            ),
        ),
        reference=tuple(
            f"{term} -> {preferred}"
            for term, preferred in sorted(DISFAVORED_GCP_TERMS.items())
        ),
    ),
    RS_GCP_BARE_IDENTIFIER: RuleDoc(
        name="gcp-bare-identifier",
        summary=(
            "A string-typed parameter named for a Google Cloud resource "
            "collection (`project`, `bucket`, ...) carries the `_id` suffix."
        ),
        rationale=(
            "Google's resource-oriented design distinguishes a resource's bare "
            "id (`my-bucket`) from its qualified `{collection}/{id}` name. A "
            "`str` parameter named for the collection alone almost always holds "
            "the id, and the "
            "`_id` suffix says so, so a caller reads the intent without tracing "
            "the value; it also matches the `project_id` the code should pass to "
            "a Pulumi `project=` argument, rather than the bare `project` that "
            "Pulumi's own signature uses. The check fires only on a string "
            "annotation, so a "
            "resource object or an `Output` named `project` is left alone, and "
            "only on an exact-match name, so `project_id` and `bucket_url` are "
            "not touched. It reaches only this unambiguous subset; whether a "
            "`*_name` holds a bare id, a path, or a Pulumi logical handle is "
            "dataflow-dependent and stays with review (`docs/gcp-naming.md`). A "
            "repo with no Google Cloud resources drops the rule via `ignore`."
        ),
        examples=(
            Example(
                bad="def grant_viewer(project: str, bucket: str) -> None: ...",
                good="def grant_viewer(project_id: str, bucket_id: str) -> None: ...",
                note="Only a `str`-typed, exact collection-noun parameter is flagged.",
            ),
        ),
        reference=tuple(
            f"{noun} -> {noun}_id" for noun in sorted(GCP_COLLECTION_NOUNS)
        ),
    ),
    RS_PRIVATE_IMPORT: RuleDoc(
        name="private-import",
        summary=(
            "A first-party import consumes another package's public surface, "
            "not its `_`-private internals."
        ),
        rationale=(
            "A single leading underscore marks a module or name internal to the "
            "package that holds it, so reaching it from outside that package "
            "relies on an implementation detail the author did not publish. The "
            "supported way to use another package is the surface it re-exports "
            "from its `__init__`; if a member is needed there, it should be "
            "lifted onto that surface, not reached past. This is the dual of "
            "RS029: RS029 asks a package to hide what only it uses, this asks "
            "other code not to reach into what was hidden. The check scopes to "
            "imports that share the importer's top-level package, so it governs "
            "a repo's own layering and leaves a reach into a third-party "
            "distribution -- whose internals a repo cannot restructure -- alone. "
            "It follows PEP 8's `Public and internal interfaces`: an interface "
            "is internal if any containing namespace is, and other modules must "
            "not rely on indirect access to it except through a package's "
            "documented `__init__`. A test module is exempt, since exercising a "
            "unit under test's internals is expected."
        ),
        examples=(
            Example(
                bad="# in myapp/api/views.py\nfrom myapp.core._engine import run",
                good="# in myapp/api/views.py\nfrom myapp.core import run",
                note=(
                    "`_engine` is internal to `myapp.core`, and `views` lives "
                    "outside `core`, so it must go through `core`'s public "
                    "surface. Re-export `run` from `core/__init__.py` rather "
                    "than reaching past it. An import from within `myapp.core` "
                    "itself is fine."
                ),
            ),
        ),
    ),
}
