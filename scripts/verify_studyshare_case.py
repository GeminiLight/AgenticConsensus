"""Re-run real English fixture checks, including a counterfactual regression."""
import json
from pathlib import Path
import subprocess
import tempfile

from system.paper_demo import PROPOSAL, FIXED


def main():
    root = Path(__file__).resolve().parents[1]
    results = []
    with tempfile.TemporaryDirectory(prefix="studyshare-independent-") as directory:
        repo = Path(directory) / "repo"
        subprocess.run(["git", "clone", "--quiet", str(root / "system/assets/studyshare.bundle"), str(repo)], check=True)
        for ref in (PROPOSAL, FIXED):
            subprocess.run(["git", "checkout", "--quiet", "--detach", ref], cwd=repo, check=True)
            for label, command in [("repository suite", ["python3", "-m", "unittest", "-q"]),
                ("independent public-field checks", ["python3", str(root / "docs/qa/llm-user-journey-2026-10-13/verify_export.py"), str(repo)])]:
                run = subprocess.run(command, cwd=repo, capture_output=True, text=True)
                results.append({"revision":ref, "check":label, "exit_code":run.returncode, "output":run.stdout + run.stderr})
        fixed_tests = subprocess.check_output(["git", "show", f"{FIXED}:test_export.py"], cwd=repo, text=True)
        subprocess.run(["git", "checkout", "--quiet", "--detach", PROPOSAL], cwd=repo, check=True)
        # Execute the exact fixed test source against the unsafe checkout; no
        # source or Git history is changed.
        run = subprocess.run(["python3", "-c", fixed_tests + "\nunittest.main(verbosity=2)\n"], cwd=repo, capture_output=True, text=True)
        results.append({"revision":PROPOSAL, "check":"fixed regression against unsafe implementation", "exit_code":run.returncode, "output":run.stdout + run.stderr})
    assert [r["exit_code"] for r in results] == [0, 1, 0, 0, 1], [(r["check"], r["exit_code"]) for r in results]
    target = root / "docs/qa/vercel-paper-2026-10-13"
    target.mkdir(parents=True, exist_ok=True)
    (target / "independent-verification.json").write_text(json.dumps(results, indent=2) + "\n")
    for result in results:
        print(result["revision"][:8], result["check"], "exit", result["exit_code"])


if __name__ == "__main__":
    main()
