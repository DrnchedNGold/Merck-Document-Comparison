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
