def test_placeholder_passes() -> None:
    """Placeholder test to keep the baseline CI green."""
    assert True


def test_monorepo_scaffold_exists() -> None:
    """Baseline scaffold directories required by SCRUM-20."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert (root / "engine").is_dir()
    assert (root / "desktop").is_dir()
    assert (root / "tests").is_dir()


def test_readme_has_install_and_test_instructions() -> None:
    """README must include dependency install and test run docs."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "Install deps and run tests" in readme
    assert "pytest" in readme
