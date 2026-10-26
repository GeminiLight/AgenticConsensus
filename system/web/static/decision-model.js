/* A read-only inspection plan. Never executes checks or grants decision authority. */
(function (root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.DecisionModel = model;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function requirementCoverage(review, manifest = {}) {
    const indexed = new Map((review.commitment_baseline || []).filter(c=>(c.paths||[]).some(p=>(review.changed_paths||[]).includes(p))).map(c=>[c.id,c]));
    for(const change of review.commitment_changes||[])indexed.set(change.after.id,change.after);
    const requirements=[...indexed.values()];
    const unverified=requirements.filter(c=>{
      const records=(manifest.obligation_statuses||[]).filter(o=>o.claim_id===c.id);
      return !records.length || records.some(o=>o.status!=='satisfied');
    }).map(c=>c.statement);
    const status=!requirements.length?'unframed':unverified.length?'unverified':'recorded';
    return {status,tone:status==='recorded'?'ok':'warn',
      heading:status==='unframed'?'Checks pass · requirements unverified':status==='unverified'?'Checks permit a decision · verification incomplete':'Recorded requirements have evidence',
      unverified:status==='unframed'?[review.intent_summary||'No behavioral requirements are recorded.']:unverified};
  }
  function nextInspection(review, manifest, {canPropose = false, project = null} = {}) {
    if (review.status === 'committed' && project?.head_ref && project.head_ref === review.target_ref) {
      const agreed = (review.commitment_changes || []).find(change => (project.commitments || []).some(item =>
        ['id','title','statement','verification','category'].every(key => item[key] === change.after[key])
        && JSON.stringify(item.paths) === JSON.stringify(change.after.paths)));
      if (agreed) return {kind:'agreement',commitmentId:agreed.after.id,label:'View agreed commitment',detail:'See the agreed requirement, its evidence and recorded decision together.'};
    }
    if (review.status !== 'open') return review.decision_records?.length
      ? {kind:'audit',label:'Inspect recorded decision',detail:'Read the attributed decision and its source records.'}
      : {kind:'audit',label:'Inspect review history',detail:'Decision attribution is unavailable. Inspect the recorded history.'};
    const priority = ['base_version','critical_findings','evidence_obligations','tests','static_analysis','proposal_conflict','evidence_freshness'];
    const rank = key => priority.includes(key) ? priority.indexOf(key) : priority.length;
    const checks = (manifest.admission_checks || []).filter(check => check.status !== 'pass' && check.key !== 'human_authority');
    checks.sort((a,b) => Number(b.status === 'block') - Number(a.status === 'block') || rank(a.key)-rank(b.key));
    const check = checks[0];
    if (!check && canPropose && requirementCoverage(review, manifest).status === 'unframed') return {kind:'commitment',label:'Define what must hold',detail:'A commitment records the behavior to preserve and the evidence needed to check it.'};
    if (!check) return {kind:'changes',label:'Read proposed changes',detail:'Passing checks do not replace your review.'};
    const checkKey = check.key;
    if (checkKey === 'critical_findings') {
      const finding = (review.findings || []).find(item => item.severity === 'critical' && item.status === 'open' && (review.changed_paths || []).includes(item.path));
      if (finding) return {kind:'finding',checkKey,label:'Inspect critical finding',detail:`${finding.path}${finding.line ? `:${finding.line}` : ''}`,path:finding.path,findingId:finding.id};
    }
    if (checkKey === 'evidence_obligations') return {kind:'requirements',checkKey,label:'Inspect missing evidence',detail:'See the requirements and the records behind them.'};
    if (checkKey === 'evidence_freshness') return {kind:'records',checkKey,label:'Inspect evidence freshness',detail:'Read the recorded versions before deciding.'};
    const labels = {base_version:'Inspect changed baseline',critical_findings:'Inspect critical check',tests:'Inspect test result',static_analysis:'Inspect structure check',proposal_conflict:'Inspect overlapping proposal'};
    return {kind:'check',checkKey,label:labels[checkKey] || 'Inspect blocking check',detail:check.summary || 'Read the recorded check and its resolution options.'};
  }
  function reviewTrace(review, manifest = {}) {
    const paths = [...new Set(review.changed_paths || [])];
    const records = review.evidence || [];
    const claims = new Set([
      ...(review.claim_deltas || []), ...(review.evidence_obligations || []),
      ...(manifest.obligation_statuses || []),
    ].map(item => item.claim_id).filter(Boolean).concat(records.flatMap(item => item.claim_ids || [])));
    const missing = (manifest.obligation_statuses || []).filter(item => !['satisfied','waived'].includes(item.status)).length;
    const tests = records.find(item => item.kind === 'tests');
    const stale = records.filter(item => item.freshness === 'stale').length;
    const unsettled = records.filter(item => item.status !== 'pass' || (item.freshness && item.freshness !== 'current')).length;
    const evidenceDetail = missing ? `${missing} requirement${missing === 1 ? '' : 's'} open`
      : !records.length ? 'No records'
      : tests?.status === 'not_run' ? 'Tests not run'
      : tests?.status === 'fail' ? 'Tests failed'
      : stale ? `${stale} stale record${stale === 1 ? '' : 's'}`
      : unsettled ? `${unsettled} record${unsettled === 1 ? '' : 's'} need attention`
      : 'Inspect source records';
    const finalAction = {committed:'commit', rejected:'reject', rebase_required:'rebase', rolled_back:'rollback'}[review.status];
    const decision = finalAction && (review.decision_records || []).find(item => item.action === finalAction);
    const groups = new Map();
    paths.forEach(path => {
      const directory = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : 'Repository root';
      if (!groups.has(directory)) groups.set(directory, []);
      groups.get(directory).push(path);
    });
    return {
      stages: [
        {id:'request', label:'Request', value:review.intent_id ? 'Linked' : 'Summary only', detail:review.intent_id ? 'Versioned intent map' : 'No intent map linked', tone:review.intent_id ? 'recorded' : 'gap', view:'intents'},
        {id:'claims', label:'Claims', value:String(claims.size), detail:claims.size ? 'Referenced in this review' : 'None linked to this review', tone:claims.size ? 'recorded' : 'gap', view:'governance'},
        {id:'changes', label:'Changes', value:String(paths.length), detail:paths.length === 1 ? 'Changed file' : 'Changed files', tone:paths.length ? 'recorded' : 'gap', tab:'changes'},
        {id:'evidence', label:'Evidence', value:String(records.length), detail:evidenceDetail, tone:missing || unsettled ? 'attention' : records.length ? 'recorded' : 'gap', tab:'evidence'},
        {id:'decision', label:'Decision', value:review.status === 'open' ? 'Pending' : decision ? 'Recorded' : 'Unattributed', detail:review.status === 'open' ? 'No final decision' : decision ? 'Inspect actor and rationale' : 'No matching decision record', tone:review.status === 'open' ? 'pending' : decision ? 'recorded' : 'attention', tab:'audit'},
      ],
      groups: [...groups].map(([directory, paths]) => ({directory, paths})),
    };
  }
  function changeMap(review, stats = []) {
    const indexed = new Map(stats.map(item => [item.path, item]));
    const files = [...new Set(review.changed_paths || [])].map(path => {
      const stat = indexed.get(path);
      const known = stat && stat.sizeKnown !== false && Number.isFinite(stat.lines) && stat.lines >= 0 && !stat.partial;
      return {path, filename:path.split('/').pop(), directory:path.includes('/') ? path.slice(0,path.lastIndexOf('/')) : 'Repository root',
        lines:known ? stat.lines : null, additions:stat?.additions ?? null, deletions:stat?.deletions ?? null};
    });
    const complete = files.every(file => file.lines !== null);
    const scale = complete && files.some(file => file.lines > 0) ? 'lines' : 'files';
    const groups = new Map();
    files.forEach(file => {
      file.weight = scale === 'lines' ? Math.max(1,file.lines) : 1;
      if (!groups.has(file.directory)) groups.set(file.directory,{directory:file.directory,files:[],lines:complete ? 0 : null,weight:0});
      const group=groups.get(file.directory);
      group.files.push(file);
      group.weight += file.weight;
      if (complete) group.lines += file.lines;
    });
    return {scale, totalLines:complete ? files.reduce((sum,file)=>sum+file.lines,0) : null, groups:[...groups.values()]};
  }

  function partitionMap(items, rect) {
    if (!items.length) return [];
    const ordered=[...items].sort((a,b)=>b.weight-a.weight || String(a.id || a.path || a.directory).localeCompare(String(b.id || b.path || b.directory)));
    function split(list, box) {
      if (list.length === 1) return [{...list[0], ...box}];
      const total=list.reduce((sum,item)=>sum+item.weight,0);
      let cut=1, subtotal=list[0].weight;
      while(cut<list.length-1 && Math.abs(total/2-subtotal-list[cut].weight) < Math.abs(total/2-subtotal)) subtotal += list[cut++].weight;
      const ratio=subtotal/total;
      const first={...box}, second={...box};
      if(box.width >= box.height) {first.width=box.width*ratio;second.x=box.x+first.width;second.width=box.width-first.width;}
      else {first.height=box.height*ratio;second.y=box.y+first.height;second.height=box.height-first.height;}
      return [...split(list.slice(0,cut),first), ...split(list.slice(cut),second)];
    }
    return split(ordered,rect);
  }
  function reviewScope(review, manifest = {}) {
    const paths=[...new Set(review.changed_paths || [])];
    return {files:paths.length, pythonFiles:paths.filter(path=>path.endsWith('.py')).length,
      claims:Number(reviewTrace(review,manifest).stages.find(stage=>stage.id==='claims').value)};
  }

  function handoffBrief(review, manifest = {}, project = {}, workspaceUrl = '') {
    const line=value=>String(value ?? '').replace(/\s+/g,' ').trim();
    const scope=reviewScope(review,manifest);
    const coverage=requirementCoverage(review,manifest);
    const checks=(manifest.admission_checks || []).filter(check=>check.status!=='pass');
    const findings=(review.findings || []).filter(finding=>finding.status==='open');
    const obligations=(manifest.obligation_statuses || []).filter(item=>!['satisfied','waived'].includes(item.status));
    const labels={base_version:'Proposal baseline',tests:'Target tests',critical_findings:'Open critical findings',
      evidence_obligations:'Required evidence',static_analysis:'Structure analysis',evidence_freshness:'Evidence freshness',
      proposal_conflict:'Overlapping proposals',human_authority:'Human decision'};
    const actions={
      base_version:'Update the proposal against the current project baseline, then analyze the revised commits.',
      tests:'Run the repository test suite against the target commit and record its result in this review.',
      critical_findings:'Resolve the open findings below and analyze the revised change, or record an authorized disposition.',
      evidence_obligations:'Collect the required records listed below for this target revision.',
      static_analysis:'Inspect the structure-check failure and analyze the corrected proposal.',
      evidence_freshness:'Replace stale evidence with records for this target revision.',
      proposal_conflict:'Compare the overlapping proposals and reconcile their changes.',
      human_authority:'Have an identity with the required project authority record the decision.',
    };
    const statuses={committed:'Approved in the local project ledger',rejected:'Rejected',rebase_required:'Update required; analyze a revised proposal next',rolled_back:'Local approval rolled back'};
    const result=[
      `Review brief: ${line(review.intent_summary || review.summary)}`,
      `Project: ${line(project.name || review.project_id)}`,
      `Review: ${line(review.id)} · revision ${review.revision ?? 'unavailable'}`,
      `Status: ${review.status==='open' ? manifest.committable ? 'Configured checks permit a human decision' : 'Blocked' : statuses[review.status] || line(review.status)}`,
      `Base: ${line(review.base_ref)}`,`Target: ${line(review.target_ref)}`,
      `Scope: ${scope.files} changed files; ${scope.pythonFiles} Python files; ${scope.claims} linked rules.`,
      !scope.claims ? 'No project rules are linked to this review; passing checks do not establish requirement coverage.' : 'Python file counts describe file types, not verification coverage.',
      `Requirement coverage: ${coverage.status}. Evidence covers only recorded requirements, not all possible risks.`,
      ...coverage.unverified.map(statement=>`Still to verify: ${line(statement)}`),
      ...(review.commitment_changes?.length ? ['', 'Project commitment changes:', ...review.commitment_changes.flatMap(change=>[
        `- ${line(change.after.title)} — ${review.status==='committed'?'accepted in this review':'proposal; not yet agreed by this review'}`,
        `  Request: ${line(change.request)}`,
        `  Before: ${line(change.before?.statement || 'No prior commitment recorded')}`,
        `  After: ${line(change.after.statement)}`,
        `  Reason: ${line(change.reason)}`,
        `  To verify: ${line(change.after.verification)}`,
      ])] : []),
      '', 'Next steps:',
      ...(review.status==='open' ? checks.length ? checks.map((check,index)=>`${index+1}. ${line(labels[check.key] || check.label || check.key)} [${line(check.key)}] — ${line(check.status)}: ${line(check.summary)}\n   ${actions[check.key] || 'Inspect the recorded check and resolve its stated condition.'}`) : ['1. Read the proposed changes and record a human decision.']
        : [review.status==='rebase_required' ? '1. Open an existing follow-up, or use Review revised version to carry forward requirements with fresh evidence. If the project baseline has advanced, start a new review against that baseline.' : '1. Inspect the recorded decision and its rationale.']),
      ...(project.test_command?.length ? [`Configured test arguments: ${JSON.stringify(project.test_command)}`] : []),
      ...(findings.length ? ['', 'Open findings:', ...findings.map(f=>`- [${line(f.id)}] ${line(f.severity)}: ${line(f.message)}${f.path ? ` — ${line(f.path)}${f.line ? `:${f.line}` : ''}` : ''}`)] : []),
      ...(obligations.length ? ['', 'Required records still open:', ...obligations.map(item=>{
        const requirement=(review.evidence_obligations || []).find(obligation=>obligation.id===item.obligation_id);
        return `- [${line(item.obligation_id)}] ${line(item.label || requirement?.label || item.claim_id)} — ${line(item.status)}`;
      })] : []),
      '', 'Evidence at this revision:',
      ...(review.evidence?.length ? review.evidence.map(item=>`- [${line(item.id)}] ${line(item.kind)}: ${line(item.status)}; ${line(item.freshness || 'freshness unavailable')}; ${line(item.summary)}`) : ['- No records.']),
      ...(review.decision_records?.length ? ['', 'Latest recorded rationale:', line(review.decision_records.at(-1).reason || 'No rationale recorded.')] : []),
      '', 'Changed files:', ...[...new Set(review.changed_paths || [])].map(path=>`- ${line(path)}`),
      '', 'This brief is a snapshot. Check the target revision again before acting.',
      'Copying this brief does not notify the proposer or change the pull request.',
      ...(review.external_url ? [`Source: ${line(review.external_url)}`] : []),
      ...(workspaceUrl ? [`Workspace link (requires access to this host): ${line(workspaceUrl)}`] : []),
    ];
    return result.join('\n');
  }
  return {nextInspection, reviewTrace, changeMap, partitionMap, reviewScope, handoffBrief, requirementCoverage};
});
