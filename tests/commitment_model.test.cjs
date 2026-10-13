const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const file='../system/web/static/commitment-model.js';
const model=fs.existsSync(require('node:path').resolve(__dirname,file))?require(file):{};
const base={id:'c1',title:'Completion protocol',statement:'Calls return a completed result.',paths:['sdk.ts'],verification:'Replay the released consumers.',category:'interface'};
test('review compares snapshot commitments, never the current project state',()=>{
  assert.equal(typeof model.reviewRows,'function');
  const review={changed_paths:['sdk.ts'],commitment_baseline:[base],commitment_changes:[{before:base,after:{...base,statement:'Calls return a durable job ID.'},request:'Make calls asynchronous.',reason:'Keep execution durable.',obligation_id:'o1'}]};
  const before=JSON.stringify(review);
  const rows=model.reviewRows(review,{obligation_statuses:[{claim_id:'c1',obligation_id:'o1',status:'missing'}]});
  assert.equal(rows.length,1);assert.equal(rows[0].before.statement,base.statement);
  assert.equal(rows[0].after.statement,'Calls return a durable job ID.');assert.equal(rows[0].status,'missing');
  assert.equal(rows[0].changed,true);assert.equal(JSON.stringify(review),before);
});
test('passed generic tests never establish commitment verification',()=>{
  const rows=model.reviewRows({changed_paths:['sdk.ts'],commitment_baseline:[base],evidence:[{kind:'tests',status:'pass'}]},{});
  assert.equal(rows[0].status,'unassessed');assert.equal(rows[0].changed,false);
});
test('unaffected baselines do not pretend to be proposed changes',()=>{
  assert.equal(model.reviewRows({changed_paths:['README.md'],commitment_baseline:[base]},{}).length,0);
});
test('project separates authorized commitments from open proposals',()=>{
  assert.equal(typeof model.projectState,'function');
  const project={commitments:[base]};const change={after:{...base,id:'c2'},request:'A new proposal'};
  const data=model.projectState(project,[{id:'r1',status:'open',commitment_changes:[change]},{id:'r2',status:'rejected',commitment_changes:[change]}]);
  assert.deepEqual(data.authorized,[base]);assert.equal(data.pending.length,1);assert.equal(data.pending[0].reviewId,'r1');
});

test('unmapped open reviews remain discoverable beside agreed and proposed commitments',()=>{
  const reviews=[
    {id:'unmapped',status:'open',changed_paths:['README.md'],commitment_baseline:[base]},
    {id:'recheck',status:'open',changed_paths:['sdk.ts'],commitment_baseline:[base]},
    {id:'proposal',status:'open',commitment_changes:[{after:base}]},
    {id:'closed',status:'rejected',changed_paths:['README.md']},
  ];
  const before=JSON.stringify(reviews),project={commitments:[base]};
  assert.deepEqual(model.projectState(project,reviews).unframed.map(review=>review.id),['unmapped']);
  assert.deepEqual(model.workspace(project,reviews).unframed.map(review=>review.id),['unmapped']);
  assert.equal(JSON.stringify(reviews),before);
});

test('the project focus connects a selected proposal to its own files and review without promoting it',()=>{
  assert.equal(typeof model.workspace,'function');
  const first={before:base,after:{...base,statement:'Return a job ID.',paths:['sdk.ts','worker.ts']},request:'Make calls asynchronous.',reason:'A caller needs durable completion.'};
  const second={before:null,after:{...base,id:'c2',title:'Retry',paths:['worker.ts']}};
  const reviews=[{id:'r1',status:'open',intent_summary:'Async calls',commitment_changes:[first,second]}];
  const input=JSON.stringify(reviews),data=model.workspace({commitments:[base]},reviews,'r1:c2');
  assert.equal(data.selected.after.id,'c2');assert.equal(data.selected.reviewId,'r1');
  assert.equal(data.pending.length,2);assert.equal(data.authorized.length,1);
  assert.equal(data.linkedPaths.length,2);assert.equal(data.selected.kind,'proposal');
  assert.equal(model.workspace({commitments:[base]},reviews,'removed').selected.after.id,'c1');
  assert.equal(JSON.stringify(reviews),input);
});

