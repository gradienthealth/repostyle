# Judgment conventions

This is the judgment layer of the Python house style: the conventions a tool cannot decide, held up by review. It is the canonical source, and each consuming repo's `CLAUDE.md` references it rather than restating it.

## Two layers

The house style has two layers, and they do not overlap.

**Mechanical** is the `RSnnn` rules in this package plus ruff, mypy, and pydoclint. These are conventions decidable from the AST, the token stream, or the line: acronym casing, abbreviations, docstring shape, fill width, import order, member order, and comment-tag format. Several naming conventions graduated here from review, including the negated boolean (RS024), the production `make_` (RS025), and the `bool`-annotated name missing its prefix (RS026). Mechanical rules fail CI, and an engineer never argues with them.

**Judgment** is everything below. These conventions need a reader to decide whether a docstring is about the right subject, whether a comment earns its place, or whether a verb means what the tree uses it to mean. Review upholds them, never a linter.

A convention belongs in exactly one layer. Once a judgment convention turns out to be mechanically decidable with near-zero false positives, it graduates to an `RSnnn` rule and leaves this doc. RS024, RS025, and RS026 all took that path. What remains here is the judgment that resisted it.

## A. A docstring states the unit's own contract

A docstring covers what *this* unit does: its inputs, outputs, behavior, edge cases, and the errors it raises. It does not describe callers, neighboring services, deployment topology, or someone else's responsibility. That context belongs in a README or a design doc, where it stays current as the topology shifts.

- A sentence describing a neighbor ("the caller then persists this to BigQuery") → cut it, or move it to the neighbor.
- Change history ("previously this returned a list, now...") → cut it. That lives in the commit and the pull request.
- A rejected alternative ("we considered a cache but...") → cut it. The docstring states the contract, not the design debate.
- A project-wide invariant the `CLAUDE.md` already owns → cut it. Do not duplicate it per unit.
- A constraint that genuinely shaped this unit → keep it, restated from the unit's own perspective. Write "rejects timestamps before the epoch", not "because downstream BigQuery cannot store them".

RS018 flags the presence and shape of under-documentation. Whether the prose is about the right subject is judgment.

## B. A comment justifies why, not what

A comment earns its place only for a non-obvious *why*: a hidden constraint, a subtle invariant, a bug workaround, or surprising third-party behavior. The identifiers already show the *what*.

- **What-narration** restating the line below it (`# increment the counter`) → cut it.
- **Absence narration** (`# no error handling needed here`, `# intentionally empty`) → cut it. An absence is not a comment-worthy fact.
- **Ticket references** (`PROC-1234`, `#1234`) on ordinary new code → cut them. The ticket lives in the pull request title and the commit, and `git blame` supplies provenance. Keep one only where it carries out-of-band context the reader needs, such as a workaround for an incident or a flag added after an outage. Keep one in a regression test too, where it pins why that specific behavior is defended. RS022 owns the shape of a tag comment; whether it earns its place is judgment.

## C. Verbs encode cost and failure mode

The verb tells a reader, without opening the body, whether a call does I/O, can raise, or mutates. A name is syntactically valid whatever verb it picks, so only judgment catches a verb that lies.

- **`build_`** is pure in-memory assembly with no I/O. A `build_` that writes a file or hits the network is mis-verbed, and wants to be `create_` or to have the I/O split out.
- **`create_`** changes the world: it writes, registers, or calls a remote. The `create_app` and `create_*_router` web-factory idiom is the sanctioned exception, since it assembles in memory despite the verb.
- **`from_<x>`** is an alternate constructor, a classmethod returning an instance, matching the stdlib's `datetime.fromisoformat`.
- **`make_`** is for test fixtures only. A production `make_` is now RS025.
- **Retrieval is layered.** At the transport layer, `get_` and `post_` mirror the HTTP verb they issue. `fetch_` is slow or fallible domain retrieval, meaning a remote read that can fail or block. A plain `get_` elsewhere is a cheap, in-memory, roughly constant-time lookup that does not fail, so a `get_` making a network call wants to be `fetch_`.
- **One verb per concept.** `parse_`, `write_`, `render_`, and `resolve_` each name one operation. Do not introduce a synonym such as `compute_`, `calculate_`, or `derive_` when the tree already settled on one, and check the surrounding modules for the established verb.
- **`validate_`, `check_`, and `ensure_`** return a verdict or raise. They never silently return `None` on both success and failure, and a predicate that swallows its result is mis-named. This stays judgment rather than a rule because whether a function signals failure can hinge on a helper it calls, which a linter cannot see.

