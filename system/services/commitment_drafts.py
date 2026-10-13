"""Bounded, local extractive drafting. Source text is data, never instructions.

No model call, checks, evidence writes or inferred approval. The user must confirm
the proposed interpretation through the ordinary commitment/evidence workflow.
"""
import re

from system.services.git_service import GitError, GitRepository


def _prose_paragraphs(content):
    """Preserve wrapped requirements with real line numbers; skip fenced examples."""
    paragraph, start, fenced = [], 1, False
    for number, line in enumerate(content.splitlines() + [""], 1):
        fence = line.lstrip().startswith(("```", "~~~"))
        boundary = not line.strip() or line.lstrip().startswith("#") or fence or fenced
        if boundary:
            if paragraph:
                yield start, "\n".join(paragraph)
                paragraph = []
        else:
            if not paragraph:
                start = number
            paragraph.append(line.strip())
        if fence:
            fenced = not fenced


def draft_commitment(review, project, request, language="en"):
    zh = language == "zh"
    request = (request or review.intent_summary).strip()
    if not request:
        raise ValueError("Describe the change and what must remain true before drafting.")
    repo = GitRepository(project.repo_path)
    sources, constraints, limitations, readings = [], [], [], []
    requirement = re.compile(r"\b(must|never|shall|required|allowlist|contract)\b|必须|不得|禁止|仅允许|不能", re.I)
    # Read immutable blobs, not the working tree, symlink targets or arbitrary paths.
    for revision in dict.fromkeys([review.base_ref, review.target_ref]):
        for path in ("README.md", "README", "readme.md"):
            try:
                file = repo.snapshot_file(revision, path, byte_limit=32_768)
            except FileNotFoundError:
                continue
            if file["status"] != "text":
                limitations.append(f"{path}@{revision[:8]}: {file['status']}")
                continue
            for number, paragraph in _prose_paragraphs(file["content"]):
                excerpt = paragraph[:500] + ("…" if len(paragraph) > 500 else "")
                if requirement.search(paragraph) and len(constraints) < 6 and excerpt not in constraints:
                    constraints.append(excerpt)
                    sources.append(dict(path=path, revision=revision, start_line=number, excerpt=excerpt))
                    if len(paragraph) > 500:
                        limitations.append(f"{path}:{number}: " + ("长段落已节选，请核对完整原文。" if zh else "Long paragraph excerpted; inspect the complete source."))
            break
    patch = repo.diff(review.base_ref, review.target_ref, max_chars=40_000)
    anchors = {}
    current = None
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+++ "):
            current = None
        elif current and (match := re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)):
            start, count = int(match[1]), int(match[2] or 1)
            if count:
                anchors.setdefault(current, (max(1, start), min(count, 8)))
    paths = list(review.changed_paths[:6])
    for path in paths:
        if path not in anchors:
            continue
        try:
            file = repo.snapshot_file(review.target_ref, path, byte_limit=48_000)
        except (FileNotFoundError, GitError):
            limitations.append(f"{path}: source unavailable")
            continue
        if file["status"] != "text":
            limitations.append(f"{path}: {file['status']}")
            continue
        start, count = anchors[path]
        end = min(start + count - 1, len(file["content"].splitlines()))
        if end < start:
            continue
        excerpt = "\n".join(file["content"].splitlines()[start - 1:end])
        sources.append(dict(path=path, revision=review.target_ref, start_line=start, excerpt=excerpt))
        readings.append(dict(path=path, start_line=start, end_line=end,
            label="本次修改的源码" if zh else "Changed source",
            summary="此处是实际变更的源码。请核对它是否满足约定；定位不代表验证通过。" if zh else "This source changed. Check it against the proposed requirement; this location is not verification.", relation="context"))
    if not constraints:
        limitations.append("未在根目录 README 中找到明确约束，请补充遗漏要求。" if zh else "No explicit constraints found in a root README; add any missing requirements.")
    if len(review.changed_paths) > len(paths):
        limitations.append("仅预选前 6 个变更文件，请核对范围。" if zh else "Only the first 6 changed files are selected; check the scope.")
    limitations.append("本地摘录草稿，不调用模型，不检查业务正确性。出处可能不完整或互相冲突，请逐项确认。" if zh else "Local extractive draft, not model reasoning or behavioral verification. Sources may be incomplete or conflicting; confirm each requirement.")
    source_refs = [f"{s['path']}:{s['start_line']} @{s['revision'][:8]}" for s in sources]
    statement = request + (("\n\n仓库中已有的约束（请确认适用）：\n" if zh else "\n\nRecorded repository constraints (confirm applicability):\n") + "\n".join(constraints) if constraints else "")
    if len(statement) > 4000:
        limitations.append("约定正文已缩短至 4000 字符；原始需求完整保留，请拆分或补充末尾要求。" if zh else "The statement was shortened to 4000 characters. The full request is preserved; split or restore omitted requirements before saving.")
    command = " ".join(project.test_command) or ("项目测试命令（尚未配置）" if zh else "project tests (not configured)")
    verification = ((f"在当前评审的目标版本运行 {command}。\n逐项核对上述要求，增加能在错误实现上失败的回归测试；同时验证预期输出及禁止的行为。记录具体断言、实际结果和版本，不以测试退出 0 代替覆盖证明。" if zh else
        f"At the current review target, run {command}.\nFor each requirement above, add a regression that fails on an incorrect implementation. Check required outputs and forbidden behavior. Record assertions, observations and revision; an exit code of 0 alone does not prove coverage."))
    if constraints:
        verification += ("\n重点核对：" if zh else "\nCheck explicitly: ") + " ".join(constraints)[:900]
    return dict(method="local-extraction", target_ref=review.target_ref, review_revision=review.revision,
        sources=sources, limitations=limitations, proposal=dict(request=request,
        title=re.split(r"[。\n.!?]", request)[0][:100] or request[:100], statement=statement[:4000],
        reason=(("草稿取自本次需求及版本化源码，尚待人工核对。出处：" if zh else "Drafted from the request and versioned sources; human confirmation is required. Sources: ") + "; ".join(source_refs))[:4000],
        category="behavior", paths=paths, verification=verification[:2000], source_readings=readings))
