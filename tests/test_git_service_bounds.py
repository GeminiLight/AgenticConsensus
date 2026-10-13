from pathlib import Path

from system.services.git_service import GitRepository
from tests.helpers import create_alternate_target, create_billing_repo


def test_tracked_paths_stops_after_the_extra_truncation_record(tmp_path: Path):
    repo, base, _target = create_billing_repo(tmp_path)

    revision, paths, truncated = GitRepository(repo).tracked_paths(base, max_entries=2)

    assert revision == base
    assert paths == ["checkout.py", "legacy/__init__.py"]
    assert truncated is True


def test_diff_returns_only_the_requested_character_budget(tmp_path: Path):
    repo, base, _target = create_billing_repo(tmp_path)
    target = create_alternate_target(
        repo,
        base,
        path="large.py",
        content="VALUE = '" + ("学" * 20_000) + "'\n",
        message="large bounded diff",
    )

    diff = GitRepository(repo).diff(base, target, max_chars=257)

    assert len(diff) == 257
    assert diff.startswith("diff --git")