## D. Nouns name identity, and clarity beats brevity

**A noun names what an object *is***, by its responsibility, not by a vague role. RS011 bans the literal `Manager`, `Helper`, `Util`, and `Utils` suffixes. Judgment catches the misses those four words cannot enumerate, such as a `Processor` or `Coordinator` that names what a class loosely does. A class whose best name is a verb usually wants to be a function.

**A boolean reads as a positive yes/no question**, prefixed `is_`, `has_`, `can_`, or `should_`. RS024 rejects an embedded `not` or `no`, and RS026 requires the prefix on a `bool`-annotated name. Judgment catches what neither reaches: a boolean that reads negative through a prefix-merged word, such as `is_invalid` forcing `if not is_invalid` where `is_valid` reads better, and a `bool`-returning function or property not phrased as a question at all, such as `valid()` for `is_valid()`, whose return type RS026's annotation match does not see.

**Clarity beats brevity.** This codebase is verbose on purpose, and a longer name that removes a guess wins. RS010 owns the fixed abbreviation list. Judgment catches the wide-scope, too-terse name it cannot pre-enumerate: a module-level `data`, `tmp`, or `val`, or a single-letter variable outside a loop, each of which forces the reader to reconstruct intent.

## E. Tests pin contract, not implementation

Ask this of every assertion: if a refactor preserves the behavior the user actually relies on, would this assertion still pass? If not, it pins implementation. The mechanical test smells are gated by RS013 through RS016. What follows is the semantic residue those token checks cannot see.

- **Verbatim message-layout pinning.** A `match=` regex or a `str(exc) ==` comparison that pins a message's layout — its word order and separators — instead of the fields it must surface. A single important identifier such as `match=r"access_token"` is fine. The smell is a multi-token regex mirroring an f-string line.
- **Constant pinning.** An assertion equal to a constant defined next to the code under test. It fails only if someone edits both sides at once, which is not a realistic regression.
- **Constant-coupled numerics.** A hardcoded number justified as "greater than *some magic constant in the source*". Import the constant and test the boundary, or rename the test to the looser guarantee it actually defends.
- **Incidental call counts.** `assert spy.call_count == 3` where the 3 is incidental. This is acceptable only when the count *is* the contract, as in "a 5-item page deduped to 1 request".

Prefer asserting the fields a message must surface over its exact layout. Looping `for sub in ["401", "invalid_client"]: assert sub in str(exc.value)` survives a formatting refactor that `match=r"401 invalid_client: ..."` does not.

## F. Prose stays accurate after edits

The most common find on a polished branch is a docstring or comment that a later edit left stale. Cross-reference each changed docstring against the current signature and body, not against what it said before.

- A concept an earlier edit renamed, now wrong in a docstring still using the old name.
- A behavior a fix subtly changed, now mis-described by prose written before the fix.
- An `Args:` or `Returns:` line describing a parameter or return the signature no longer has.

## Using this canon

**Repos** reference this doc from their `CLAUDE.md` style section rather than restating the conventions, so the canon has one home. Repo-specific conventions, such as a hexagonal ports layer or a test-naming scheme, stay in that repo's own docs. What lives here applies across repos.

**Reviewers**, human or agent, cite this doc as the source of truth rather than restating a convention in a comment thread.

**Graduation is one-directional.** A judgment convention that becomes mechanically decidable moves to an `RSnnn` rule and is struck from this doc, with a pointer left behind. `make_` and the negated boolean both went that way. This doc only ever shrinks as the linter grows.
