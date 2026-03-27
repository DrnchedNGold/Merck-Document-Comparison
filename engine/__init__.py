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
from .compare_keys import (
    CompareKey,
    align_runs_by_compare_keys,
    generate_compare_keys,
)
from .paragraph_alignment import ParagraphAlignment, align_paragraphs
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
    "CompareKey",
    "parse_docx_body_ir",
    "generate_compare_keys",
    "align_runs_by_compare_keys",
    "ParagraphAlignment",
    "align_paragraphs",
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
