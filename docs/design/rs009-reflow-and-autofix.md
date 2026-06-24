# RS009 reflow and the autofix substrate

Decision record for PROC-2280 (structure-aware reflow) and PROC-2279 (autofix substrate). The two issues turn on one shared question — what rewrite engine does `gradient-pystyle` adopt — so they are resolved together here.

## Decision

1. **Reflow on our own structure model, not an off-the-shelf formatter.** RS009's `_fill_units` already segments a docstring into the units that matter (Google sections as hanging paragraphs, bullets, and the verbatim exemptions). Reflow is a greedy refill of each fillable unit at its hanging indent. No `docformatter`, no `mdformat`.
1. **Splice, don't rebuild — and no `libcst`.** Re-inserting reflowed text is a targeted replacement of the line ranges the units already carry. `gradient-pystyle` only edits docstrings, comments, and single tokens, never restructures code, so a concrete syntax tree buys nothing. PROC-2279's "targeted text splice" option is the substrate.
1. **The check stays stdlib; reflow stays stdlib.** Because the reflow reuses the existing scanner, the always-on pre-commit hook keeps its stdlib-only footprint with no optional-dependency extra to manage.
1. **RS009 becomes the first autofix rule.** A `--fix` flag rewrites in place and exits non-zero when it changed a file, so the hook stops and the developer re-stages — the standard pre-commit fixer contract.

## Why not wrap docformatter or mdformat

The spike ran both tools at our 72-column house style against fixtures covering every structure RS009 must handle. Neither can reflow our docstrings:

| Structure | docformatter | mdformat `--wrap 72` |
| -- | -- | -- |
| Plain prose | reflows | reflows |
| Markdown table | flattens into a run-on paragraph | untouched (AST-safe) |
| Fenced code | verbatim | verbatim |
| Doctest `>>>` | verbatim | no concept |
| ASCII diagram | verbatim | — |
| Google `Args:`/`Returns:`/`Raises:` | no-op, leaves overflowing | misreads the indent as a code fence |
| Long bullet | no-op, leaves overflowing | hanging indent |
| Long URL | keeps the URL, rewraps around it | moves the URL to its own line |

The decisive row is Google sections, the core of the house style. `docformatter` ignores them and `mdformat` fences them — and `docformatter` destroys tables on top of that. The part both tools get wrong is exactly the part our scanner already gets right, so wrapping a formatter would mean fighting it on the cases we care about most while inheriting a new dependency. The earlier premise that `fhir-ingestor` standardizes on `libcst` is also false: it has no `libcst` anywhere (though it does already depend on `mdformat`).

## How the reflow works

`reflow_doc_fill(path, source, skip_lines)` walks the same docstring and comment units as the check. For each fillable unit it greedily refills to 72 columns: the first line keeps the unit's leading whitespace and any marker, and continuation lines wrap to a hanging indent — two columns for a bullet, four for a section entry or label, the established indent for a unit that already spans lines. The verbatim structures (code fences, doctests, tables, diagrams, section headers) break units and are never refilled. A unit is skipped when it carries a closing docstring quote on a text line, or when any of its lines is in `skip_lines` (the suppression set). Replacements apply bottom-up so earlier line numbers stay valid.

The table and diagram exemption is new: a line opening with `|` or a run of box-drawing characters (`+----+`, `====`, a `---` rule) is verbatim, which also fixes a latent false positive in the check itself.

## Known limitations

- Reflow treats an inline backtick code span as ordinary words, so a span containing spaces can wrap across a line boundary. The content is preserved; only the line break moves. Protecting spans as unbreakable units is a future refinement.
- ASCII-art detection covers the `|`- and box-character-led cases, not free-form art. Fence such art or suppress the line.
- Reflow normalizes intra-line runs of whitespace to single spaces, matching the single-space house style.

## Scope deferred

- A dedicated reflow path for standalone `.md` files, where `mdformat` (already a vetted dependency in `fhir-ingestor`) is a good fit and tables and fenced code are structurally untouchable.
- Autofix for the other mechanical rules named in PROC-2279 (RS001, RS005, RS010). Each is a single-token splice on the same substrate this record establishes.
