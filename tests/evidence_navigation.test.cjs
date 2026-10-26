const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');

test('a direct evidence action opens and focuses its exact requirement, including covered groups',()=>{
  const source=fs.readFileSync('system/web/static/app.js','utf8');
  const body=source.slice(source.indexOf('function focusEvidenceObligation('),source.indexOf('function bindEvidenceWorkspace('));
  const calls=[],group={open:false},details={open:false},otherDetails={open:false};
  const card=(id,disclosure)=>({dataset:{obligationCard:id},
    closest:()=>group,querySelector:selector=>selector==='details.evidence-record-details'?disclosure:null,
    focus:()=>calls.push('focus:'+id),scrollIntoView:()=>calls.push('scroll:'+id)});
  const cards=[card('unrelated',otherDetails),card('needed',details)];
  const state={evidenceQuery:'old search',evidenceFilter:'attention',evidenceObligation:'old'};
  const inputs={'#evidence-record-search':{value:'old'},'#evidence-record-filter':{value:'attention'}};
  const focus=vm.runInNewContext(`${body}\nfocusEvidenceObligation`,{state,
    $:selector=>inputs[selector],document:{querySelectorAll:()=>cards},
    refreshEvidenceRecords:()=>calls.push('refresh'),setReviewWorkspaceTab:tab=>calls.push('review:'+tab),setEvidenceTab:tab=>calls.push('evidence:'+tab)});
  focus('needed');
  assert.equal(state.evidenceObligation,'needed');assert.equal(state.evidenceQuery,'');assert.equal(state.evidenceFilter,'all');
  assert.equal(inputs['#evidence-record-search'].value,'');assert.equal(inputs['#evidence-record-filter'].value,'all');
  assert.equal(group.open,true);assert.equal(details.open,true);assert.equal(otherDetails.open,false);
  assert.equal(cards[0].dataset.focused,'false');assert.equal(cards[1].dataset.focused,'true');
  assert.deepEqual(calls,['refresh','review:evidence','evidence:requirements','focus:needed','scroll:needed']);
  inputs['#review-tab-evidence']={focus:()=>calls.push('focus:evidence-tab')};
  focus('removed');
  assert.equal(calls.at(-1),'focus:evidence-tab');
});
