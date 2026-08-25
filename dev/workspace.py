"""Locating the repo root, regardless of how a script is launched.

  1. BUILD_WORKSPACE_DIRECTORY -- set by `bazel run`, points at the repo root.
  2. `git rev-parse --show-toplevel` -- for direct (non-Bazel) dev runs.

No relative-path fallback: if neither is available we raise rather than guess.
"""

import os
import subprocess
from pathlib import Path


def workspace_root():
    env = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if env:
        return Path(env)
    return Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
