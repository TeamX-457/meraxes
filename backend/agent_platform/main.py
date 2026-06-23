"""Backward-compatible entry — delegates to Meraxes v1 agent optimizer."""

import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parent.parent / "v1_classic_ai"
sys.path.insert(0, str(V1_ROOT))

from meraxes_agent.main import app  # noqa: E402, F401
