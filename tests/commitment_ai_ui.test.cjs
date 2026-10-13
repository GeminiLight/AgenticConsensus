const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup() {
  const review={id:'review-a',revision:2,target_ref:'target',base_ref:'base',project_id:'project-a'};
  const context={window:{}, I18n:{mark:s=>s,t:s=>s}, document:{body:{classList:{contains:()=>false}}},
    esc:s=>String(s??'').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
    state:{activeReview:review,activeProject:{id:'project-a',version:1},aiRuns:[]}};
  vm.runInNewContext(fs.readFileSync('system/web/static/commitment-ui.js','utf8'),context);
  return context;
}
test('risk panel offers an explicit analysis, not an automatic model call',()=>{
  const c=setup(); const html=c.window.CommitmentUI.riskView(c.state.activeReview);
  assert.match(html,/data-analyze-risks/); assert.match(html,/Not analyzed/);
});
test('only the matching review and project version may display current model risks',()=>{
  const c=setup(); c.state.aiRuns=[{review_id:'review-a',review_revision:1,project_version:1,feature:'risk_analysis',result:{method:'model',risks:[{title:'OUTDATED'}]}}];
  assert.doesNotMatch(c.window.CommitmentUI.riskView(c.state.activeReview),/OUTDATED/);
});
test('model risks are escaped, actionable and labelled as advice, not verification',()=>{
  const c=setup(); c.state.aiRuns=[{review_id:'review-a',review_revision:2,project_version:1,feature:'risk_analysis',result:{method:'model',model:'test-glm',sources:[],limitations:[],risks:[{severity:'high',title:'<script>unsafe</script>',detail:'A possible leak',check:'Assert only public fields',citation_ids:[]}]}}];
  const html=c.window.CommitmentUI.riskView(c.state.activeReview);
  assert.match(html,/&lt;script&gt;/); assert.doesNotMatch(html,/<script>/);
  assert.match(html,/Assert only public fields/); assert.match(html,/not verification/);
});
test('fallback must not render no-risks as a successful model assessment',()=>{
  const c=setup(); c.state.aiRuns=[{review_id:'review-a',review_revision:2,project_version:1,feature:'risk_analysis',result:{method:'local-extraction',fallback_reason:'timeout',risks:[],sources:[],limitations:[]}}];
  const html=c.window.CommitmentUI.riskView(c.state.activeReview);
  assert.match(html,/AI analysis unavailable/); assert.doesNotMatch(html,/No specific risk identified/);
});
