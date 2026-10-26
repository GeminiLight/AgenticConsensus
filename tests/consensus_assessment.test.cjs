const {test}=require('node:test'),assert=require('node:assert/strict');
const model=require('../system/web/static/commitment-model.js');
const fs=require('node:fs'),vm=require('node:vm');
const commitment={id:'c',title:'Keep task scope',statement:'Reject workspace credentials.',paths:['connector.py'],verification:'Run the rejection test.'};
const item={kind:'proposal',reviewId:'r',targetRef:'target',after:commitment};
const review={id:'r',status:'open',target_ref:'target',changed_paths:['connector.py'],commitment_baseline:[commitment],evidence:[{id:'proof-1'},{id:'proof-2'},{id:'unrelated'}]};
const manifest={committable:false,admission_checks:[{key:'tests',status:'block'}],obligation_statuses:[
  {claim_id:'c',obligation_id:'one',status:'satisfied',evidence_ids:['proof-1']},
  {claim_id:'c',obligation_id:'two',status:'missing',evidence_ids:[]},
]};
test('one supporting record cannot hide another unmet requirement for the same commitment',()=>{
  const state=model.inspection(item,review,manifest);
  assert.equal(state.status,'missing');assert.equal(state.obligation.obligation_id,'two');
  assert.deepEqual(state.evidence.map(r=>r.id),['proof-1']);
  assert.equal(model.reviewRows(review,manifest)[0].status,'missing');
  const summary=model.assessment(item,review,manifest);
  assert.equal(summary.supported,1);assert.equal(summary.total,2);assert.equal(summary.decision,'blocked');
  assert.equal(model.nextStep(item,review,manifest).action,'evidence');
});
test('support for this commitment never clears a blocker elsewhere in the review',()=>{
  const all={...manifest,obligation_statuses:manifest.obligation_statuses.map(o=>({...o,status:'satisfied'}))};
  const summary=model.assessment(item,review,all);
  assert.equal(summary.evidence,'satisfied');assert.equal(summary.supported,2);
  assert.equal(summary.decision,'blocked');assert.equal(summary.blockers,1);
});
test('waivers remain exceptions and do not count as supporting evidence',()=>{
  const waived={...manifest,committable:true,admission_checks:[],obligation_statuses:manifest.obligation_statuses.map(o=>({...o,status:'waived'}))};
  const summary=model.assessment(item,review,waived);
  assert.equal(summary.evidence,'waived');assert.equal(summary.supported,0);assert.equal(summary.decision,'pending');
});
test('a changed commitment keeps its exact obligation scope',()=>{
  const exact={...item,obligation_id:'one'};
  assert.equal(model.assessment(exact,review,manifest).total,1);
  assert.equal(model.inspection(exact,review,manifest).status,'satisfied');
});
test('historical agreement and generic passing checks cannot establish current verification',()=>{
  const agreed={...item,kind:'agreed',reviewId:null};
  assert.equal(model.assessment(agreed,review,manifest).evidence,'unassessed');
  assert.equal(model.assessment(agreed,review,manifest).decision,'unassessed');
  const generic=model.assessment(item,review,{committable:true,obligation_statuses:[]});
  assert.equal(generic.evidence,'unassessed');assert.equal(generic.total,0);assert.equal(generic.decision,'pending');
});
test('loading, unavailable and mismatched versions never reuse previous evidence counts',()=>{
  for(const phase of ['loading','error']){
    const result=model.assessment(item,review,manifest,phase);
    assert.equal(result.evidence,phase);assert.equal(result.records,0);assert.equal(result.total,0);
  }
  const mismatch=model.assessment(item,{...review,target_ref:'older'},manifest);
  assert.equal(mismatch.evidence,'error');assert.equal(mismatch.decision,'error');
});
test('recorded approval is separate from evidence, and inputs remain unchanged',()=>{
  const before=JSON.stringify({item,review,manifest});
  assert.equal(model.assessment(item,{...review,status:'committed'},manifest).decision,'committed');
  assert.equal(model.assessment(item,{...review,status:'committed'},manifest).blockers,0);
  assert.equal(JSON.stringify({item,review,manifest}),before);
});

function renderers(resource,viewer=false){
  const source=fs.readFileSync('system/web/static/commitment-ui.js','utf8');
  const body=source.slice(source.indexOf('  function nextStepView('),source.indexOf('  function footprint('));
  return vm.runInNewContext(`${body}\n({next:nextStepView,assessment:assessmentView})`,{
    CommitmentModel:model,resourceFor:()=>resource,statuses:{missing:'Needs verification',satisfied:'Evidence attached'},
    document:{body:{classList:{contains:()=>viewer}}},esc:v=>String(v??''),m:s=>s,I18n:{t:s=>s},uiIcon:()=>''});
}
test('a requirement action has an exact destination, while an unassessed commitment stays in context',()=>{
  const ready={review,manifest,load:'ready'};
  assert.match(renderers(ready).next(item),/data-meaning-obligation="two"/);
  assert.match(renderers(ready).next(item),/Review required evidence/);
  const unassessed=renderers({...ready,manifest:{committable:true,obligation_statuses:[]}}).next(item);
  assert.match(unassessed,/data-meaning-next="evidence"/);
  assert.doesNotMatch(unassessed,/data-meaning-verify|Review required evidence/);
});
test('viewer assessment never invites a decision the viewer cannot make',()=>{
  const ready={review,manifest:{...manifest,committable:true,admission_checks:[]},load:'ready'};
  assert.match(renderers(ready,true).assessment(item),/Awaiting an authorized decision/);
  assert.doesNotMatch(renderers(ready,true).assessment(item),/Awaiting your decision/);
  assert.match(renderers(ready).assessment(item),/Awaiting your decision/);
});

test('snapshot refresh preserves focus on summary and retry controls, including the busy state',()=>{
  const source=fs.readFileSync('system/web/static/commitment-ui.js','utf8');
  const body=source.slice(source.indexOf('  function refreshInspection('),source.indexOf('  function setMeaningView('));
  for(const attribute of ['data-meaning-evidence-summary','data-meaning-decision','data-meaning-next']){
    for(const disabled of [false,true]){
      const calls=[],zone={id:attribute==='data-meaning-next'?'meaning-next-step':'meaning-assessment',focus:()=>calls.push('zone')};
      const active={closest:selector=>selector==='[data-flow-key]'?null:zone,hasAttribute:name=>name===attribute};
      const selected={disabled,focus:()=>calls.push('control')};
      const choice={positions:new Map()};
      const nodes=new Map();
      const $=selector=>{
        if(selector==='#meaning-source-search')return null;
        if(!nodes.has(selector))nodes.set(selector,{dataset:{},setAttribute(){}});
        return nodes.get(selector);
      };
      const refresh=vm.runInNewContext(`${body}\nrefreshInspection`,{
        currentMeaning:()=>item,$,document:{activeElement:active,querySelector:()=>selected,querySelectorAll:()=>[]},
        inspectorView:()=>'',footprint:()=>'',inspectionContent:()=>'',nextStepView:()=>'',assessmentView:()=>'',graphView:()=>'',
        inspectorChoice:()=>choice,requestAnimationFrame:()=>{}});
      refresh();
      assert.deepEqual(calls,[disabled?'zone':'control']);
      if(disabled)assert.equal(zone.tabIndex,-1);
    }
  }
});
