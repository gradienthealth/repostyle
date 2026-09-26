"""Binds checks for python rules."""

from repostyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_BANNED_IMPORT_BY_PATH,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_COGNITIVE_COMPLEXITY,
    RS_DEEPLY_NESTED_TYPE,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DURATION_AS_TIMEDELTA,
    RS_ELEMENT_ORDER,
    RS_EQ_HASH_PAIRING,
    RS_EXCEPTION_ALIAS,
    RS_FILENAME_CONVENTION,
    RS_GCP_BARE_IDENTIFIER,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_NEGATED_BOOLEAN,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_OVER_BROAD_EXCEPT,
    RS_PORT_NO_IMPLEMENTATION,
    RS_PREDICATE_FUNCTION_NAMING,
    RS_PRIVATE_IMPORT,
    RS_RANGE_LEN_REINDEX,
    RS_SOURCE_MODULE_SIZE,
    RS_TOO_MANY_POSITIONAL_ARGS,
)
from repostyle.rules.annotations import (
    check_deeply_nested_type,
)
from repostyle.rules.complexity import (
    check_cognitive_complexity,
)
from repostyle.rules.docstrings import (
    check_imperative_docstring_opening,
)
from repostyle.rules.duration import (
    check_duration_as_timedelta,
)
from repostyle.rules.encapsulation import (
    check_private_import,
)
from repostyle.rules.equality import (
    check_eq_hash_pairing,
)
from repostyle.rules.error_handling import (
    check_over_broad_except,
)
from repostyle.rules.filenames import (
    check_filename_casing,
    check_filename_extension,
)
from repostyle.rules.idioms import (
    check_range_len_reindex,
)
from repostyle.rules.import_layering import (
    check_banned_import_by_path,
)
from repostyle.rules.layout import (
    check_class_member_order,
    check_module_element_order,
)
from repostyle.rules.logging_phi import (
    check_no_phi_safe_with_exc_info,
)
from repostyle.rules.module_size import (
    check_source_module_size,
)
from repostyle.rules.naming import (
    check_acronym_casing,
    check_banned_abbreviation,
    check_boolean_prefix_required,
    check_discouraged_class_suffix,
    check_exception_alias,
    check_gcp_bare_identifier,
    check_no_make_in_production,
    check_no_negated_boolean,
    check_predicate_function_naming,
)
from repostyle.rules.ports import (
    check_port_no_implementation,
)
from repostyle.rules.signatures import (
    check_too_many_positional_args,
)

RULES = {
    RS_ACRONYM_CASING: (check_acronym_casing,),
    RS_PORT_NO_IMPLEMENTATION: (check_port_no_implementation,),
    RS_DURATION_AS_TIMEDELTA: (check_duration_as_timedelta,),
    RS_NO_PHI_SAFE_EXC_INFO: (check_no_phi_safe_with_exc_info,),
    RS_BANNED_ABBREVIATION: (check_banned_abbreviation,),
    RS_DISCOURAGED_CLASS_SUFFIX: (check_discouraged_class_suffix,),
    RS_NO_NEGATED_BOOLEAN: (check_no_negated_boolean,),
    RS_BOOLEAN_PREFIX_REQUIRED: (check_boolean_prefix_required,),
    RS_NO_MAKE_IN_PRODUCTION: (check_no_make_in_production,),
    RS_GCP_BARE_IDENTIFIER: (check_gcp_bare_identifier,),
    RS_COGNITIVE_COMPLEXITY: (check_cognitive_complexity,),
    RS_SOURCE_MODULE_SIZE: (check_source_module_size,),
    RS_BANNED_IMPORT_BY_PATH: (check_banned_import_by_path,),
    RS_ELEMENT_ORDER: (check_module_element_order, check_class_member_order),
    RS_IMPERATIVE_DOCSTRING_OPENING: (check_imperative_docstring_opening,),
    RS_TOO_MANY_POSITIONAL_ARGS: (check_too_many_positional_args,),
    RS_EXCEPTION_ALIAS: (check_exception_alias,),
    RS_FILENAME_CONVENTION: (check_filename_extension, check_filename_casing),
    RS_DEEPLY_NESTED_TYPE: (check_deeply_nested_type,),
    RS_EQ_HASH_PAIRING: (check_eq_hash_pairing,),
    RS_PREDICATE_FUNCTION_NAMING: (check_predicate_function_naming,),
    RS_RANGE_LEN_REINDEX: (check_range_len_reindex,),
    RS_PRIVATE_IMPORT: (check_private_import,),
    RS_OVER_BROAD_EXCEPT: (check_over_broad_except,),
}
