"""SCRUM-83 / SCRUM-86: run the engine compare CLI as a subprocess (stable for the desktop shell)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def default_repo_root() -> Path:
    """Parent of ``desktop/`` (repository root)."""
    return Path(__file__).resolve().parents[1]


def build_compare_command(
    original: str,
    revised: str,
    output: str,
    *,
    config_path: str | None = None,
    repo_root: Path | None = None,
) -> tuple[list[str], dict[str, str], Path]:
    root = repo_root or default_repo_root()
    cmd = [
        sys.executable,
        "-m",
        "engine.compare_cli",
        "--original",
        original,
        "--revised",
        revised,
        "--output",
        output,
    ]
    if config_path:
        cmd.extend(["--config", config_path])
    env = {**os.environ, "PYTHONPATH": str(root)}
    return cmd, env, root


def run_compare_subprocess(
    original: str,
    revised: str,
    output: str,
    *,
    config_path: str | None = None,
    repo_root: Path | None = None,
    timeout_sec: float = 600,
) -> subprocess.CompletedProcess[str]:
    cmd, env, root = build_compare_command(
        original,
        revised,
        output,
        config_path=config_path,
        repo_root=repo_root,
    )
    logger.info(
        "Starting engine compare: original=%s revised=%s output=%s",
        Path(original).name,
        Path(revised).name,
        Path(output).name,
    )
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode == 0:
        logger.info("Engine compare succeeded.")
    else:
        stderr = (proc.stderr or "").strip()
        snippet = stderr.splitlines()[0] if stderr else ""
        logger.warning("Engine compare failed: exit_code=%s stderr_first_line=%r", proc.returncode, snippet)
    return proc


def open_path_with_default_app(path: Path) -> str | None:
    """Open a file with the OS default handler. Returns an error message on failure, else None."""
    p = str(path.resolve())
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", p], check=False, capture_output=True)
        elif sys.platform == "win32":
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", p], check=False, capture_output=True)
    except OSError as e:
        return str(e)
    return None
