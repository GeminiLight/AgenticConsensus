const assert = require('node:assert/strict');
const {test} = require('node:test');
const {existsSync} = require('node:fs');
const file = '../system/web/static/decision-model.js';
const model = existsSync(require('node:path').resolve(__dirname, file)) ? require(file) : {};
const inspect = (review, manifest) => {
  assert.equal(typeof model.nextInspection, 'function', 'A deterministic next inspection is missing');
  return model.nextInspection(review, manifest);
};
const check = (key, status = 'block') => ({key, status, label:key, summary:'Recorded check'});
const review = {status:'open', changed_paths:['archive.py'], findings:[{id:'f1',severity:'critical',status:'open',path:'archive.py',line:5,message:'Unknown target'}]};
const manifest = {committable:false,admission_checks:[check('critical_findings'),check('evidence_obligations')]};

test('passing checks without requirements stay explicitly unverified', () => {
  assert.equal(typeof model.requirementCoverage, 'function');
  const coverage = model.requirementCoverage({status:'open', intent_summary:'Never export email', commitment_changes:[]}, {committable:true});
  assert.equal(coverage.status, 'unframed');
  assert.equal(coverage.tone, 'warn');
  assert.equal(coverage.heading, 'Checks pass · requirements unverified');
  assert.deepEqual(coverage.unverified, ['Never export email']);
});

test('covered requirements remain scoped and waived checks are not verified', () => {
  assert.equal(typeof model.requirementCoverage, 'function');
  const subject={status:'open',commitment_changes:[{after:{id:'c1',statement:'Private fields excluded'}}]};
  assert.equal(model.requirementCoverage(subject,{committable:true,obligation_statuses:[{claim_id:'c1',status:'waived'}]}).status,'unverified');
  assert.equal(model.requirementCoverage(subject,{committable:true,obligation_statuses:[{claim_id:'c1',status:'satisfied'}]}).status,'recorded');
});

test('visible scope counts unique paths and review-bound rules, not passed checks', () => {
  const source = {changed_paths:['App.tsx','App.tsx','app.py'],claim_deltas:[{claim_id:'c1'}],
    evidence:[{kind:'static_analysis',status:'pass',claim_ids:['c1','c2']}]};
  assert.deepEqual(model.reviewScope(source),{files:2,pythonFiles:1,claims:2});
  assert.deepEqual(model.reviewScope({changed_paths:['App.tsx'],evidence:[{kind:'static_analysis',status:'pass'}]}),
    {files:1,pythonFiles:0,claims:0});
});

test('handoff includes every unresolved check and traceable source without mutating the review', () => {
  const source = {...review,id:'review-source',revision:7,base_ref:'a'.repeat(40),target_ref:'b'.repeat(40),
    evidence:[{id:'e-stale',kind:'tests',status:'pass',freshness:'stale',summary:'Prior run'}],
    findings:[...review.findings,{id:'f2',severity:'warning',status:'waived',message:'Already disposed'}]};
  const assessment = {committable:false,admission_checks:['base_version','tests','critical_findings','evidence_obligations','evidence_freshness','human_authority'].map(key=>check(key)),
    obligation_statuses:[{obligation_id:'o1',claim_id:'c1',label:'Target test attestation',status:'stale'}]};
  const project = {name:'Example',test_command:['pytest','-q'],repo_path:'/private/host-only-repository'};
  const before = JSON.stringify([source,assessment,project]);
  const brief = model.handoffBrief(source,assessment,project,'http://127.0.0.1:8782/?review=review-source');
  for (const item of assessment.admission_checks) assert.ok(brief.includes(`[${item.key}]`));
  for (const item of [source.base_ref,source.target_ref,'review-source · revision 7','[f1]','archive.py:5','[o1] Target test attestation — stale','[e-stale] tests: pass; stale','["pytest","-q"]']) assert.ok(brief.includes(item),item);
  assert.ok(!brief.includes('[f2]'));
  assert.ok(!brief.includes(project.repo_path));
  assert.match(brief,/requires access to this host/);
  assert.match(brief,/does not notify the proposer/);
  assert.equal(JSON.stringify([source,assessment,project]),before);
});

test('a passing no-rule review does not promise that requirements were covered', () => {
  const brief = model.handoffBrief({status:'open',changed_paths:['App.tsx']},{committable:true,admission_checks:[check('tests','pass')]});
  assert.match(brief,/Configured checks permit a human decision/);
  assert.match(brief,/0 Python files; 0 linked rules/);
  assert.match(brief,/passing checks do not establish requirement coverage/);
});

