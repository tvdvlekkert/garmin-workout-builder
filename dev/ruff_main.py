"""Bazel launcher for ruff: the wheel has no console entry point, so exec the
bundled binary at <wheel_repo>/bin/ruff, resolved relative to the ruff package.
"""

import os
import sys
from pathlib import Path

import ruff

ruff_bin = Path(ruff.__file__).parents[2] / "bin" / "ruff"
os.execv(ruff_bin, ["ruff", *sys.argv[1:]])