test('an agreed card links only to a recorded decision with the same commitment snapshot',()=>{
  const approved={id:'approved',status:'committed',commitment_changes:[{after:base}],decision_records:[{action:'commit',actor:'owner'}]};
  const data=model.workspace({commitments:[base]},[approved]);
  assert.equal(data.selected.kind,'agreed');assert.equal(data.selected.reviewId,'approved');
  assert.equal(data.selected.decidedBy,'owner');
  assert.equal(model.workspace({commitments:[{...base,statement:'A later meaning.'}]},[approved]).selected.reviewId,null);
  assert.equal(model.workspace({commitments:[]},[]).selected,null);
});

test('inspection uses only evidence linked to this commitment, not generic passing tests',()=>{
  assert.equal(typeof model.inspection,'function');
  const item={after:base,obligation_id:'o1'};
  const review={evidence:[{id:'generic',status:'pass'},{id:'linked',status:'fail'}]};
  const manifest={obligation_statuses:[{claim_id:'c1',obligation_id:'o1',status:'contested',evidence_ids:['linked']} ]};
  const result=model.inspection(item,review,manifest,[]);
  assert.equal(result.status,'contested');assert.deepEqual(result.evidence.map(e=>e.id),['linked']);
  assert.equal(result.files[0].path,'sdk.ts');assert.equal(result.files[0].changes,null);
  assert.equal(model.inspection(item,review,{},[]).status,'unassessed');
});

test('file footprint counts only linked patch lines and reports incomplete patches',()=>{
  assert.equal(typeof model.inspection,'function');
  const files=[{path:'sdk.ts',additions:20,deletions:5,partial:true},{path:'unrelated.ts',additions:100,deletions:0}];
  const result=model.inspection({after:base},{},{},files);
  assert.equal(result.files.length,1);assert.deepEqual(result.files[0].changes,{additions:20,deletions:5,partial:true});
  assert.equal(result.totalChanges,25);
});

test('alignment readings remain authored observations, not consensus or passed evidence',()=>{
  assert.equal(typeof model.alignment,'function');
  const notes=[{path:'sdk.ts',version_ref:'target',relation:'tension',summary:'The consumer expects a different return type.',start_line:2,end_line:3},
    {path:'sdk.ts',version_ref:'old',relation:'supports'}, {path:'foreign.ts',version_ref:'target',relation:'supports'}];
  const item={kind:'proposal',after:base,source_readings:notes};
  const result=model.alignment(item,{target_ref:'target'},{});
  assert.equal(result.readings.length,1);assert.equal(result.questions,1);
  assert.equal(result.agreed,false);assert.equal(result.evidenceStatus,'unassessed');
  assert.equal(result.unreadPaths.length,0);
  assert.equal(model.alignment({after:base},{target_ref:'target'},{}).unreadPaths.length,1);
});

test('review projection preserves source readings for editing, and exact agreed snapshots retain their provenance',()=>{
  const note={path:'sdk.ts',version_ref:'target',relation:'context',summary:'Recorded reading',start_line:1,end_line:1};
  const review={id:'r',status:'committed',changed_paths:['sdk.ts'],commitment_changes:[{after:base,source_readings:[note]}]};
  assert.deepEqual(model.reviewRows(review)[0].sourceReadings,[note]);
  assert.deepEqual(model.workspace({commitments:[base]},[review]).selected.source_readings,[note]);
});

