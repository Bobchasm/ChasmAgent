from __future__ import annotations

import subprocess
from pathlib import Path

from ..utils import truncate_text


def run_command(root: Path, command: str, timeout: int = 120) -> str:
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

