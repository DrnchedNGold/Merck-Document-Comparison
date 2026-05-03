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


def test_readme_lists_project_setup_dependencies() -> None:
    """README should provide setup prerequisites for teammates."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "Project setup dependencies and tools" in readme
    assert "Python 3.12 or newer" in readme
    assert "Docker" in readme
