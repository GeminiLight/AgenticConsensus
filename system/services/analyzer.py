from __future__ import annotations

import ast
from dataclasses import dataclass, field

from system.domain.models import (
    Finding,
    PythonImportSubstitution,
    RehydratedDeltaCandidate,
)
from system.services.git_service import GitRepository


@dataclass(frozen=True)
class ImportObservation:
    module: str
    line: int
    dynamic: bool = False


@dataclass
class ParsedImports:
    imports: set[ImportObservation] = field(default_factory=set)
    unobservable: set[int] = field(default_factory=set)
    syntax_error: tuple[int | None, str] | None = None


def _extract(source: str) -> ParsedImports:
    result = ParsedImports()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        result.syntax_error = (exc.lineno, exc.msg)
        return result

    importlib_aliases = {"importlib"}
    import_module_aliases = {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_aliases.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.add(ImportObservation(alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.imports.add(ImportObservation(node.module, node.lineno))
            for alias in node.names:
                if alias.name != "*":
                    result.imports.add(ImportObservation(f"{node.module}.{alias.name}", node.lineno))
        elif isinstance(node, ast.Call):
            is_import_module = (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in importlib_aliases
                and node.func.attr == "import_module"
            )
            is_dunder_import = isinstance(node.func, ast.Name) and node.func.id in import_module_aliases
            if is_import_module or is_dunder_import:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    result.imports.add(ImportObservation(node.args[0].value, node.lineno, dynamic=True))
                else:
                    result.unobservable.add(node.lineno)
    return result


def _is_forbidden(module: str, forbidden_modules: list[str]) -> bool:
    return any(module == blocked or module.startswith(f"{blocked}.") for blocked in forbidden_modules)


def analyze_python_imports(
    repository: GitRepository,
    base_ref: str,
    target_ref: str,
    *,
    rule_id: str,
    forbidden_modules: list[str],
    severity: str = "critical",
) -> list[Finding]:
    findings: list[Finding] = []
    for path in repository.changed_python_files(base_ref, target_ref):
        before = _extract(repository.show(base_ref, path) or "")
        after = _extract(repository.show(target_ref, path) or "")

        if after.syntax_error:
            line, message = after.syntax_error
            findings.append(
                Finding(
                    rule_id=rule_id,
                    kind="syntax_error",
                    severity="critical",
                    message=f"Changed Python file cannot be parsed: {message}",
                    path=path,
                    line=line,
                )
            )
            continue

        before_modules = {item.module for item in before.imports}
        candidates = [
            observation
            for observation in after.imports
            if observation.module not in before_modules and _is_forbidden(observation.module, forbidden_modules)
        ]
        candidates = [
            observation
            for observation in candidates
            if not any(
                other.line == observation.line
                and other.module != observation.module
                and observation.module.startswith(f"{other.module}.")
                for other in candidates
            )
        ]
        for observation in sorted(candidates, key=lambda item: (item.line, item.module)):
            findings.append(
                Finding(
                    rule_id=rule_id,
                    kind="forbidden_dependency",
                    severity=severity,
                    message=f"New import crosses the declared boundary: {observation.module}",
                    path=path,
                    line=observation.line,
                    details={"module": observation.module, "dynamic_literal": observation.dynamic},
                )
            )

        for line in sorted(after.unobservable - before.unobservable):
            findings.append(
                Finding(
                    rule_id=rule_id,
                    kind="unobservable",
                    severity="critical",
                    message="Dynamic import target cannot be resolved by static analysis",
                    path=path,
                    line=line,
                    details={"boundary": forbidden_modules},
                )
            )
    return findings


def rehydrate_python_import_substitutions(
    repository: GitRepository,
    base_ref: str,
    target_ref: str,
) -> tuple[list[RehydratedDeltaCandidate], list[str]]:
    """Psi for the bounded Phi operator, derived only from the artifact diff."""
    candidates: list[RehydratedDeltaCandidate] = []
    unobservable: list[str] = []
    for path in repository.changed_python_files(base_ref, target_ref):
        before_source = repository.show(base_ref, path) or ""
        after_source = repository.show(target_ref, path) or ""
        try:
            before_tree = ast.parse(before_source)
            after_tree = ast.parse(after_source)
        except SyntaxError as exc:
            unobservable.append(f"{path}: syntax prevents import rehydration at line {exc.lineno}")
            continue
        before_modules = {
            node.module
            for node in ast.walk(before_tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        after_modules = {
            node.module
            for node in ast.walk(after_tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        removed = sorted(before_modules - after_modules)
        added = sorted(after_modules - before_modules)
        if not removed and not added:
            continue
        if not removed or not added:
            unobservable.append(
                f"{path}: import change cannot be paired into a substitution"
            )
            continue
        pair_count = len(removed) * len(added)
        confidence = 1.0 if pair_count == 1 else 1.0 / pair_count
        if pair_count > 1:
            unobservable.append(
                f"{path}: {pair_count} import substitutions remain structurally ambiguous"
            )
        for from_module in removed:
            for to_module in added:
                candidates.append(
                    RehydratedDeltaCandidate(
                        structural_delta=PythonImportSubstitution(
                            path=path,
                            from_module=from_module,
                            to_module=to_module,
                        ),
                        confidence=confidence,
                        evidence=[
                            f"{path}@{repository.resolve(base_ref)} removed from-import {from_module}",
                            f"{path}@{repository.resolve(target_ref)} added from-import {to_module}",
                        ],
                    )
                )
    if not candidates and not unobservable:
        unobservable.append("artifact diff contains no observable Python from-import substitution")
    return candidates, unobservable
