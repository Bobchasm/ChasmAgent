from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..utils import truncate_text


def run_command(root: Path, command: str, timeout: int = 120) -> str:
    # basic safety checks to avoid destructive operations
    danger_patterns = [r"\brm\s+-rf\b", r"\bsudo\b", r"\bmkfs\b", r"\bdd\b", r"\bshutdown\b", r"\breboot\b", r"\bsystemctl\b"]
    for p in danger_patterns:
        if re.search(p, command):
            raise ValueError("refused to run potentially dangerous command")

    proc = subprocess.run(
        command,
        cwd=root,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    stdout = truncate_text(proc.stdout or "", 8000)
    stderr = truncate_text(proc.stderr or "", 5000)
    return (
        f"exit_code={proc.returncode}\n"
        f"stdout:\n{stdout}\n"
        f"stderr:\n{stderr}"
    )

