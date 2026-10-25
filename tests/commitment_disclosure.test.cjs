const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const CommitmentModel=require('../system/web/static/commitment-model.js');

function setup({meaning='',viewer=false}={}) {
  const after={id:'c1',title:'Keep scoped access',category:'behavior',statement:'Reject workspace-wide providers.',verification:'Run the rejection check at the target revision.',paths:['connector.py']};
  const review={id:'r1',status:'open',changed_paths:['connector.py'],commitment_changes:[{after,request:'Add archive access.',reason:'Keep the task boundary.',recorded_by:'owner',obligation_id:'o1'}]};
  const listeners={};
  const context={window:{location:{href:'http://localhost/?project=p1'+(meaning?'&meaning='+encodeURIComponent(meaning):'')},addEventListener(){}},URL,CommitmentModel,
    state:{activeProject:{id:'p1'}},document:{body:{classList:{contains:()=>viewer}},addEventListener:(name,fn)=>{(listeners[name]??=[]).push(fn);}},
    $:()=>({addEventListener(){},reset(){},close(){},dataset:{}}),
    I18n:{mark:s=>s,t:s=>s},uiIcon:()=>'',sentence:s=>s,esc:s=>String(s??'')};
  vm.runInNewContext(fs.readFileSync('system/web/static/commitment-ui.js','utf8'),context);
  const ui=context.window.CommitmentUI;
  return {ui,listeners,render:(id='r1')=>ui.reviewView({...review,id},{obligation_statuses:[{claim_id:'c1',obligation_id:'o1',status:'missing'}]})};
}
const render=options=>setup(options).render();
test('collapsed commitments retain the full requirement, verification and evidence entry point',()=>{
  const html=render();
  assert.doesNotMatch(html,/<details class="commitment-workbench[^>]* open/);
  assert.match(html,/Reject workspace-wide providers\./);
  assert.match(html,/Run the rejection check at the target revision\./);
  assert.match(html,/data-commitment-evidence="o1"/);
  assert.match(html,/Needs verification/);
  assert.match(html,/data-propose-commitment="c1"/);
});
test('a direct commitment link opens its detail without requiring an extra disclosure action',()=>{
  assert.match(render({meaning:'r1:c1'}),/<details class="commitment-workbench[^>]* open/);
});
test('viewer can inspect the requirement and evidence without seeing edit actions',()=>{
  const html=render({viewer:true});
  assert.match(html,/data-commitment-evidence="o1"/);
  assert.doesNotMatch(html,/data-propose-commitment/);
});
test('manual disclosure choice survives a re-render, belongs to its review, and clears on sign-out',()=>{
  const c=setup();c.ui.bind();
  const toggle=open=>c.listeners.toggle.forEach(fn=>fn({target:{id:'review-commitments',dataset:{commitmentPanel:'r1'},open,matches:()=>false}}));
  toggle(true);
  assert.match(c.render(),/<details class="commitment-workbench[^>]* open/);
  assert.doesNotMatch(c.render('r2'),/<details class="commitment-workbench[^>]* open/);
  toggle(false);
  assert.doesNotMatch(c.render(),/<details class="commitment-workbench[^>]* open/);
  toggle(true);c.ui.clear();
  assert.doesNotMatch(c.render(),/<details class="commitment-workbench[^>]* open/);
});
