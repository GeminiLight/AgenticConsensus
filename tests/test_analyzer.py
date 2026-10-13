import subprocess
from pathlib import Path

from system.services.analyzer import analyze_python_imports
from system.services.git_service import GitRepository


def run(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, message: str) -> str:
    run(repo, "git", "add", ".")
    run(repo, "git", "commit", "-m", message)
    return run(repo, "git", "rev-parse", "HEAD")


def test_detects_only_new_forbidden_imports(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(repo, "git", "init", "-q")
    run(repo, "git", "config", "user.email", "test@example.test")
    run(repo, "git", "config", "user.name", "Test")
    (repo / "existing.py").write_text("import legacy.billing\n", encoding="utf-8")
    (repo / "checkout.py").write_text("def total():\n    return 1\n", encoding="utf-8")
    base = commit(repo, "base")

    (repo / "checkout.py").write_text("from legacy.billing import Invoice\n", encoding="utf-8")
    target = commit(repo, "agent patch")

    findings = analyze_python_imports(
        GitRepository(repo), base, target, rule_id="billing-boundary", forbidden_modules=["legacy.billing"]
    )
    forbidden = [item for item in findings if item.kind == "forbidden_dependency"]
    assert len(forbidden) == 1
    assert forbidden[0].path == "checkout.py"
    assert "existing.py" not in {item.path for item in forbidden}


def test_nonliteral_dynamic_import_is_unobservable(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(repo, "git", "init", "-q")
    run(repo, "git", "config", "user.email", "test@example.test")
    run(repo, "git", "config", "user.name", "Test")
    (repo / "plugin.py").write_text("def load(name):\n    return name\n", encoding="utf-8")
    base = commit(repo, "base")
    (repo / "plugin.py").write_text(
        "import importlib\n\ndef load(name):\n    return importlib.import_module(name)\n", encoding="utf-8"
    )
    target = commit(repo, "dynamic loader")

    findings = analyze_python_imports(
        GitRepository(repo), base, target, rule_id="billing-boundary", forbidden_modules=["legacy.billing"]
    )
    assert any(item.kind == "unobservable" and item.path == "plugin.py" for item in findings)


def test_from_import_and_aliased_dynamic_import_do_not_bypass_boundary(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(repo, "git", "init", "-q")
    run(repo, "git", "config", "user.email", "test@example.test")
    run(repo, "git", "config", "user.name", "Test")
    (repo / "checkout.py").write_text("def total():\n    return 1\n", encoding="utf-8")
    base = commit(repo, "base")
    (repo / "checkout.py").write_text(
        "from legacy import billing\n"
        "from importlib import import_module as load_module\n\n"
        "def load(name):\n    return load_module(name)\n",
        encoding="utf-8",
    )
    target = commit(repo, "bypass attempts")

    findings = analyze_python_imports(
        GitRepository(repo), base, target, rule_id="billing-boundary", forbidden_modules=["legacy.billing"]
    )
    assert any(item.kind == "forbidden_dependency" and item.details["module"] == "legacy.billing" for item in findings)
    assert any(item.kind == "unobservable" and item.line == 5 for item in findings)
