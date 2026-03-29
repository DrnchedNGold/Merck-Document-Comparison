"""SCRUM-91 / MDC-017: human-readable error UX for desktop + CLI contract mapping."""

from __future__ import annotations

from dataclasses import dataclass

# Exit code contract from engine.compare_cli (documented as stable in CLI --help).
EXIT_USAGE = 2
EXIT_PREFLIGHT = 10
EXIT_DOCUMENT_STRUCTURE = 11
EXIT_COMPARE_RUN = 12


@dataclass(frozen=True)
class CompareFailureUX:
    headline: str
    message: str
    details: str


def _clean_details(stderr: str | None, stdout: str | None) -> str:
    raw = (stderr or "").strip() or (stdout or "").strip()
    return raw


def describe_compare_failure(
    *,
    returncode: int,
    stderr: str | None = None,
    stdout: str | None = None,
) -> CompareFailureUX:
    details = _clean_details(stderr, stdout)

    if returncode == EXIT_USAGE:
        headline = "Invalid settings or usage"
        msg = (
            "The comparison could not start because the settings profile (JSON) or inputs were invalid.\n\n"
            "Try again with the default profile, or re-save the profile JSON.\n"
            "If the problem persists, share the Details text with support."
        )
    elif returncode == EXIT_PREFLIGHT:
        headline = "Input documents are not eligible for compare"
        msg = (
            "One of the selected documents was rejected by preflight validation.\n\n"
            "Common causes:\n"
            "- Not a .docx file, or the file is corrupted\n"
            "- The document already contains Track Changes or comments (v1 does not support this)\n\n"
            "Pick clean source documents and try again. Share Details if you need help."
        )
    elif returncode == EXIT_DOCUMENT_STRUCTURE:
        headline = "Document structure problem"
        msg = (
            "The document package or XML structure could not be read.\n\n"
            "Try opening the file in Word and re-saving as .docx, then retry.\n"
            "If it still fails, share the Details text with support."
        )
    elif returncode == EXIT_COMPARE_RUN:
        headline = "Comparison failed"
        msg = (
            "The engine encountered an error while generating the output document.\n\n"
            "Try again, and if it repeats, share the Details text with support."
        )
    else:
        headline = "Comparison failed"
        msg = f"The engine failed with exit code {returncode}. Share the Details text with support."

    if not details:
        details = f"(no engine output; exit code {returncode})"

    return CompareFailureUX(headline=headline, message=msg, details=details)

