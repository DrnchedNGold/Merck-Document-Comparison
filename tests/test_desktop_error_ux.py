from __future__ import annotations

from desktop.error_ux import (
    EXIT_COMPARE_RUN,
    EXIT_DOCUMENT_STRUCTURE,
    EXIT_PREFLIGHT,
    EXIT_USAGE,
    describe_compare_failure,
)


def test_describe_compare_failure_usage_mentions_profile_and_details() -> None:
    ux = describe_compare_failure(
        returncode=EXIT_USAGE,
        stderr="Invalid JSON in --config: Expecting property name enclosed in double quotes",
    )
    assert "Invalid settings" in ux.headline
    assert "profile" in ux.message.lower() or "settings" in ux.message.lower()
    assert "Invalid JSON" in ux.details


def test_describe_compare_failure_preflight_mentions_track_changes() -> None:
    ux = describe_compare_failure(
        returncode=EXIT_PREFLIGHT,
        stderr="Tracked changes detected in source document",
    )
    assert "eligible" in ux.headline.lower()
    assert "track changes" in ux.message.lower()


def test_describe_compare_failure_document_structure_mentions_resave() -> None:
    ux = describe_compare_failure(
        returncode=EXIT_DOCUMENT_STRUCTURE,
        stderr="Missing word/document.xml",
    )
    assert "structure" in ux.headline.lower()
    msg = ux.message.lower()
    assert ("re-saving" in msg) or ("re-save" in msg) or ("resav" in msg)


def test_describe_compare_failure_compare_run_has_generic_failure() -> None:
    ux = describe_compare_failure(returncode=EXIT_COMPARE_RUN, stderr="I/O error")
    assert "failed" in ux.headline.lower()
    assert "error" in ux.message.lower()


def test_describe_compare_failure_unknown_exit_code_includes_code() -> None:
    ux = describe_compare_failure(returncode=99, stderr="")
    assert "99" in ux.message
    assert "99" in ux.details

