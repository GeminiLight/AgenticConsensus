import importlib.util
from pathlib import Path


def test_bundled_git_has_a_minimal_nonsecret_environment(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "system/services/runtime_tools.py"
    assert path.exists(), "Vercel needs an explicit bundled Git runtime"
    spec = importlib.util.spec_from_file_location("runtime_tools", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "BUNDLED_GIT", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "not-for-git-subprocesses")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/git").touch()
    assert module.git_executable() == str(tmp_path / "bin/git")
    environment = module.git_environment()
    assert environment["GIT_EXEC_PATH"] == str(tmp_path / "bin")
    assert environment["LD_LIBRARY_PATH"] == str(tmp_path / "lib")
    assert "OPENAI_API_KEY" not in environment
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"


def test_packaging_uses_only_build_image_dependencies():
    path = Path(__file__).resolve().parents[1] / "system/prepare_vercel_runtime.py"
    assert path.exists(), "The deploy must bundle Git and its linked libraries"
    spec = importlib.util.spec_from_file_location("runtime_packager", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    libraries = module.linked_libraries("libpcre2-8.so.0 => /lib/libpcre2-8.so.0 (0xabc)\nlibc.so.6 => /lib/libc.so.6 (0xdef)\n/lib64/ld-linux-x86-64.so.2 (0xff)")
    assert libraries == [Path("/lib/libpcre2-8.so.0")]
