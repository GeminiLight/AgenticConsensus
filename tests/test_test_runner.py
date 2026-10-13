from pathlib import Path

from system.services.test_runner import run_tests
from tests.helpers import create_billing_repo


def test_test_executable_must_be_an_allowlisted_command_name(tmp_path: Path):
    repo, _, target = create_billing_repo(tmp_path)
    result = run_tests(repo, ["/tmp/untrusted/python3", "-m", "unittest"], target_ref=target)
    assert result.status == "fail"
    assert "allowlisted" in result.summary
