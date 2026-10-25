const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../system/web/static');
const I18n = require(path.join(root, 'i18n.js'));
I18n.setLanguage('en');
const model = fs.existsSync(path.join(root, 'evidence-model.js')) ? require(path.join(root, 'evidence-model.js')) : {};
const review = {status:'open', target_ref:'new', evidence:[], findings:[], waivers:[], claim_deltas:[], evidence_obligations:[
  {id:'done', claim_id:'c1', label:'Verified source', verification:'dsse_ed25519'},
  {id:'missing', claim_id:'c1', label:'Denied ungranted capability', verification:'authorized_record'},
  {id:'waived', claim_id:'c1', label:'Runtime observation'},
  {id:'unknown', claim_id:'c1', label:'Unknown requirement'},
]};
const manifest = {obligation_statuses:[
  {obligation_id:'done',status:'satisfied',evidence_ids:['r1'],waiver_ids:[]},
  {obligation_id:'missing',status:'stale',evidence_ids:['r2'],waiver_ids:[]},
  {obligation_id:'waived',status:'waived',evidence_ids:[],waiver_ids:['w1']},
], blockers:['Something else'], committable:false};
const record = {id:'r1',kind:'tests',status:'pass',outcome:'supports',freshness:'current',artifact_ref:'new',summary:'Tests completed',provenance:'runner/builds/long/full-source',obligation_ids:[],claim_ids:[],details:{}};

test('verification context uses the proposed snapshot, then its baseline, never a later project meaning',()=>{
  const baseline={id:'c1',title:'Original behavior',statement:'Return the result.'};
  const proposed={...baseline,title:'Durable completion',statement:'Return a job ID.'};
  const input={commitment_baseline:[baseline],commitment_changes:[{after:proposed}]};
  const obligation={claim_id:'c1',label:'Start a job.\nReconnect and check its result.'};
  const later=[{id:'c1',title:'A later rule'}];
  const context=model.obligationContext(input,obligation,later);
  assert.equal(context.title,proposed.title);assert.equal(context.statement,proposed.statement);
  assert.equal(context.plan,obligation.label);assert.equal(context.source,'proposal');
  assert.equal(model.obligationContext({...input,commitment_changes:[]},obligation,later).title,baseline.title);
  assert.equal(model.obligationContext({},obligation,later).title,later[0].title);
  assert.equal(model.obligationContext({},obligation,[]).title,obligation.label);
  assert.equal(model.obligationContext({},obligation,[]).statement,'');
});

test('requirements preserve authoritative stale/waived states and never guess a missing status', () => {
  assert.equal(typeof model.requirements, 'function');
  const view = model.requirements(review, manifest);
  assert.deepEqual(view.pending.map(item => item.obligation.id), ['missing','unknown']);
  assert.deepEqual(view.covered.map(item => item.status.status), ['satisfied','waived']);
  assert.equal(view.pending[0].status.status, 'stale');
  assert.equal(view.pending[1].status.status, 'unknown');
  assert.equal(manifest.obligation_statuses.length, 3);
});

test('old and unknown records cannot look like current supporting evidence', () => {
  assert.equal(typeof model.assessRecord, 'function');
  assert.equal(model.assessRecord(record, 'new').attention, false);
  for (const change of [{freshness:'stale'}, {freshness:'unknown'}, {artifact_ref:'old'}, {status:'unknown'}, {outcome:'inconclusive'}]) {
    assert.equal(model.assessRecord({...record,...change}, 'new').attention, true);
    assert.notEqual(model.assessRecord({...record,...change}, 'new').label, 'Supports');
  }
  assert.equal(model.assessRecord({...record,artifact_ref:null}, 'new').label, 'Version unknown');
});

test('server-invalidated records stay visible in attention even if their stored run passed', () => {
  assert.deepEqual(model.assessRecord(record, 'new', ['r1']), {label:'Invalidated',attention:true});
  assert.equal(model.recordView([record], 'new', '', 'attention', '', ['r1']).length, 1);
});

test('record search includes full provenance, identities, and canonical IDs', () => {
  assert.equal(typeof model.recordView, 'function');
  const records = [record, {...record,id:'r2',freshness:'stale',recorded_by:'reviewer@example.test'}];
  assert.equal(model.recordView(records,'new',' FULL-SOURCE ','all').length, 2);
  assert.deepEqual(model.recordView(records,'new','reviewer@','attention').map(item => item.id), ['r2']);
  assert.deepEqual(model.recordView(records,'new','r1','attention'), []);
  assert.equal(model.recordView([], 'new', '', 'all').length, 0);
});

