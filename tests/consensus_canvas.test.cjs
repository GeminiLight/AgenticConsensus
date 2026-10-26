const {test}=require('node:test'),assert=require('node:assert/strict');
const model=require('../system/web/static/commitment-model.js');
const item={kind:'recheck',reviewId:'r',targetRef:'target',after:{id:'exports',title:'Public exports',statement:'Keep exports public.',verification:'Run privacy and tag checks.',paths:['exports.py']}};
const review={id:'r',target_ref:'target',status:'open',evidence:[{id:'public',summary:'Published-only test passed.'},{id:'email',summary:'Email exclusion test passed.'},{id:'generic',kind:'tests',status:'pass'}]};
const manifest={committable:false,obligation_statuses:[
  {claim_id:'exports',obligation_id:'o1',label:'Published notes only',status:'satisfied',evidence_ids:['public']},
  {claim_id:'exports',obligation_id:'o2',label:'Author emails excluded',status:'satisfied',evidence_ids:['email']},
  {claim_id:'exports',obligation_id:'o3',label:'Tags preserved',status:'missing',evidence_ids:[]},
  {claim_id:'other',obligation_id:'unrelated',status:'satisfied',evidence_ids:['generic']},
]};
test('canvas lanes pair each requirement only with its own recorded evidence',()=>{
  const before=JSON.stringify({item,review,manifest}),graph=model.verificationGraph(item,review,manifest);
  assert.equal(graph.rows.length,3);assert.equal(graph.summary.supported,2);assert.equal(graph.summary.total,3);
  assert.deepEqual(graph.rows.map(row=>row.records.map(record=>record.id)),[['public'],['email'],[]]);
  assert.equal(graph.rows[2].id,'o3');assert.equal(graph.rows[2].label,'Tags preserved');assert.equal(graph.phase,'verify');
  assert.equal(JSON.stringify({item,review,manifest}),before);
});
test('drafts retain their exact requirement scope, and plans never become counted proof',()=>{
  const draft=model.verificationGraph({...item,kind:'proposal',obligation_id:'o3'},review,manifest);
  assert.equal(draft.rows.length,1);assert.equal(draft.rows[0].status,'missing');
  const plan=model.verificationGraph(item,review,{committable:true});
  assert.equal(plan.summary.total,0);assert.equal(plan.rows[0].id,null);assert.equal(plan.rows[0].status,'unassessed');
  assert.equal(plan.rows[0].label,item.after.verification);assert.deepEqual(plan.rows[0].records,[]);
});
test('unavailable or mismatched snapshots cannot paint old evidence green',()=>{
  for(const graph of [model.verificationGraph(item,review,manifest,'loading'),model.verificationGraph(item,review,manifest,'error'),model.verificationGraph(item,{...review,target_ref:'old'},manifest)]){
    assert.equal(graph.summary.supported,0);assert.equal(graph.rows.length,1);assert.deepEqual(graph.rows[0].records,[]);
    assert.ok(['loading','error'].includes(graph.rows[0].status));
  }
  assert.equal(model.verificationGraph({...item,reviewId:null},review,manifest).phase,'verify');
});
test('exceptions, stale records and contested results remain distinct from supported requirements',()=>{
  for(const status of ['waived','stale','contested']){
    const graph=model.verificationGraph(item,review,{...manifest,obligation_statuses:[{...manifest.obligation_statuses[0],status}]});
    assert.equal(graph.rows[0].status,status);assert.equal(graph.summary.supported,0);
    assert.equal(graph.phase,status==='waived'?'decide':'verify');
  }
  const done=model.verificationGraph(item,review,{...manifest,committable:true,obligation_statuses:manifest.obligation_statuses.slice(0,2)});
  assert.equal(done.phase,'decide');assert.equal(done.summary.decision,'pending');
});
