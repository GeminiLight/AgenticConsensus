"""Use the deployment's bundled Git without leaking service credentials to children."""
from pathlib import Path

BUNDLED_GIT = Path(__file__).resolve().parents[1] / "assets" / "git-runtime"


def git_executable() -> str:
    executable = BUNDLED_GIT / "bin" / "git"
    return str(executable) if executable.is_file() else "git"


def git_environment(path: str = "/usr/bin:/bin:/usr/sbin:/sbin") -> dict[str, str]:
    environment = {"PATH": path, "LANG": "C.UTF-8", "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"}
    if (BUNDLED_GIT / "bin" / "git").is_file():
        environment.update(PATH=f"{BUNDLED_GIT / 'bin'}:{path}",
            GIT_EXEC_PATH=str(BUNDLED_GIT / "bin"), LD_LIBRARY_PATH=str(BUNDLED_GIT / "lib"))
    return environment