const originNote={path:'sdk.ts',version_ref:'v1',relation:'context',label:'SDK',summary:'Original source reading.',start_line:1,end_line:2};
function history(){
  const origin={id:'origin',status:'committed',base_version:1,target_ref:'v1',commitment_changes:[{after:base,request:'Keep existing consumers working.',reason:'A released consumer needs the result.',recorded_by:'author',source_readings:[originNote]}],decision_records:[{action:'commit',actor:'owner'}]};
  const latest={id:'latest',status:'committed',base_version:2,target_ref:'v2',changed_paths:['sdk.ts'],commitment_baseline:[base],commitment_changes:[],decision_records:[{action:'commit',actor:'maintainer'}]};
  return {origin,latest,project:{version:3,head_ref:'v2',commitments:[base]}};
}
test('current applicability and the decision that established meaning have separate identities',()=>{
  const {origin,latest,project}=history(),selected=model.workspace(project,[origin,latest]).selected;
  assert.equal(selected.reviewId,'latest');
  assert.equal(selected.originReviewId,'origin');
  assert.equal(selected.originTarget,'v1');assert.equal(selected.targetRef,'v2');
  assert.equal(selected.applicability,'current');
  assert.equal(selected.request,origin.commitment_changes[0].request);
  assert.equal(selected.reason,origin.commitment_changes[0].reason);
  assert.equal(selected.recorded_by,'author');assert.equal(selected.decidedBy,'owner');
  assert.deepEqual(selected.source_readings,[],'Old source notes cannot describe the new version');
  assert.deepEqual(selected.originReadings,[originNote]);
});
test('historical approval cannot substitute for a missing current-version assessment',()=>{
  const {origin,project}=history(),selected=model.workspace(project,[origin]).selected;
  assert.equal(selected.reviewId,null);assert.equal(selected.applicability,'unassessed');
  assert.equal(selected.originReviewId,'origin');assert.deepEqual(selected.source_readings,[]);
});
test('same target with a different meaning or a rolled-back decision cannot establish current applicability',()=>{
  const {origin,latest,project}=history();
  for(const other of [{...latest,status:'rolled_back'},{...latest,commitment_baseline:[{...base,statement:'A different meaning.'}]}]){
    assert.equal(model.workspace(project,[other,origin]).selected.reviewId,null);
  }
});
test('open changes touching an unchanged commitment remain visible as rechecks',()=>{
  const {origin,latest,project}=history(),review={...latest,id:'pending',status:'open'};
  const data=model.workspace(project,[review,origin]);
  assert.equal(data.pending.length,1);assert.equal(data.selected.kind,'recheck');
  assert.equal(data.selected.reviewId,'pending');assert.equal(data.selected.originReviewId,'origin');
  assert.equal(data.selected.after.statement,base.statement);
  assert.equal(data.authorized.length,1);
  assert.equal(model.workspace(project,[{...review,changed_paths:['readme.md']},origin]).pending.length,0);
});
test('pending assessments never replace the agreed-state evidence context',()=>{
  const {origin,latest,project}=history();
  const data=model.workspace(project,[{...latest,status:'open'},origin],'agreed:c1');
  assert.equal(data.selected.kind,'agreed');assert.equal(data.selected.reviewId,null);
});
test('rollback to an earlier artifact reuses its own correspondence, not a later version',()=>{
  const {origin,latest,project}=history();
  const item=model.workspace({...project,version:4,head_ref:'v1'},[{...latest,status:'rolled_back'},origin]).selected;
  assert.equal(item.reviewId,'origin');assert.deepEqual(item.source_readings,[originNote]);
});
test('next step is grounded in the selected commitment and its evidence state',()=>{
  assert.equal(typeof model.nextStep,'function');
  const item={kind:'proposal',after:base,reviewId:'r',source_readings:[{...originNote,relation:'tension'}]};
  const review={target_ref:'v1'};
  assert.equal(model.nextStep(item,review,{},'loading').action,'loading');
  assert.equal(model.nextStep(item,review,{},'error').action,'retry');
  assert.equal(model.nextStep(item,review,{},'ready').action,'source');
  const clear={...item,source_readings:[]};
  for(const status of ['missing','stale','contested','unassessed'])assert.equal(model.nextStep(clear,review,{obligation_statuses:[{claim_id:'c1',status}]},'ready').action,'evidence');
  assert.equal(model.nextStep(clear,review,{obligation_statuses:[{claim_id:'c1',status:'satisfied'}]},'ready').action,'review');
  assert.equal(model.nextStep({...clear,kind:'agreed',reviewId:null},review,{},'ready').action,'new-review');
});
test('an unchanged baseline remains agreed while the new implementation needs checking',()=>{
  assert.equal(model.alignment({kind:'recheck',after:base},{}).agreed,true);
});
test('a stale proposal sends the user to the changed baseline before source questions',()=>{
  const item={kind:'proposal',reviewId:'r',after:base,source_readings:[{...originNote,relation:'tension'}]};
  const result=model.nextStep(item,{target_ref:'v1'},{admission_checks:[{key:'base_version',status:'block'}]},'ready');
  assert.equal(result.action,'review');assert.equal(result.status,'rebase');
});

test('an approved exact version leads to the recorded outcome, not another approval',()=>{
  const item={kind:'agreed',after:base,reviewId:'r',source_readings:[]};
  assert.equal(model.nextStep(item,{status:'committed',target_ref:'v1'}, {obligation_statuses:[{claim_id:'c1',status:'satisfied'}]},'ready').status,'recorded');
});
