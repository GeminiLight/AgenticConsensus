"""Copy persisted governed records into a fresh local preview.

Preserve repository paths, revisions, evidence and audit records. Exclude account
credentials and sessions. The source is read-only; existing outputs are refused.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system.services.database import Database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError("Choose a fresh preview database; existing data is preserved.")
    destination = Database(output)
    tables = ("projects", "reviews", "intents", "audit_events", "project_audit_events")
    counts = {}
    with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as original:
        with destination.connect() as preview:
            for table in tables:
                cursor = original.execute(f'SELECT * FROM "{table}"')
                columns = [item[0] for item in cursor.description]
                rows = cursor.fetchall()
                placeholders = ",".join("?" for _ in columns)
                names = ",".join(f'"{name}"' for name in columns)
                preview.executemany(f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', rows)
                counts[table] = len(rows)
    print(json.dumps({"database":str(output), "copied_records":counts,
                      "source_read_only":True, "credentials_copied":False}, indent=2))


if __name__ == "__main__":
    main()
