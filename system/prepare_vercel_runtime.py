"""Package Git from the Linux build image for the isolated, local-only paper case.

No downloaded executable, provider credential, shell wrapper, or network Git
helper is included. The function runtime supplies glibc and its dynamic loader.
"""
from pathlib import Path
import platform
import re
import shutil
import subprocess


def linked_libraries(output: str) -> list[Path]:
    libraries = []
    for line in output.splitlines():
        match = re.search(r"=>\s+(/\S+)", line)
        if match:
            path = Path(match.group(1))
            if not re.match(r"lib(c|m|pthread|dl|rt|resolv)\.so", path.name):
                libraries.append(path)
    return libraries


def main():
    if platform.system() != "Linux":
        raise RuntimeError("Package the runtime on Vercel's Linux build image")
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is missing from the build image")
    root = Path(__file__).parent / "assets" / "git-runtime"
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "lib").mkdir(exist_ok=True)
    for name in ("git", "git-upload-pack", "git-index-pack", "git-receive-pack"):
        destination = root / "bin" / name
        shutil.copy2(git, destination)
        destination.chmod(0o755)
    pending = [Path(git)]
    seen = set()
    while pending:
        binary = pending.pop()
        result = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=True, timeout=20)
        if "not found" in result.stdout:
            raise RuntimeError("A Git runtime library is missing")
        for library in linked_libraries(result.stdout):
            if library.name not in seen:
                seen.add(library.name)
                shutil.copy2(library, root / "lib" / library.name)
                pending.append(library)
    print(f"Bundled Git and {len(seen)} linked libraries for the paper demo")


if __name__ == "__main__":
    main()
