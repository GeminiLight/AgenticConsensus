from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml

from system.paths import default_database_path, runtime_root
from system.services.database import Database
from system.services.llm import LLMConfig


def run_checks(database_path: Path) -> dict:
    runtime_path = runtime_root() / "runtime.yaml"
    runtime = (
        yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
        if runtime_path.is_file()
        else {"server": {"host": "127.0.0.1"}}
    )
    llm = LLMConfig.from_env()
    checks = {
        "configuration": "ok" if runtime.get("server", {}).get("host") == "127.0.0.1" else "warning",
        "database": Database(database_path).health(),
        "git": "ok" if shutil.which("git") else "missing",
        "model": llm.runtime_status(),
    }
    checks["status"] = "ok" if checks["git"] == "ok" and checks["configuration"] == "ok" else "degraded"
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentic-consensus-check")
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args(argv)
    report = run_checks(args.database)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
