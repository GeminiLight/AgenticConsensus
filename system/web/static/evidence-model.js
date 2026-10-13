(function (root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.EvidenceModel = model;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  // Presentation only. Admission and authority remain server decisions.
  function obligationContext(review, obligation, claims = []) {
    const proposal=(review.commitment_changes || []).find(change=>change.after.id===obligation.claim_id)?.after;
    const baseline=(review.commitment_baseline || []).find(item=>item.id===obligation.claim_id);
    const rule=claims.find(item=>item.id===obligation.claim_id);
    const subject=proposal || baseline || rule;
    return {title:subject?.title || obligation.label || obligation.claim_id,
      statement:subject?.statement || '',plan:obligation.label || '',
      source:proposal?'proposal':baseline?'baseline':rule?'rule':'unknown'};
  }
  function requirements(review, manifest) {
    const statuses = new Map((manifest.obligation_statuses || []).map(item => [item.obligation_id, item]));
    const entries = (review.evidence_obligations || []).map(obligation => ({
      obligation,
      status: statuses.get(obligation.id) || {status:'unknown', evidence_ids:[], waiver_ids:[]},
    }));
    return {
      pending: entries.filter(item => !['satisfied','waived'].includes(item.status.status)),
      covered: entries.filter(item => ['satisfied','waived'].includes(item.status.status)),
    };
  }

  function assessRecord(item, target, invalidatedIds = []) {
    if (invalidatedIds.includes(item.id)) return {label:'Invalidated',attention:true};
    if (item.freshness === 'stale' || (item.artifact_ref && target && item.artifact_ref !== target)) return {label:'Outdated',attention:true};
    if (item.freshness !== 'current') return {label:'Freshness unknown',attention:true};
    if (!item.artifact_ref || !target) return {label:'Version unknown',attention:true};
    if (item.status === 'fail') return {label:'Failed',attention:true};
    if (item.outcome === 'contests') return {label:'Conflicts',attention:true};
    if (item.status === 'pass' && item.outcome === 'supports') return {label:'Supports',attention:false};
    return {label:item.outcome === 'not_applicable' ? 'Not applicable' : 'Inconclusive',attention:true};
  }

  function recordView(records, target, query = '', filter = 'all', obligationId = '', invalidatedIds = []) {
    const needle = query.trim().toLowerCase();
    return records.filter(item => {
      if (obligationId && !(item.obligation_ids || []).includes(obligationId)) return false;
      if (filter === 'attention' && !assessRecord(item, target, invalidatedIds).attention) return false;
      return !needle || [item.id,item.kind,item.summary,item.provenance,item.recorded_by,item.authority,item.artifact_ref,
        ...(item.claim_ids || []),...(item.obligation_ids || [])].join(' ').toLowerCase().includes(needle);
    });
  }
  return {obligationContext,requirements,assessRecord,recordView};
});
