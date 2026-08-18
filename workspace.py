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
    # Anchor at this file's directory so we find the repo containing the
    # source, not whatever cwd happens to be. check=True raises if we're not
    # in a git repo -- a loud failure beats resolving paths against a guess.
    top = subprocess.run(
        ["git", "-C", str(Path(__file__).parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(top)
