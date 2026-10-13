/* Intent data stays independent of presentation: alternatives are never merged. */
(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  else root.IntentModel = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const questions = (value) => [...new Set(String(value).split("\n").map((line) => line.trim().replace(/\s+/g, " ")).filter(Boolean))];
  function repositoryScope(tree, loading = false) {
    if (loading || !tree || tree.error || !Array.isArray(tree.entries)) return {state:'unknown', pythonFiles:0};
    const pythonFiles=tree.entries.filter(entry=>entry.kind==='file' && entry.path.endsWith('.py')).length;
    return {state:pythonFiles ? 'python_found' : tree.truncated ? 'unknown' : 'no_python', pythonFiles};
  }
  function fromAIRun(run) {
    const candidates = run.result?.candidates;
    if (!Array.isArray(candidates) || candidates.length < 2 || candidates.length > 20) {
      throw new Error("The interpreter must return 2–20 alternatives. Your request is unchanged; retry or write alternatives yourself.");
    }
    return candidates.map((candidate) => {
      const result = clone(candidate);
      result.provenance = `${candidate.provenance}; AI run ${run.id}`;
      if (result.provenance.length > 1000) throw new Error("The interpreter's source reference is too long to record. Your draft is unchanged.");
      result.status = "active";
      return result;
    });
  }
  function editCandidate(candidate, values) {
    const result = clone(candidate);
    result.title = values.title.trim();
    result.summary = values.summary.trim();
    result.structural_delta = {kind: "python_import_substitution", path: values.path.trim(), from_module: values.from_module.trim(), to_module: values.to_module.trim()};
    result.uncertainties = questions(values.uncertainties);
    const changed = ["title", "summary", "structural_delta", "uncertainties"].some((key) => JSON.stringify(result[key]) !== JSON.stringify(candidate[key]));
    if (changed && !result.provenance.startsWith("human-authored") && !result.provenance.endsWith("; human-edited")) {
      result.provenance += "; human-edited";
    }
    if (changed) result.confidence = null;
    return result;
  }
  function clarificationPayload(intent, {question, answer, retained, resolved}) {
    const active = intent.candidates.filter((candidate) => candidate.status === "active");
    if (!retained.length) throw new Error("Keep at least one interpretation. Uncheck only the alternatives this answer rules out.");
    if (retained.some((id) => !active.some((candidate) => candidate.id === id))) throw new Error("The interpretations changed. Reopen clarification to review the current version.");
    const resolvedUncertainties = {};
    for (const candidate of active.filter((item) => retained.includes(item.id))) {
      const indexes = [...new Set(resolved[candidate.id] || [])];
      if (indexes.some((index) => !Number.isInteger(index) || index < 0 || index >= candidate.uncertainties.length)) throw new Error("The questions changed. Reopen clarification to review the current version.");
      if (indexes.length) resolvedUncertainties[candidate.id] = indexes.map((index) => candidate.uncertainties[index]);
    }
    return {
      question: question.trim(), answer: answer.trim(), expected_revision: intent.revision,
      retained_candidate_ids: active.filter((item) => retained.includes(item.id)).map((item) => item.id),
      eliminated_candidate_ids: active.filter((item) => !retained.includes(item.id)).map((item) => item.id),
      resolved_uncertainties: resolvedUncertainties,
    };
  }
  function canSelect(intent, candidate) {
    return ["clarification_required", "ready_for_selection"].includes(intent.status) && candidate.status === "active" && candidate.uncertainties.length === 0;
  }
  function canRevise(intent, candidate = null) {
    return ["clarification_required", "ready_for_selection"].includes(intent.status)
      && (candidate ? candidate.status === "active" : intent.candidates.length < 20);
  }
  function candidateValues(candidate) {
    return {title: candidate.title, summary: candidate.summary, path: candidate.structural_delta.path,
      from_module: candidate.structural_delta.from_module, to_module: candidate.structural_delta.to_module,
      uncertainties: candidate.uncertainties.join("\n")};
  }
  function candidateChanges(before, after) {
    const labels = {title: "Approach name", summary: "Explanation", path: "Python file", from_module: "Current import", to_module: "Replace with", uncertainties: "Open questions"};
    const oldValues = before ? candidateValues(before) : {}, newValues = candidateValues(after);
    return Object.entries(labels).filter(([field]) => (oldValues[field] || "") !== newValues[field])
      .map(([field, label]) => ({field, label, before: oldValues[field] || "", after: newValues[field]}));
  }
  function rebaseCandidate(original, latest, values) {
    const edited = editCandidate(original, values), result = candidateValues(latest);
    for (const change of candidateChanges(original, edited)) result[change.field] = change.after;
    return result;
  }
  function revisionPayload(intent, {candidateId = null, values, reason}) {
    const fail = (field, message) => {const error = new Error(message); error.field = field; throw error;};
    if (!["clarification_required", "ready_for_selection"].includes(intent.status)) throw new Error("This request is locked after selection. Inspect the recorded proposal instead.");
    const original = candidateId ? intent.candidates.find(candidate => candidate.id === candidateId && candidate.status === "active") : null;
    if (candidateId && !original) throw new Error("This proposal is no longer active. Review the latest request before continuing.");
    if (!candidateId && intent.candidates.length >= 20) throw new Error("This request already contains 20 interpretations, including ruled-out alternatives.");
    const candidate = editCandidate(original || {provenance: "human-authored/added-alternative", confidence: null, status: "active"}, values);
    for (const [field, limit] of [["title",240],["summary",2000],["path",1000],["from_module",500],["to_module",500]]) {
      const value = field in candidate ? candidate[field] : candidate.structural_delta[field];
      if (!value || value.length > limit) fail(field, `Add ${field === "title" ? "an approach name" : field === "summary" ? "an explanation" : field.replaceAll("_", " ")} of at most ${limit} characters.`);
    }
    const delta = candidate.structural_delta;
    if (!delta.path.endsWith(".py") || delta.path.startsWith("/") || delta.path.split("/").includes("..")) fail("path", "Use a safe repository-relative Python file, such as checkout.py.");
    for (const field of ["from_module", "to_module"]) if (!delta[field].split(".").every(part => /^[_\p{ID_Start}][_\p{ID_Continue}]*$/u.test(part))) fail(field, "Use a dotted Python module name, such as billing.pricing.");
    if (delta.from_module === delta.to_module) fail("to_module", "The replacement must differ from the current import.");
    if (candidate.uncertainties.length > 20) fail("uncertainties", "Keep at most 20 open questions, one per line.");
    if (candidate.provenance.length > 1000) throw new Error("The source lineage is too long to record this edit. Your draft is kept.");
    if (original && !candidateChanges(original, candidate).length) throw new Error("No proposal changes yet. Edit the approach or close the draft.");
    if (!reason?.trim() || reason.trim().length < 8 || reason.trim().length > 4000) fail("reason", "Explain why this proposal should change (8–4000 characters). Include why any question is no longer open.");
    return {question: original ? "How should this proposal be revised?" : "What additional interpretation should stay open?", answer: reason.trim(), expected_revision: intent.revision,
      retained_candidate_ids: intent.candidates.filter(item => item.status === "active").map(item => item.id),
      eliminated_candidate_ids: [], resolved_uncertainties: {},
      candidate_revisions: original ? {[original.id]: candidate} : {}, added_candidates: original ? [] : [candidate]};
  }
  function recordedRevision(intent, payload, actor) {
    const turn = (intent.clarification_history || []).find(item => item.intent_revision === payload.expected_revision + 1);
    if (!turn || turn.actor !== actor || turn.question !== payload.question || turn.answer !== payload.answer) return false;
    if (Object.keys(payload.candidate_revisions).length !== turn.revised_candidate_ids.length || payload.added_candidates.length !== turn.added_candidate_ids.length) return false;
    const equivalent = (a, b) => a && b && !candidateChanges(a, b).length && a.provenance === b.provenance && a.confidence === b.confidence;
    return Object.entries(payload.candidate_revisions).every(([id, candidate]) => turn.revised_candidate_ids.includes(id) && equivalent(candidate, turn.after_candidates.find(item => item.id === id)))
      && payload.added_candidates.every((candidate, index) => equivalent(candidate, turn.after_candidates.find(item => item.id === turn.added_candidate_ids[index])));
  }
  function nextAction(intent) {
    if (intent.status === "realized") return "Inspect the linked review to compare the proposed change with the original intent. Realization is not merge approval.";
    if (intent.status === "selected") return "Create an isolated proposal, then inspect its round-trip verification. Your working checkout is not modified.";
    if (intent.candidates.some((candidate) => canSelect(intent, candidate))) return "Select a resolved interpretation when you are ready, or keep clarifying. Other alternatives remain in the record.";
    return "Record what you know. Resolve only the questions your answer addresses; keep alternatives open until you can distinguish them.";
  }
  return {repositoryScope, fromAIRun, editCandidate, clarificationPayload, canSelect, nextAction, canRevise, candidateValues, candidateChanges, rebaseCandidate, revisionPayload, recordedRevision};
});
