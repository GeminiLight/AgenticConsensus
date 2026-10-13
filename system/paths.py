from __future__ import annotations

import os
from pathlib import Path


def runtime_root() -> Path:
    """Return the operator-owned directory for config and mutable local data."""
    configured = os.environ.get("AGENTIC_CONSENSUS_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.cwd().resolve()


def default_database_path() -> Path:
    return runtime_root() / "var" / "agentic-consensus.db"


def default_demo_repo_path() -> Path:
    return runtime_root() / "var" / "demo-repo"


def default_env_path() -> Path:
    return runtime_root() / ".env"
