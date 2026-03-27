import json
from pathlib import Path

from engine.contracts import (
    DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    validate_body_ir,
    validate_compare_config,
    validate_diff_ops,
)


def _load_contract_fixture() -> dict:
    root = Path(__file__).resolve().parents[1]
    fixture_path = root / "tests" / "fixtures" / "engine_contract_fixture.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_contract_fixture_payloads_pass_validation() -> None:
    fixture = _load_contract_fixture()

    assert validate_body_ir(fixture["original_body_ir"]) == []
    assert validate_body_ir(fixture["revised_body_ir"]) == []
    assert validate_compare_config(fixture["compare_config"]) == []
    assert validate_diff_ops(fixture["expected_diff_ops"]) == []


def test_compare_config_matches_default_word_like_stub() -> None:
    fixture = _load_contract_fixture()
    assert fixture["compare_config"] == DEFAULT_WORD_LIKE_COMPARE_CONFIG


def test_diff_op_contract_rejects_unknown_op() -> None:
    fixture = _load_contract_fixture()
    invalid_diff_ops = [*fixture["expected_diff_ops"]]
    invalid_diff_ops[0] = {**invalid_diff_ops[0], "op": "move"}

    errors = validate_diff_ops(invalid_diff_ops)
    assert any("unsupported op" in error for error in errors)


def test_validate_body_ir_rejects_wrong_version() -> None:
    errors = validate_body_ir({"version": 2, "blocks": []})  # type: ignore[arg-type]
    assert any("version must be 1" in e for e in errors)


def test_validate_body_ir_rejects_non_list_blocks() -> None:
    errors = validate_body_ir({"version": 1, "blocks": "not-a-list"})  # type: ignore[arg-type]
    assert any("blocks must be a list" in e for e in errors)


def test_validate_body_ir_rejects_bad_paragraph_type() -> None:
    body_ir = {
        "version": 1,
        "blocks": [{"type": "table", "id": "t1", "runs": []}],
    }
    errors = validate_body_ir(body_ir)  # type: ignore[arg-type]
    assert any("type='paragraph'" in e for e in errors)


def test_validate_body_ir_rejects_empty_paragraph_id() -> None:
    body_ir = {
        "version": 1,
        "blocks": [{"type": "paragraph", "id": "", "runs": [{"text": "x"}]}],
    }
    errors = validate_body_ir(body_ir)
    assert any("non-empty string id" in e for e in errors)


def test_validate_compare_config_rejects_missing_field() -> None:
    partial = {k: v for k, v in DEFAULT_WORD_LIKE_COMPARE_CONFIG.items() if k != "ignore_case"}
    errors = validate_compare_config(partial)  # type: ignore[arg-type]
    assert any("missing required field 'ignore_case'" in e for e in errors)


def test_validate_compare_config_rejects_non_bool_field() -> None:
    bad = {**DEFAULT_WORD_LIKE_COMPARE_CONFIG, "ignore_case": "yes"}  # type: ignore[dict-item]
    errors = validate_compare_config(bad)  # type: ignore[arg-type]
    assert any("'ignore_case' must be bool" in e for e in errors)


def test_validate_diff_ops_rejects_invalid_path() -> None:
    errors = validate_diff_ops([{"op": "insert", "path": "", "before": None, "after": "x"}])
    assert any("path must be a non-empty string" in e for e in errors)