test('handoff carries the proposed meaning and its verification requirement, not just file counts',()=>{
  const source={...review,commitment_changes:[{request:'Preserve checkout totals.',reason:'Existing callers depend on the example.',before:{statement:'total(3) is six.'},after:{title:'Checkout example',statement:'Addition preserves total(3) as six.',verification:'Run the recorded target test.'}}]};
  const brief=model.handoffBrief(source,manifest);
  for(const text of ['Project commitment changes:','Preserve checkout totals.','total(3) is six.','Addition preserves total(3) as six.','Run the recorded target test.'])assert.ok(brief.includes(text),text);
  assert.match(brief,/not yet agreed/);
});

test('an update-needed handoff directs a new analysis and preserves the recorded rationale', () => {
  const brief = model.handoffBrief({...review,status:'rebase_required',decision_records:[{action:'rebase',reason:'Use the updated baseline.'}]},manifest);
  assert.match(brief,/Review revised version/);
  assert.match(brief,/carry forward requirements/);
  assert.match(brief,/Use the updated baseline\./);
  assert.ok(!brief.includes('review stays open'));
  assert.ok(!brief.includes('Merged'));
});

test('copied briefs disclose unverified intent even when structural rules exist',()=>{
  const brief=model.handoffBrief({status:'open',intent_summary:'Do not export email.',changed_paths:['export.py'],claim_deltas:[{claim_id:'imports'}]},
    {committable:true,admission_checks:[],obligation_statuses:[]});
  assert.match(brief,/Requirement coverage: unframed/);
  assert.match(brief,/Still to verify: Do not export email\./);
});

test('an open critical finding has a direct read-only diff inspection', () => {
  const before = JSON.stringify([review, manifest]);
  assert.deepEqual(inspect(review,manifest), {kind:'finding',checkKey:'critical_findings',label:'Inspect critical finding',detail:'archive.py:5',path:'archive.py',findingId:'f1'});
  assert.equal(JSON.stringify([review,manifest]),before,'Planning cannot mutate evidence or authority');
});
test('a moved project baseline is inspected before findings or evidence', () => {
  const result = inspect(review,{...manifest,admission_checks:[...manifest.admission_checks,check('base_version')]});
  assert.equal(result.checkKey,'base_version');
  assert.equal(result.kind,'check');
  assert.equal(result.label,'Inspect changed baseline');
});
test('waived findings and paths outside the patch cannot invent a diff target', () => {
  for (const finding of [{...review.findings[0],status:'waived'}, {...review.findings[0],path:'unchanged.py'}, {...review.findings[0],path:null}]) {
    const result = inspect({...review,findings:[finding]},manifest);
    assert.equal(result.kind,'check');
    assert.equal(result.checkKey,'critical_findings');
    assert.equal(result.path,undefined);
  }
});
test('missing evidence opens the evidence requirements, not an attach or waiver form', () => {
  assert.deepEqual(inspect(review,{...manifest,admission_checks:[check('critical_findings','pass'),check('evidence_obligations')]}),
    {kind:'requirements',checkKey:'evidence_obligations',label:'Inspect missing evidence',detail:'See the requirements and the records behind them.'});
});
test('test and unfamiliar blockers open their check rather than run or waive it', () => {
  for (const key of ['tests','static_analysis','future_policy']) {
    const result = inspect(review,{...manifest,admission_checks:[check(key)]});
    assert.equal(result.kind,'check');
    assert.equal(result.checkKey,key);
  }
});
test('unknown freshness remains an inspection and human authority is not an invented blocker', () => {
  const result = inspect(review,{...manifest,admission_checks:[check('human_authority','unknown'),check('evidence_freshness','warn')]});
  assert.equal(result.kind,'records');
  assert.equal(result.checkKey,'evidence_freshness');
});
test('ready reviews lead to reading the change, never automatic approval', () => {
  assert.deepEqual(inspect(review,{committable:true,admission_checks:[check('tests','pass')]}),
    {kind:'changes',label:'Read proposed changes',detail:'Passing checks do not replace your review.'});
});
test('an operator with an unframed change is led to define its commitment',()=>{
  const ready={committable:true,admission_checks:[check('tests','pass')]};
  const step=model.nextInspection(review,ready,{canPropose:true});
  assert.equal(step.kind,'commitment');assert.equal(step.label,'Define what must hold');
  assert.equal(model.nextInspection(review,ready,{canPropose:false}).kind,'changes');
  assert.equal(model.nextInspection(review,manifest,{canPropose:true}).kind,'finding');
  const framed={...review,commitment_changes:[{after:{id:'c',statement:'Exclude private notes'}}]};
  assert.equal(model.nextInspection(framed,ready,{canPropose:true}).kind,'changes');
});
test('approval leads to its current agreed commitment, while older decisions retain their history',()=>{
  const after={id:'c',title:'Public exports',statement:'Exclude private notes',category:'behavior',verification:'Check privacy',paths:['exports.py']};
  const source={...review,status:'committed',target_ref:'accepted',commitment_changes:[{after}],decision_records:[{action:'commit'}]};
  const project={head_ref:'accepted',commitments:[after]};
  const step=model.nextInspection(source,{}, {project});
  assert.equal(step.kind,'agreement');assert.equal(step.commitmentId,'c');
  for(const other of [null,{...project,head_ref:'later'},{...project,commitments:[]},{...project,commitments:[{...after,statement:'Revised agreement'}]}]){
    assert.equal(model.nextInspection(source,{}, {project:other}).kind,'audit');
  }
  assert.equal(model.nextInspection({...source,status:'rejected'},{},{project}).kind,'audit');
});
test('closed reviews inspect provenance and a contradictory manifest stays safe', () => {
  for(const status of ['committed','rejected','rebase_required','rolled_back']) {
    assert.equal(inspect({...review,status},manifest).kind,'audit');
  }
  assert.equal(inspect(review,{...manifest,committable:true}).kind,'finding');
});
test('missing terminal attribution is disclosed instead of inventing a recorded decision', () => {
  assert.deepEqual(inspect({...review,status:'rejected',decision_records:[]},manifest),
    {kind:'audit',label:'Inspect review history',detail:'Decision attribution is unavailable. Inspect the recorded history.'});
  assert.equal(inspect({...review,status:'committed',decision_records:[{id:'d1'}]},manifest).label,'Inspect recorded decision');
});

