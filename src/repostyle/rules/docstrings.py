"""Docstring structure, prose, and code-span rules."""

from repostyle.rules._docstring_edits import (
    DOUBLE_BACKTICK_PATTERN as DOUBLE_BACKTICK_PATTERN,
)
from repostyle.rules._docstring_edits import (
    fix_docstring_terminal_punctuation as fix_docstring_terminal_punctuation,
)
from repostyle.rules.code_spans import (
    check_glued_code_span_in_comments as check_glued_code_span_in_comments,
)
from repostyle.rules.code_spans import (
    check_glued_code_span_in_docstrings as check_glued_code_span_in_docstrings,
)
from repostyle.rules.code_spans import (
    check_glued_code_span_in_md as check_glued_code_span_in_md,
)
from repostyle.rules.code_spans import (
    check_no_double_backticks_in_docstrings as check_no_double_backticks_in_docstrings,
)
from repostyle.rules.code_spans import (
    check_no_double_backticks_in_md as check_no_double_backticks_in_md,
)
from repostyle.rules.code_spans import (
    fix_double_backticks as fix_double_backticks,
)
from repostyle.rules.docstring_openings import (
    check_field_comment_as_docstring as check_field_comment_as_docstring,
)
from repostyle.rules.docstring_openings import (
    check_filler_docstring_opening as check_filler_docstring_opening,
)
from repostyle.rules.docstring_openings import (
    check_imperative_docstring_opening as check_imperative_docstring_opening,
)
from repostyle.rules.docstring_openings import (
    check_summary_comment_as_docstring as check_summary_comment_as_docstring,
)
from repostyle.rules.docstring_sections import (
    ATTRIBUTES_SECTION_PATTERN as ATTRIBUTES_SECTION_PATTERN,
)
from repostyle.rules.docstring_sections import (
    check_docstring_section_alias as check_docstring_section_alias,
)
from repostyle.rules.docstring_sections import (
    check_docstring_section_order as check_docstring_section_order,
)
from repostyle.rules.docstring_sections import (
    check_duplicate_docstring_section as check_duplicate_docstring_section,
)
from repostyle.rules.docstring_sections import (
    check_invalid_docstring_section as check_invalid_docstring_section,
)
from repostyle.rules.docstring_sections import (
    check_no_attributes_block as check_no_attributes_block,
)
from repostyle.rules.docstring_sections import (
    fix_docstring_section_alias as fix_docstring_section_alias,
)
from repostyle.rules.prose_typography import (
    check_disfavored_gcp_term_in_docstrings as check_disfavored_gcp_term_in_docstrings,
)
from repostyle.rules.prose_typography import (
    check_nonstandard_dash_in_docstrings as check_nonstandard_dash_in_docstrings,
)
from repostyle.rules.prose_typography import (
    fix_disfavored_gcp_term_in_docstrings as fix_disfavored_gcp_term_in_docstrings,
)
from repostyle.rules.prose_typography import (
    fix_nonstandard_dash_in_docstrings as fix_nonstandard_dash_in_docstrings,
)
from repostyle.rules.sentence_style import (
    check_bullet_item_casing as check_bullet_item_casing,
)
from repostyle.rules.sentence_style import (
    check_bullet_item_casing_in_comments as check_bullet_item_casing_in_comments,
)
from repostyle.rules.sentence_style import (
    check_docstring_temporal_markers as check_docstring_temporal_markers,
)
from repostyle.rules.sentence_style import (
    check_docstring_terminal_punctuation as check_docstring_terminal_punctuation,
)
from repostyle.rules.sentence_style import (
    check_lowercase_entry_description as check_lowercase_entry_description,
)
from repostyle.rules.sentence_style import (
    check_unbackticked_code_reference as check_unbackticked_code_reference,
)
from repostyle.rules.symbol_references import (
    check_acronym_casing_in_docstrings as check_acronym_casing_in_docstrings,
)
from repostyle.rules.symbol_references import (
    check_unbackticked_sibling_symbol as check_unbackticked_sibling_symbol,
)
from repostyle.rules.symbol_references import (
    check_unbackticked_sibling_symbol_in_comments as check_unbackticked_sibling_symbol_in_comments,
)
from repostyle.rules.symbol_references import (
    fix_acronym_casing_in_docstrings as fix_acronym_casing_in_docstrings,
)
