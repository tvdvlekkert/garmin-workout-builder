"""Bazel launcher for ruff.

ruff's wheel ships the compiled binary as a data script (no console entry point),
and its own find_ruff_bin() only checks sysconfig/site-packages paths that don't
exist under Bazel's runfiles. rules_python drops the binary at
<wheel_repo>/bin/ruff -- two dirs above the ruff package -- so resolve it relative
to the imported module rather than hardcoding the platform-specific repo name.
"""

import os
import sys
from pathlib import Path

import ruff

ruff_bin = Path(ruff.__file__).parents[2] / "bin" / "ruff"
os.execv(ruff_bin, ["ruff", *sys.argv[1:]])