test('review trace shows missing links and genuine directory membership without mutating records', () => {
  assert.equal(typeof model.reviewTrace, 'function');
  const source = {status:'open', changed_paths:['App.tsx','components/Card.tsx','services/ai.ts'],
    evidence:[{kind:'git',status:'pass'},{kind:'static_analysis',status:'pass'},{kind:'tests',status:'not_run'}],
    claim_deltas:[], decision_records:[]};
  const before = JSON.stringify(source);
  const trace = model.reviewTrace(source, {obligation_statuses:[]});
  assert.equal(trace.stages.find(s=>s.id==='request').value,'Summary only');
  assert.equal(trace.stages.find(s=>s.id==='claims').value,'0');
  assert.equal(trace.stages.find(s=>s.id==='claims').tone,'gap');
  assert.equal(trace.stages.find(s=>s.id==='changes').value,'3');
  assert.equal(trace.stages.find(s=>s.id==='evidence').detail,'Tests not run');
  assert.equal(trace.stages.find(s=>s.id==='evidence').tone,'attention');
  assert.equal(trace.stages.find(s=>s.id==='decision').value,'Pending');
  assert.deepEqual(trace.groups.map(g=>[g.directory,g.paths.length]),[['Repository root',1],['components',1],['services',1]]);
  assert.equal(JSON.stringify(source),before);
});

test('review trace uses review-bound claims and treats stale passing evidence as attention', () => {
  const trace=model.reviewTrace({status:'open',intent_id:'intent-1',changed_paths:[],
    claim_deltas:[{claim_id:'c1'},{claim_id:'c1'}],evidence_obligations:[{claim_id:'c2'}],
    evidence:[{kind:'tests',status:'pass',freshness:'stale'}]}, {obligation_statuses:[{claim_id:'c1',status:'missing'}]});
  assert.equal(trace.stages.find(s=>s.id==='request').value,'Linked');
  assert.equal(trace.stages.find(s=>s.id==='claims').value,'2');
  assert.equal(trace.stages.find(s=>s.id==='evidence').tone,'attention');
  assert.equal(trace.stages.find(s=>s.id==='evidence').detail,'1 requirement open');
});

test('an interim waiver is not a final decision and missing attribution stays explicit', () => {
  const waived=model.reviewTrace({status:'open',decision_records:[{action:'waive'}]},{});
  assert.equal(waived.stages.find(s=>s.id==='decision').value,'Pending');
  const unattributed=model.reviewTrace({status:'committed',decision_records:[]},{});
  assert.equal(unattributed.stages.find(s=>s.id==='decision').value,'Unattributed');
  assert.equal(unattributed.stages.find(s=>s.id==='decision').tone,'attention');
  const decided=model.reviewTrace({status:'rejected',decision_records:[{action:'reject'}]},{});
  assert.equal(decided.stages.find(s=>s.id==='decision').value,'Recorded');
});

