# Test module size rule

Status: Implemented.

## Objective

Warn when a Python test module exceeds 500 code lines, prompting review of production responsibility boundaries and test organization. A large test module warrants review but does not by itself establish a production defect.

## Implementation plan

1. Use the existing test-file detection, including Python helpers and `conftest.py` under `tests/`. Count each physical code line once. Exclude blank lines, comment-only lines, and module, class, and function docstrings. Include imports, decorators, fixtures, helpers, parameter tables, non-docstring string literals, and bracket-only lines. Exactly 500 passes; 501 warns.
1. Use AST source spans to identify docstrings and tokens to distinguish comments from code. Preserve code sharing a line with a docstring or comment. Follow existing invalid-Python handling. Emit one finding per file and provide no automatic fix. Suggested message: "Test module has 742 code lines (limit: 500); review responsibility boundaries and split tests into cohesive modules."
1. Add `max-test-file-lines = 500` under `[tool.repostyle]`, accepting positive integers. Allocate the next available rule ID during implementation. Register warning severity with existing error-promotion support. Add exports, catalog guidance, and repository documentation.
1. Reuse `# style: ignore-file[RSnnn]` to suppress only this rule throughout a file. Document the allocated ID, recommend placing the directive near the top, and explain that a short rationale can help future readers.
1. Test threshold boundaries, documentation exclusions, multiline data, decorators, mixed code and comments, scope, configuration, and invalid configuration. Verify whole-file suppression preserves unrelated findings. Check baseline and deprecated diff-mode behavior and document any limit imposed by line-based filtering. Run the test suite and repository checks, then inspect findings against this repository's tests.
1. Explain useful remediation: split production responsibilities when tests expose coupling or unrelated behavior; otherwise organize tests into cohesive modules. Discourage arbitrary numbered splits and reducing coverage merely to satisfy the threshold.

## Completion record

RS062 implements the rule as a warning. It uses the existing test-file scope and reads `max-test-file-lines` as a positive integer with a default of 500. It emits one finding at the first counted code line and has no automatic fix.

The count uses AST expression spans to exclude complete module, class, and function docstrings, including parenthesized and concatenated forms. Python tokens identify code, so comment-only and blank lines are excluded while code sharing a line with a comment or docstring remains counted. Non-docstring multiline strings count each nonblank physical line. Invalid Python produces no finding, matching the other Python rules.

The focused RS062 suite passed with 26 tests. The final full suite passed with 1,455 tests on Python 3.13, and `pre-commit run --all-files` passed every hook. The repository self-scan found three existing test modules over the default: `tests/test_doc_value.py` at 826 code lines, `tests/test_rules.py` at 2,831, and `tests/test_runner.py` at 532.

A rule-specific `ignore-file` directive suppresses only RS062. A baseline records its single per-file finding, so later growth stays suppressed until the finding is retired; the baseline does not ratchet the line count. The deprecated `--diff` mode filters on the first code line, so an edit elsewhere in an oversized module does not report RS062 unless that anchor line also changes.
