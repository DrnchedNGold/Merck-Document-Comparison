"""Engine package for document comparison components."""

from .contracts import (
    ALLOWED_DIFF_OPS,
    DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    BodyIR,
    BodyParagraph,
    BodyRun,
    CompareConfig,
    DiffOp,
    validate_body_ir,
    validate_compare_config,
    validate_diff_ops,
)

__all__ = [
    "ALLOWED_DIFF_OPS",
    "DEFAULT_WORD_LIKE_COMPARE_CONFIG",
    "BodyIR",
    "BodyParagraph",
    "BodyRun",
    "CompareConfig",
    "DiffOp",
    "validate_body_ir",
    "validate_compare_config",
    "validate_diff_ops",
]
