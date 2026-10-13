"""Offline tests must never inherit an operator's live model credentials/config."""
import os

import pytest


@pytest.fixture(autouse=True)
def isolated_model_environment(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith(("CONSENSUS_LLM_", "OPENAI_", "ANTHROPIC_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("CONSENSUS_LLM_ENABLED", "false")
    monkeypatch.setattr("system.services.llm.default_env_path", lambda: tmp_path / "absent-model.env")
    monkeypatch.setattr("system.services.github.default_env_path", lambda: tmp_path / "absent-github.env")
    yield
    # load_dotenv adds keys without going through monkeypatch. Remove fixture
    # values before monkeypatch restores the original operator environment.
    for name in list(os.environ):
        if name.startswith(("CONSENSUS_LLM_", "OPENAI_", "ANTHROPIC_")):
            os.environ.pop(name, None)