function rendering() {
  const source = fs.readFileSync(path.join(root, 'app.js'),'utf8');
  const helpers = source.slice(source.indexOf('function renderEvidenceBrief('), source.indexOf('function renderCheckResolution('));
  return vm.runInNewContext(`${helpers}\n({brief:renderEvidenceBrief, obligations:renderEvidenceObligations, records:renderEvidence, workspace:typeof renderEvidenceWorkspace === 'function' ? renderEvidenceWorkspace : null, error:typeof evidenceErrorMessage === 'function' ? evidenceErrorMessage : null})`, {
    EvidenceModel:model,
    I18n,
    uiIcon:()=>'',
    state:{evidenceTab:'requirements',evidenceQuery:'',evidenceFilter:'all',activeProject:{claims:[{id:'c1',title:'Only task-scoped credentials'}],attestation_trust_roots:[]}},
    esc:value => String(value ?? '').replace(/[&<>"']/g,c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    sentence:value => String(value ?? ''), title:value => String(value ?? ''), plainVersion:value => value,
    short:value => String(value ?? '').slice(0,8), plural:(n,s,p) => `${n} ${n === 1 ? s : p || s+'s'}`,
  });
}

test('summary never claims approval from supporting records or calls stale evidence missing', () => {
  const html = rendering().brief({...review,evidence:[record]},manifest);
  assert.match(html, /need attention/);
  assert.doesNotMatch(html, /still missing|Recorded evidence supports this review/);
  const noRequirements = rendering().brief({...review,evidence_obligations:[],evidence:[record]}, {...manifest,obligation_statuses:[]});
  assert.match(noRequirements, /Not ready to approve/);
  assert.match(noRequirements, /Other checks need attention/);
  assert.doesNotMatch(noRequirements, /No outstanding|supports this review/i);
});

test('completed evidence remains distinct from the approval decision',()=>{
  const html=rendering().brief({...review,evidence_obligations:[]},{obligation_statuses:[],committable:true});
  assert.match(html,/No outstanding evidence items/);
  assert.match(html,/Approval is recorded separately/);
  assert.match(html,/data-attention="false"/);
});

test('requirement leads with human-readable claim and explains stale evidence, with exact IDs on demand', () => {
  const html = rendering().obligations(review,manifest);
  assert.match(html, /Only task-scoped credentials/);
  assert.match(html, /target revision|current target/);
  assert.match(html, /Verification details/);
  assert.match(html, /View linked records/);
  assert.match(html, /Unknown/);
});

test('manual commitment requirements lead with their title and keep the verification plan inspectable',()=>{
  const input={...review,commitment_changes:[{after:{id:'c1',title:'Keep checkout totals',statement:'Existing callers still receive six.'}}]};
  const html=rendering().obligations(input,manifest);
  assert.match(html,/<h4>Keep checkout totals<\/h4>/);
  assert.match(html,/Existing callers still receive six\./);
  assert.match(html,/Verification plan/);assert.match(html,/Denied ungranted capability/);
  assert.doesNotMatch(html,/Only task-scoped credentials/);
});

test('missing evidence is presented as needing verification, not as a failed check',()=>{
  const html=rendering().obligations(review,{obligation_statuses:[{obligation_id:'missing',status:'missing'}]});
  assert.match(html,/Needs verification/);
  assert.doesNotMatch(html,/×/);
});

test('record renderer exposes full provenance and IDs without unsafe markup or hover-only truncation', () => {
  const html = rendering().records({...review,evidence:[{...record,provenance:'runner/'+'long-'.repeat(20)+'<unsafe>',summary:'Test <unsafe>'}]});
  assert.match(html, /Record details/);
  assert.match(html, /long-long-long-long-long-long-long-long-long-long-long-long-long-long-long-long-long-long-long-long-&lt;unsafe&gt;/);
  assert.match(html, /r1/);
  assert.doesNotMatch(html, /<unsafe>/);
});

test('workspace separates requirements, records and claims into labelled mutually exclusive views', () => {
  const render = rendering().workspace;
  assert.equal(typeof render,'function');
  const html = render(review,manifest);
  assert.match(html, /role="tablist" aria-label="Evidence views"/);
  assert.match(html, /id="evidence-panel-records"[^>]* hidden/);
  assert.match(html, /id="evidence-panel-claims"[^>]* hidden/);
  assert.match(html, /Covered requirements/);
  assert.match(html, /No records yet/);
  assert.match(html, /id="refresh-evidence-records"/);
});

test('visible status has no second accessible label on a decorative symbol', () => {
  const html = rendering().obligations(review,manifest);
  assert.match(html, /class="obligation-state" aria-hidden="true"/);
  assert.doesNotMatch(html, /class="obligation-state" aria-label=/);
});

test('waived findings return to attention after expiry, without relabelling them as missing records', () => {
  const input = {...review,evidence_obligations:[],findings:[{id:'f1',status:'waived'}],waivers:[{finding_ids:['f1'],expires_at:'2000-01-01T00:00:00Z'}]};
  assert.match(rendering().brief(input,{...manifest,obligation_statuses:[]}), /0 requirements · 1 finding/);
});

test('linked records filter uses exact obligation membership, not an ID substring', () => {
  assert.equal(model.recordView([{...record,obligation_ids:['one-more']}], 'new', '', 'all', 'one').length, 0);
  assert.equal(model.recordView([{...record,obligation_ids:['one']}], 'new', '', 'all', 'one').length, 1);
});

test('attachment errors distinguish ambiguous connection failure from server rejection', () => {
  const error = rendering().error;
  assert.equal(typeof error,'function');
  assert.match(error({name:'TypeError',message:'Failed to fetch'}), /could not be confirmed/i);
  assert.match(error({name:'TypeError',message:'Failed to fetch'}), /Records.*retry/i);
  assert.match(error({message:'actor is not authorized'}), /actor is not authorized/);
});
