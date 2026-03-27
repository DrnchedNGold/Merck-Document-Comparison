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
from .docx_body_ingest import DocumentXmlMissingError, parse_docx_body_ir
from .preflight_validation import (
    CommentsDetectedError,
    InvalidDocxFileTypeError,
    InvalidDocxZipFileError,
    PreflightValidationError,
    TrackedChangesDetectedError,
    validate_docx_for_preflight,
)

__all__ = [
    "ALLOWED_DIFF_OPS",
    "DEFAULT_WORD_LIKE_COMPARE_CONFIG",
    "BodyIR",
    "BodyParagraph",
    "BodyRun",
    "CompareConfig",
    "DiffOp",
    "DocumentXmlMissingError",
    "parse_docx_body_ir",
    "validate_body_ir",
    "validate_compare_config",
    "validate_diff_ops",
    "validate_docx_for_preflight",
    "PreflightValidationError",
    "InvalidDocxFileTypeError",
    "InvalidDocxZipFileError",
    "TrackedChangesDetectedError",
    "CommentsDetectedError",
]
