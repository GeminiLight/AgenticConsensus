from pathlib import Path
from importlib.metadata import version
import tomllib

import yaml

from system import __version__
from system.check import run_checks
from system.paths import runtime_root


ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_stays_in_sync():
    package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((ROOT / "system.yaml").read_text(encoding="utf-8"))

    assert __version__ == "0.22.3"
    assert package["project"]["version"] == __version__
    assert manifest["version"] == __version__
    assert version("agentic-consensus") == __version__


def test_local_secret_file_is_ignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignored


def test_vercel_points_to_the_exported_fastapi_application():
    package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert package["tool"]["vercel"]["entrypoint"] == "system.web.app:app"


def test_vercel_has_a_recognized_root_fastapi_entrypoint():
    entrypoint = ROOT / "app.py"

    assert entrypoint.is_file()
    assert entrypoint.read_text(encoding="utf-8") == (
        "from system.web.app import app\n\n__all__ = [\"app\"]\n"
    )


def test_github_release_contract_is_complete():
    required = [
        "CHANGELOG.md",
        ".env.example",
        ".github/workflows/ci.yml",
        ".github/dependabot.yml",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/pull_request_template.md",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "SECURITY.md",
        "docs/architecture.md",
        "docs/user-journeys.md",
    ]
    for relative_path in required:
        assert (ROOT / relative_path).is_file(), relative_path

    package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert package["project"]["readme"] == "README.md"
    assert package["project"]["license"] == {"file": "LICENSE"}

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'python-version: ["3.11", "3.12", "3.13"]' in workflow
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "actions/upload-artifact" not in workflow
    assert "python -m pytest" in workflow
    assert "python -m build" in workflow

    dependabot = (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    assert "dependency-name: pytest" in dependabot
    assert "dependency-name: pytest-cov" in dependabot
    assert "version-update:semver-major" in dependabot

    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=" in example
    assert "ANTHROPIC_API_KEY=" in example
    assert "sk-" not in example

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "git clone https://github.com/GeminiLight/AgenticConsensus.git" in readme
    assert "Apache-2.0" in readme


def test_installed_runtime_uses_working_directory_or_explicit_home(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AGENTIC_CONSENSUS_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    assert runtime_root() == tmp_path.resolve()
    assert run_checks(tmp_path / "fresh.db")["configuration"] == "ok"

    explicit_home = tmp_path / "product-home"
    monkeypatch.setenv("AGENTIC_CONSENSUS_HOME", str(explicit_home))
    assert runtime_root() == explicit_home.resolve()
