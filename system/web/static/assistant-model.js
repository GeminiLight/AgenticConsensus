/* Review-owned transient state. No local storage, authority, or model actions. */
(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  else root.AssistantModel = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function createSession() {
    const drafts = new Map();
    let owner = null;
    const key = (review, project) => JSON.stringify([project.id, review.id]);
    const owns = (draft) => Boolean(draft && drafts.get(draft.key) === draft && owner !== null);
    return {
      syncOwner(userId, csrf) {
        const next = userId && csrf ? JSON.stringify([userId, csrf]) : null;
        if (next !== owner || next === null) drafts.clear();
        owner = next;
      },
      get(review, project) {
        if (!owner || !review || !project) return null;
        const id = key(review, project);
        if (!drafts.has(id)) drafts.set(id, {key:id, question:"", deliberate:true, runId:null, pending:null, message:"", state:"idle", optionsOpen:false});
        return drafts.get(id);
      },
      owns,
      begin(draft, review, project, kind) {
        if (!owns(draft) || draft.pending) return null;
        const operation = {draft, kind, reviewId:review.id, projectId:project.id, reviewRevision:review.revision, projectVersion:project.version, targetRef:review.target_ref};
        draft.pending = operation;
        return operation;
      },
      finish(operation, message, state) {
        if (!owns(operation?.draft) || operation.draft.pending !== operation) return false;
        Object.assign(operation.draft, {pending:null, message, state});
        return true;
      },
    };
  }
  function isCurrent(run, review, project) {
    return Boolean(run && review && project && run.review_id === review.id && run.project_id === project.id
      && run.review_revision === review.revision && run.project_version === project.version
      && !(run.quality_flags || []).includes("legacy_unversioned_context"));
  }
  function contextMatches(operation, review, project) {
    return Boolean(operation && review && project && operation.reviewId === review.id && operation.projectId === project.id
      && operation.reviewRevision === review.revision && operation.projectVersion === project.version
      && operation.targetRef === review.target_ref);
  }
  function sourceTarget(citation, review, project, manifest) {
    if (!citation?.id || !review) return null;
    const separator = citation.id.indexOf(":");
    const kind = citation.id.slice(0, separator), id = citation.id.slice(separator + 1);
    if (kind === "finding") {
      const finding = review.findings?.find(item => item.id === id);
      return finding?.path && review.changed_paths?.includes(finding.path) ? {kind, id, path:finding.path} : null;
    }
    const records = {evidence:review.evidence, obligation:review.evidence_obligations, decision:review.decision_records, claim:project?.claims};
    if (records[kind]?.some(item => item.id === id)) return {kind, id};
    if (kind === "admission" && manifest?.admission_checks?.some(item => item.key === id)) return {kind, id};
    if ((kind === "diff" || kind === "review") && id === review.id) return {kind, id};
    return null;
  }
  function errorMessage(error) {
    const detail = error?.message || "The request could not finish.";
    if (error?.status === 409) return "The review context changed. Refresh this review, then ask again. Your question is kept.";
    if (error?.status === 401) return "Your session expired. Sign in again to continue.";
    if (error?.status === 403) return "You do not have permission to use this action. Ask a workspace operator; no review decision was changed.";
    if (!error?.status) return "Check your connection to the workspace, then retry. Your question is kept.";
    return `${detail} ${error.status >= 500 ? "The service could not finish; retry, or inspect recorded gaps locally." : "Review the message, then retry."} Your question is kept.`;
  }
  return {createSession, isCurrent, contextMatches, sourceTarget, errorMessage};
});
