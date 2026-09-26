"""A partition of the single-file rule registry."""

from repostyle.rules._violation import (
    RS_ACRONYM_CASING_IN_PROSE,
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_BANNER_COMMENT,
    RS_BULLET_ITEM_CASING,
    RS_DEEPLY_NESTED_TYPE,
    RS_DISFAVORED_GCP_TERM,
    RS_DOC_SUMMARY_OVERFLOW,
    RS_DOCSTRING_SECTION_ALIAS,
    RS_DOCSTRING_SECTION_ORDER,
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    RS_DUPLICATE_DOCSTRING_SECTION,
    RS_EQ_HASH_PAIRING,
    RS_EXCEPTION_ALIAS,
    RS_FILENAME_CONVENTION,
    RS_FILLER_DOCSTRING_OPENING,
    RS_GLUED_CODE_SPAN,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_INVALID_DOCSTRING_SECTION,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_NONSTANDARD_DASH,
    RS_OVER_BROAD_EXCEPT,
    RS_PREDICATE_FUNCTION_NAMING,
    RS_PRIVATE_IMPORT,
    RS_RAISE_DESCRIBED_IN_PROSE,
    RS_RAISES_SECTION_INCOMPLETE,
    RS_RANGE_LEN_REINDEX,
    RS_RETURN_DESCRIBED_IN_PROSE,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    RS_TOO_MANY_POSITIONAL_ARGS,
    RS_UNBACKTICKED_CODE_REFERENCE,
    RS_UNBACKTICKED_SIBLING_SYMBOL,
)
from repostyle.rules.annotations import check_deeply_nested_type
from repostyle.rules.comments import (
    check_acronym_casing_in_comments,
    check_banner_comment,
    check_comment_temporal_markers,
    check_comment_terminal_punctuation,
    check_disfavored_gcp_term_in_comments,
    check_nonstandard_dash_in_comments,
)
from repostyle.rules.doc_fill import (
    check_doc_summary_overflow,
    check_double_space_after_period,
)
from repostyle.rules.doc_value import (
    check_arg_described_in_prose,
    check_raise_described_in_prose,
    check_raises_section_incomplete,
    check_return_described_in_prose,
)
from repostyle.rules.docstrings import (
    check_acronym_casing_in_docstrings,
    check_bullet_item_casing,
    check_bullet_item_casing_in_comments,
    check_disfavored_gcp_term_in_docstrings,
    check_docstring_section_alias,
    check_docstring_section_order,
    check_docstring_temporal_markers,
    check_docstring_terminal_punctuation,
    check_duplicate_docstring_section,
    check_filler_docstring_opening,
    check_glued_code_span_in_comments,
    check_glued_code_span_in_docstrings,
    check_glued_code_span_in_md,
    check_imperative_docstring_opening,
    check_invalid_docstring_section,
    check_lowercase_entry_description,
    check_nonstandard_dash_in_docstrings,
    check_unbackticked_code_reference,
    check_unbackticked_sibling_symbol,
    check_unbackticked_sibling_symbol_in_comments,
)
from repostyle.rules.encapsulation import check_private_import
from repostyle.rules.equality import check_eq_hash_pairing
from repostyle.rules.error_handling import check_over_broad_except
from repostyle.rules.filenames import (
    check_filename_casing,
    check_filename_extension,
)
from repostyle.rules.idioms import check_range_len_reindex
from repostyle.rules.naming import (
    check_exception_alias,
    check_predicate_function_naming,
)
from repostyle.rules.signatures import check_too_many_positional_args

RULES_PART = {
    RS_FILLER_DOCSTRING_OPENING: (check_filler_docstring_opening,),
    RS_IMPERATIVE_DOCSTRING_OPENING: (check_imperative_docstring_opening,),
    RS_TOO_MANY_POSITIONAL_ARGS: (check_too_many_positional_args,),
    RS_EXCEPTION_ALIAS: (check_exception_alias,),
    RS_TERMINAL_PUNCTUATION: (
        check_docstring_terminal_punctuation,
        check_comment_terminal_punctuation,
    ),
    RS_ARG_DESCRIBED_IN_PROSE: (check_arg_described_in_prose,),
    RS_RETURN_DESCRIBED_IN_PROSE: (check_return_described_in_prose,),
    RS_FILENAME_CONVENTION: (check_filename_extension, check_filename_casing),
    RS_DOC_SUMMARY_OVERFLOW: (check_doc_summary_overflow,),
    RS_UNBACKTICKED_CODE_REFERENCE: (check_unbackticked_code_reference,),
    RS_GLUED_CODE_SPAN: (
        check_glued_code_span_in_md,
        check_glued_code_span_in_docstrings,
        check_glued_code_span_in_comments,
    ),
    RS_UNBACKTICKED_SIBLING_SYMBOL: (
        check_unbackticked_sibling_symbol,
        check_unbackticked_sibling_symbol_in_comments,
    ),
    RS_DEEPLY_NESTED_TYPE: (check_deeply_nested_type,),
    RS_RAISE_DESCRIBED_IN_PROSE: (check_raise_described_in_prose,),
    RS_EQ_HASH_PAIRING: (check_eq_hash_pairing,),
    RS_RAISES_SECTION_INCOMPLETE: (check_raises_section_incomplete,),
    RS_PREDICATE_FUNCTION_NAMING: (check_predicate_function_naming,),
    RS_TEMPORAL_MARKER: (
        check_docstring_temporal_markers,
        check_comment_temporal_markers,
    ),
    RS_RANGE_LEN_REINDEX: (check_range_len_reindex,),
    RS_LOWERCASE_ENTRY_DESCRIPTION: (check_lowercase_entry_description,),
    RS_PRIVATE_IMPORT: (check_private_import,),
    RS_ACRONYM_CASING_IN_PROSE: (
        check_acronym_casing_in_docstrings,
        check_acronym_casing_in_comments,
    ),
    RS_DISFAVORED_GCP_TERM: (
        check_disfavored_gcp_term_in_docstrings,
        check_disfavored_gcp_term_in_comments,
    ),
    RS_OVER_BROAD_EXCEPT: (check_over_broad_except,),
    RS_BULLET_ITEM_CASING: (
        check_bullet_item_casing,
        check_bullet_item_casing_in_comments,
    ),
    RS_NONSTANDARD_DASH: (
        check_nonstandard_dash_in_docstrings,
        check_nonstandard_dash_in_comments,
    ),
    RS_BANNER_COMMENT: (check_banner_comment,),
    RS_INVALID_DOCSTRING_SECTION: (check_invalid_docstring_section,),
    RS_DOCSTRING_SECTION_ORDER: (check_docstring_section_order,),
    RS_DOCSTRING_SECTION_ALIAS: (check_docstring_section_alias,),
    RS_DUPLICATE_DOCSTRING_SECTION: (check_duplicate_docstring_section,),
    RS_DOUBLE_SPACE_AFTER_PERIOD: (check_double_space_after_period,),
}