test('current records are not stale and unknown freshness is not a pass', () => {
  const source={status:'open',evidence:[{kind:'tests',status:'pass',freshness:'current'}]};
  assert.equal(model.reviewTrace(source,{}).stages.find(s=>s.id==='evidence').tone,'recorded');
  source.evidence[0].freshness='unknown';
  assert.equal(model.reviewTrace(source,{}).stages.find(s=>s.id==='evidence').tone,'attention');
});

test('a waiver cannot supply missing attribution for an approved review', () => {
  const result=model.reviewTrace({status:'committed',decision_records:[{action:'waive'}]},{});
  assert.equal(result.stages.find(s=>s.id==='decision').value,'Unattributed');
});

test('evidence claim references remain visible even when no claim delta was recorded', () => {
  const result=model.reviewTrace({status:'open',evidence:[{kind:'attestation',status:'pass',freshness:'current',claim_ids:['c1','c2','c1']}]},{});
  assert.equal(result.stages.find(s=>s.id==='claims').value,'2');
});

test('the change map sizes only actual review paths using recorded line counts', () => {
  assert.equal(typeof model.changeMap, 'function');
  const source={changed_paths:['App.tsx','components/Card.tsx','services/ai.ts','App.tsx']};
  const stats=[{path:'App.tsx',lines:80},{path:'components/Card.tsx',lines:15},{path:'services/ai.ts',lines:5},{path:'outside.ts',lines:9999}];
  const before=JSON.stringify([source,stats]);
  const map=model.changeMap(source,stats);
  assert.equal(map.scale,'lines');
  assert.equal(map.totalLines,100);
  assert.deepEqual(map.groups.map(g=>[g.directory,g.lines]),[['Repository root',80],['components',15],['services',5]]);
  assert.deepEqual(map.groups.flatMap(g=>g.files.map(f=>f.path)).sort(),['App.tsx','components/Card.tsx','services/ai.ts'].sort());
  assert.equal(JSON.stringify([source,stats]),before);
});

test('missing or truncated size data switches the entire map to honest file-count sizing', () => {
  const source={changed_paths:['a.ts','b.ts']};
  for (const stats of [[{path:'a.ts',lines:100}], [{path:'a.ts',lines:100},{path:'b.ts',lines:2,partial:true}], [{path:'a.ts',lines:100},{path:'b.ts',lines:0,sizeKnown:false}]]) {
    const map=model.changeMap(source,stats);
    assert.equal(map.scale,'files');
    assert.equal(map.totalLines,null);
    assert.ok(map.groups.flatMap(g=>g.files).every(f=>f.weight===1));
  }
});

test('renames and empty patches stay visible without inventing changed lines', () => {
  const map=model.changeMap({changed_paths:['renamed.ts','changed.ts']},[{path:'renamed.ts',lines:0},{path:'changed.ts',lines:25}]);
  assert.equal(map.totalLines,25);
  const renamed=map.groups.flatMap(g=>g.files).find(f=>f.path==='renamed.ts');
  assert.equal(renamed.lines,0);
  assert.ok(renamed.weight>0);
  assert.deepEqual(model.changeMap({changed_paths:[]},[]).groups,[]);
});

test('map rectangles are bounded, nonoverlapping and deterministic', () => {
  assert.equal(typeof model.partitionMap,'function');
  const items=Array.from({length:17},(_,i)=>({id:String(i),weight:i+1}));
  const rects=model.partitionMap(items,{x:0,y:0,width:1000,height:440});
  assert.deepEqual(rects,model.partitionMap(items,{x:0,y:0,width:1000,height:440}));
  assert.equal(rects.length,items.length);
  for(const r of rects) {
    assert.ok(r.x>=0 && r.y>=0 && r.width>0 && r.height>0);
    assert.ok(r.x+r.width<=1000.00001 && r.y+r.height<=440.00001);
  }
  for(const [i,a] of rects.entries()) for(const b of rects.slice(i+1)) {
    const overlapX=Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x);
    const overlapY=Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y);
    assert.ok(overlapX<=0.00001 || overlapY<=0.00001);
  }
  assert.ok(Math.abs(rects.reduce((sum,r)=>sum+r.width*r.height,0)-440000)<0.001);
});
