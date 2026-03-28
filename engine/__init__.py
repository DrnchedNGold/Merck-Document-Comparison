"""Engine package for document comparison components."""

from .contracts import (
    ALLOWED_DIFF_OPS,
    DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    BodyIR,
    BodyParagraph,
    BodyRun,
    BodyTable,
    BodyTableCell,
    CompareConfig,
    DiffOp,
    validate_body_ir,
    validate_compare_config,
    validate_diff_ops,
)
from .docx_body_ingest import (
    DocumentXmlMissingError,
    parse_docx_body_ir,
    parse_structural_blocks_from_element,
)
from .compare_keys import (
    CompareKey,
    align_runs_by_compare_keys,
    generate_compare_keys,
)
from .body_compare import (
    MatchedParagraphDiff,
    matched_document_package_inline_diffs,
    matched_paragraph_inline_diffs,
    single_paragraph_body,
)
from .body_revision_emit import (
    apply_body_track_changes_to_document_root,
    apply_track_changes_to_hdr_ftr_root,
    build_paragraph_track_change_elements,
    emit_docx_with_body_track_changes,
    emit_docx_with_package_track_changes,
)
from .document_package import DocumentPackageIR, parse_docx_document_package
from .docx_output_package import write_docx_copy_with_part_replacements
from .docx_package_parts import DOCUMENT_PART_PATH, discover_header_footer_part_paths
from .inline_run_diff import inline_diff_single_paragraph
from .paragraph_alignment import ParagraphAlignment, align_paragraphs
from .table_diff import diff_table_blocks
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
    "BodyTable",
    "BodyTableCell",
    "CompareConfig",
    "DiffOp",
    "DocumentXmlMissingError",
    "CompareKey",
    "parse_docx_body_ir",
    "parse_structural_blocks_from_element",
    "DocumentPackageIR",
    "parse_docx_document_package",
    "DOCUMENT_PART_PATH",
    "discover_header_footer_part_paths",
    "apply_body_track_changes_to_document_root",
    "apply_track_changes_to_hdr_ftr_root",
    "build_paragraph_track_change_elements",
    "emit_docx_with_body_track_changes",
    "emit_docx_with_package_track_changes",
    "matched_document_package_inline_diffs",
    "generate_compare_keys",
    "align_runs_by_compare_keys",
    "ParagraphAlignment",
    "align_paragraphs",
    "diff_table_blocks",
    "inline_diff_single_paragraph",
    "MatchedParagraphDiff",
    "matched_paragraph_inline_diffs",
    "single_paragraph_body",
    "validate_body_ir",
    "validate_compare_config",
    "validate_diff_ops",
    "validate_docx_for_preflight",
    "write_docx_copy_with_part_replacements",
    "PreflightValidationError",
    "InvalidDocxFileTypeError",
    "InvalidDocxZipFileError",
    "TrackedChangesDetectedError",
    "CommentsDetectedError",
]
