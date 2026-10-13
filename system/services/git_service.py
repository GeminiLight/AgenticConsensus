from __future__ import annotations

import re
import selectors
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from system.services.runtime_tools import git_environment, git_executable


_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@+-]{0,199}$")


class GitError(RuntimeError):
    pass


@dataclass
class PhiArtifactResult:
    base_ref: str
    target_ref: str | None = None
    git_ref: str | None = None
    artifact_diff: str = ""
    failed_preconditions: list[str] = field(default_factory=list)


class GitRepository:
    def __init__(self, path: str | Path, timeout_seconds: int = 15):
        self.path = Path(path).expanduser().resolve()
        self.timeout_seconds = timeout_seconds
        if not self.path.is_dir():
            raise GitError(f"repository path does not exist: {self.path}")
        if not (self.path / ".git").exists():
            raise GitError(f"not a Git repository: {self.path}")

    def _run(self, *args: str, check: bool = True) -> str:
        return self._run_at(self.path, *args, check=check)

    def _run_at(self, cwd: Path, *args: str, check: bool = True) -> str:
        try:
            result = subprocess.run(
                [git_executable(), "--no-pager", *args],
                cwd=cwd,
                check=check,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=git_environment(),
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            stderr = getattr(exc, "stderr", "") or ""
            raise GitError(f"git command failed: {stderr.strip()[:300]}") from exc
        return result.stdout.strip()

    def _run_bounded(
        self,
        *args: str,
        max_bytes: int | None = None,
        max_records: int | None = None,
        record_separator: bytes = b"\0",
    ) -> tuple[str, bool]:
        """Stream bounded Git output and terminate once the requested limit is known."""
        if (max_bytes is None) == (max_records is None):
            raise ValueError("exactly one bounded-output limit is required")
        if max_bytes is not None and max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be positive")

        command = [git_executable(), "--no-pager", *args]
        process = subprocess.Popen(
            command,
            cwd=self.path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=git_environment(),
        )
        if process.stdout is None or process.stderr is None:
            process.kill()
            raise GitError("git command did not expose output streams")
        output = bytearray()
        stderr = bytearray()
        record_count = 0
        truncated = False
        deadline = time.monotonic() + self.timeout_seconds
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, self.timeout_seconds)
                events = selector.select(remaining)
                if not events:
                    raise subprocess.TimeoutExpired(command, self.timeout_seconds)
                for key, _mask in events:
                    chunk = key.fileobj.read1(16_384)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "stderr":
                        if len(stderr) < 4_096:
                            stderr.extend(chunk[: 4_096 - len(stderr)])
                        continue
                    output.extend(chunk)
                    if max_bytes is not None and len(output) >= max_bytes:
                        del output[max_bytes:]
                        truncated = True
                        break
                    if max_records is not None:
                        record_count += chunk.count(record_separator)
                        if record_count >= max_records:
                            position = -1
                            for _ in range(max_records):
                                position = output.find(record_separator, position + 1)
                            del output[position + len(record_separator) :]
                            truncated = True
                            break
                if truncated:
                    process.terminate()
                    break

            if truncated:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            else:
                remaining = max(deadline - time.monotonic(), 0.001)
                process.wait(timeout=remaining)
                if process.returncode:
                    message = stderr.decode("utf-8", errors="replace").strip()[:300]
                    raise GitError(f"git command failed: {message}")
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise GitError("git command failed: timed out") from exc
        finally:
            selector.close()
            process.stdout.close()
            process.stderr.close()
            if process.poll() is None:
                process.kill()
                process.wait()

        return output.decode("utf-8", errors="replace"), truncated

    @staticmethod
    def validate_ref(ref: str) -> str:
        if not _SAFE_REF.fullmatch(ref) or ref.startswith("-") or ".." in ref:
            raise GitError("invalid Git revision")
        return ref

    def resolve(self, ref: str) -> str:
        ref = self.validate_ref(ref)
        try:
            return self._run("rev-parse", "--verify", f"{ref}^{{commit}}")
        except GitError as exc:
            raise GitError(f"Git revision not found: {ref}") from exc

    def head(self) -> str:
        return self._run("rev-parse", "HEAD")

    def merge_base(self, left_ref: str, right_ref: str) -> str:
        left = self.resolve(left_ref)
        right = self.resolve(right_ref)
        try:
            return self._run("merge-base", left, right)
        except GitError as exc:
            raise GitError("Git revisions do not share a merge base") from exc

    def changed_python_files(self, base_ref: str, target_ref: str) -> list[str]:
        return [path for path in self.changed_files(base_ref, target_ref) if path.endswith(".py")]

    def changed_files(self, base_ref: str, target_ref: str) -> list[str]:
        base = self.resolve(base_ref)
        target = self.resolve(target_ref)
        output = self._run("diff", "--name-status", "--diff-filter=AMR", base, target)
        paths: list[str] = []
        for line in output.splitlines():
            fields = line.split("\t")
            if not fields:
                continue
            path = fields[-1]
            if not path.startswith("/") and ".." not in Path(path).parts:
                paths.append(path)
        return sorted(set(paths))

    def tracked_paths(
        self,
        ref: str,
        *,
        max_entries: int = 2_000,
    ) -> tuple[str, list[str], bool]:
        """Return repository-relative files tracked by one immutable Git snapshot."""
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        resolved = self.resolve(ref)
        output, truncated = self._run_bounded(
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            resolved,
            max_records=max_entries + 1,
        )
        paths = [
            path
            for path in output.split("\0")
            if path and not path.startswith("/") and ".." not in Path(path).parts
        ]
        return resolved, paths[:max_entries], truncated or len(paths) > max_entries

    def show(self, ref: str, path: str) -> str | None:
        resolved = self.resolve(ref)
        if path.startswith("/") or ".." in Path(path).parts:
            raise GitError("invalid repository-relative path")
        try:
            return self._run("show", f"{resolved}:{path}")
        except GitError:
            return None

    def snapshot_file(self, ref: str, path: str, *, byte_limit: int = 262_144) -> dict:
        """Read one exact tracked blob; never dereference links or read the checkout."""
        if (
            not path or len(path) > 1000 or "\\" in path
            or any(ord(char) < 32 for char in path)
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise ValueError("use an exact repository-relative file path")
        revision = self.resolve(ref)
        tree, _ = self._run_bounded(
            "ls-tree", "-z", "--full-tree", revision, "--", path, max_records=2,
        )
        records = [record for record in tree.split("\0") if record]
        if len(records) != 1 or "\t" not in records[0]:
            raise FileNotFoundError(path)
        metadata, name = records[0].split("\t", 1)
        mode, kind, object_id = metadata.split()
        if name != path or kind == "tree":
            raise FileNotFoundError(path)
        result = dict(revision=revision, path=path, object_id=object_id,
                      byte_size=None, byte_limit=byte_limit, content=None)
        if mode == "160000":
            return {**result, "status": "submodule"}
        size = int(self._run("cat-file", "-s", object_id))
        result["byte_size"] = size
        if mode == "120000":
            return {**result, "status": "symlink"}
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise FileNotFoundError(path)
        if size > byte_limit:
            return {**result, "status": "too_large"}
        try:
            raw = subprocess.run(
                [git_executable(), "--no-pager", "cat-file", "blob", object_id],
                cwd=self.path, capture_output=True, check=True,
                timeout=self.timeout_seconds,
                env=git_environment(),
            ).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise GitError("snapshot blob could not be read") from exc
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {**result, "status": "binary"}
        if any(ord(char) < 32 and char not in "\t\r\n" for char in content):
            return {**result, "status": "binary"}
        return {**result, "status": "text" if content else "empty", "content": content}

    def diff_stat(self, base_ref: str, target_ref: str) -> str:
        return self._run("diff", "--stat", self.resolve(base_ref), self.resolve(target_ref))

    def diff(self, base_ref: str, target_ref: str, max_chars: int | None = 60_000) -> str:
        base = self.resolve(base_ref)
        target = self.resolve(target_ref)
        if max_chars is None:
            return self._run("diff", "--unified=3", base, target)
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        value, _truncated = self._run_bounded(
            "diff",
            "--unified=3",
            base,
            target,
            max_bytes=(max_chars + 2) * 4,
        )
        return value.strip()[:max_chars]

    def delete_proposal_ref(self, git_ref: str, expected_target: str) -> bool:
        """Delete only this attempt's proposal ref, and only at its expected commit."""
        if not git_ref.startswith("refs/agentic-consensus/proposals/"):
            raise GitError("ref is outside the AgenticConsensus proposal namespace")
        validated_ref = self.validate_ref(git_ref)
        expected = self.resolve(expected_target)
        try:
            current = self.resolve(validated_ref)
        except GitError:
            return False
        if current != expected:
            return False
        self._run("update-ref", "-d", validated_ref, expected)
        return True

    def realize_python_import_substitution(
        self,
        base_ref: str,
        *,
        path: str,
        from_module: str,
        to_module: str,
        proposal_id: str,
    ) -> PhiArtifactResult:
        """Realize one local from-import substitution in an isolated Git worktree."""
        import ast

        base = self.resolve(base_ref)
        result = PhiArtifactResult(base_ref=base)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}", proposal_id):
            result.failed_preconditions.append("proposal ID cannot form a safe Git reference")
            return result
        source = self.show(base, path)
        if source is None:
            result.failed_preconditions.append(f"source path does not exist at the base revision: {path}")
            return result
        target_module_path = "/".join(to_module.split("."))
        if (
            self.show(base, f"{target_module_path}.py") is None
            and self.show(base, f"{target_module_path}/__init__.py") is None
        ):
            result.failed_preconditions.append(
                f"target module is not a local artifact at the base revision: {to_module}"
            )
            return result
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            result.failed_preconditions.append(
                f"source file is not valid Python at line {exc.lineno}: {exc.msg}"
            )
            return result
        matches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == from_module
        ]
        if len(matches) != 1:
            result.failed_preconditions.append(
                f"source import must occur exactly once as 'from {from_module} import ...'; observed {len(matches)}"
            )
            return result
        node = matches[0]
        if node.end_lineno != node.lineno:
            result.failed_preconditions.append("multi-line from imports are outside this Phi operator")
            return result
        lines = source.splitlines(keepends=True)
        line_index = node.lineno - 1
        before_token = f"from {from_module} import"
        after_token = f"from {to_module} import"
        if lines[line_index].count(before_token) != 1:
            result.failed_preconditions.append("source import text does not match its parsed structure")
            return result
        lines[line_index] = lines[line_index].replace(before_token, after_token, 1)
        updated_source = "".join(lines)
        try:
            ast.parse(updated_source)
        except SyntaxError as exc:
            result.failed_preconditions.append(
                f"realized source is not valid Python at line {exc.lineno}: {exc.msg}"
            )
            return result

        git_ref = f"refs/agentic-consensus/proposals/{proposal_id}"
        with tempfile.TemporaryDirectory(prefix="consensus-phi-") as temporary:
            worktree = Path(temporary) / "worktree"
            added = False
            created_ref = False
            target: str | None = None
            try:
                self._run("worktree", "add", "--detach", str(worktree), base)
                added = True
                target_path = worktree / path
                target_path.write_text(updated_source, encoding="utf-8")
                self._run_at(worktree, "add", "--", path)
                self._run_at(
                    worktree,
                    "-c",
                    "user.name=AgenticConsensus Phi",
                    "-c",
                    "user.email=phi@agentic-consensus.local",
                    "commit",
                    "-m",
                    f"AgenticConsensus Phi: {from_module} -> {to_module}",
                )
                target = self._run_at(worktree, "rev-parse", "HEAD")
                self._run("update-ref", git_ref, target)
                created_ref = True
                artifact_diff = self.diff(base, target, max_chars=None)
                result.target_ref = target
                result.git_ref = git_ref
                result.artifact_diff = artifact_diff
            except (GitError, OSError) as exc:
                if created_ref and target is not None:
                    self.delete_proposal_ref(git_ref, target)
                result.failed_preconditions.append(f"isolated realization failed: {exc}")
            finally:
                if added:
                    try:
                        self._run("worktree", "remove", "--force", str(worktree))
                    except GitError:
                        self._run("worktree", "prune", check=False)
        return result
