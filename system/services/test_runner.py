from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from system.domain.models import Evidence
from system.services.runtime_tools import git_environment, git_executable


_ALLOWED_EXECUTABLES = {"python", "python3", "pytest", "uv", "npm", "pnpm", "cargo", "go"}


def run_tests(
    repo_path: str | Path,
    command: list[str],
    *,
    target_ref: str,
    timeout_seconds: int = 60,
) -> Evidence:
    if not command:
        return Evidence(kind="tests", status="not_run", summary="No test command is allowlisted for this project")
    executable = Path(command[0]).name
    if executable not in _ALLOWED_EXECUTABLES or command[0] != executable:
        return Evidence(
            kind="tests",
            status="fail",
            summary=f"Test executable is not allowlisted: {executable}",
        )
    if any("\x00" in token or len(token) > 500 for token in command):
        return Evidence(kind="tests", status="fail", summary="Test command contains an invalid token")

    safe_path = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    try:
        with tempfile.TemporaryDirectory(prefix="agentic-consensus-test-") as temporary:
            sandbox = Path(temporary) / "repository"
            clone = subprocess.run(
                [git_executable(), "clone", "--quiet", "--no-hardlinks", str(Path(repo_path).resolve()), str(sandbox)],
                capture_output=True,
                text=True,
                timeout=min(timeout_seconds, 30),
                env=git_environment(safe_path),
            )
            if clone.returncode != 0:
                return Evidence(kind="tests", status="fail", summary="Could not create an isolated test checkout")
            checkout = subprocess.run(
                [git_executable(), "checkout", "--quiet", "--detach", target_ref],
                cwd=sandbox,
                capture_output=True,
                text=True,
                timeout=min(timeout_seconds, 30),
                env=git_environment(safe_path),
            )
            if checkout.returncode != 0:
                return Evidence(kind="tests", status="fail", summary="Could not check out the target revision")
            result = subprocess.run(
                command,
                cwd=sandbox,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env={"PATH": safe_path, "LANG": "C.UTF-8", "PYTHONPATH": ""},
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Evidence(kind="tests", status="fail", summary=f"Test execution failed: {type(exc).__name__}")

    combined = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())[-8000:]
    status = "pass" if result.returncode == 0 else "fail"
    summary = f"Test command exited {result.returncode}"
    return Evidence(
        kind="tests",
        status=status,
        summary=summary,
        details={"command": command, "target_ref": target_ref, "exit_code": result.returncode, "output": combined},
    )
