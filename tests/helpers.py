import subprocess
from pathlib import Path


def run(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, message: str) -> str:
    run(repo, "git", "add", ".")
    run(repo, "git", "commit", "-m", message)
    return run(repo, "git", "rev-parse", "HEAD")


def create_billing_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "billing-repo"
    repo.mkdir()
    run(repo, "git", "init", "-q")
    run(repo, "git", "config", "user.email", "test@example.test")
    run(repo, "git", "config", "user.name", "Test")
    (repo / "legacy").mkdir()
    (repo / "legacy" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "legacy" / "billing.py").write_text("RATE = 2\n", encoding="utf-8")
    (repo / "checkout.py").write_text("def total(value):\n    return value * 2\n", encoding="utf-8")
    (repo / "test_checkout.py").write_text(
        "import unittest\nfrom checkout import total\n\n"
        "class CheckoutTest(unittest.TestCase):\n"
        "    def test_total(self):\n        self.assertEqual(total(3), 6)\n",
        encoding="utf-8",
    )
    base = commit(repo, "base architecture")
    (repo / "checkout.py").write_text(
        "from legacy.billing import RATE\n\ndef total(value):\n    return value * RATE\n", encoding="utf-8"
    )
    target = commit(repo, "agent patch with legacy dependency")
    return repo, base, target


def create_alternate_target(repo: Path, base: str, *, path: str, content: str, message: str) -> str:
    """Create a second proposal from the same base without relying on a branch name."""
    run(repo, "git", "checkout", "-q", "--detach", base)
    target_path = repo / path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return commit(repo, message)


def create_capability_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "capability-repo"
    repo.mkdir()
    run(repo, "git", "init", "-q")
    run(repo, "git", "config", "user.email", "test@example.test")
    run(repo, "git", "config", "user.name", "Test")
    (repo / "security").mkdir()
    (repo / "security" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "security" / "task_scope.py").write_text(
        "def get_task_token(task_id):\n    return f'task:{task_id}'\n", encoding="utf-8"
    )
    (repo / "connector_registry.py").write_text(
        "PROVIDERS = {'calendar': 'security.task_scope'}\n", encoding="utf-8"
    )
    (repo / "test_registry.py").write_text(
        "import unittest\nfrom connector_registry import PROVIDERS\n\n"
        "class RegistryTest(unittest.TestCase):\n"
        "    def test_calendar_provider(self):\n"
        "        self.assertEqual(PROVIDERS['calendar'], 'security.task_scope')\n",
        encoding="utf-8",
    )
    base = commit(repo, "base: task-scoped capability policy")
    (repo / "connectors").mkdir()
    (repo / "connectors" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "connectors" / "archive.py").write_text(
        "from importlib import import_module\n\n"
        "def load_provider(provider_name):\n"
        "    return import_module(provider_name)\n",
        encoding="utf-8",
    )
    (repo / "connector_registry.py").write_text(
        "PROVIDERS = {\n"
        "    'calendar': 'security.task_scope',\n"
        "    'archive': 'legacy.workspace_credentials',\n"
        "}\n",
        encoding="utf-8",
    )
    target = commit(repo, "agent patch: add archive connector through configured provider")
    return repo, base, target
