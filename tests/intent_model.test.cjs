const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const I18n = require('../system/web/static/i18n.js');
I18n.setLanguage('en');
const modulePath = path.join(__dirname, '../system/web/static/intent-model.js');
const model = fs.existsSync(modulePath) ? require(modulePath) : {};

test('request scope distinguishes a complete non-Python snapshot from an unknown one', () => {
  const tree = {entries:[{kind:'file',path:'App.tsx'},{kind:'directory',path:'folder.py'}],truncated:false};
  const before = JSON.stringify(tree);
  assert.deepEqual(model.repositoryScope(tree), {state:'no_python',pythonFiles:0});
  for (const partial of [null, {error:'Unavailable'}, {...tree,truncated:true}]) {
    assert.equal(model.repositoryScope(partial).state,'unknown');
  }
  assert.equal(model.repositoryScope(tree,true).state,'unknown');
  assert.equal(JSON.stringify(tree),before);
});

test('a Python path signals candidate applicability, not that a change has been verified', () => {
  assert.deepEqual(model.repositoryScope({entries:[{kind:'file',path:'src/app.py'},{kind:'file',path:'App.tsx'}],truncated:true}),
    {state:'python_found',pythonFiles:1});
});
const candidate = (id, overrides = {}) => ({
  id, status: 'active', title: `Interpretation ${id}`, summary: `Reason for ${id}`,
  structural_delta: {kind: 'python_import_substitution', path: `${id}.py`, from_module: `old.${id}`, to_module: `new.${id}`},
  uncertainties: ['Preserve behavior?', 'Keep the authority boundary?'], provenance: 'model/advisory', confidence: 0.7, ...overrides,
});

test('AI drafts retain every alternative, its own delta and source without mutating the run', () => {
  assert.equal(typeof model.fromAIRun, 'function');
  const run = {id: 'run-123', result: {candidates: [candidate('a'), candidate('b'), candidate('c')]}};
  const original = JSON.stringify(run);
  const drafts = model.fromAIRun(run);
  assert.equal(drafts.length, 3);
  assert.deepEqual(drafts[1].structural_delta, run.result.candidates[1].structural_delta);
  assert.equal(drafts[1].summary, 'Reason for b');
  assert.equal(drafts[1].confidence, 0.7);
  assert.match(drafts[1].provenance, /model\/advisory.*run-123/);
  drafts[0].uncertainties.pop();
  assert.equal(JSON.stringify(run), original);
});

test('candidate edits keep source lineage and do not turn separate questions into one', () => {
  assert.equal(typeof model.editCandidate, 'function');
  const original = candidate('b');
  const draft = model.editCandidate(original, {title: 'Adjusted B', path: 'b.py', from_module: 'old.b', to_module: 'new.b', summary: 'Reason for b', uncertainties: 'Preserve behavior?\nKeep the authority boundary?'});
  assert.equal(draft.title, 'Adjusted B');
  assert.equal(draft.provenance, 'model/advisory; human-edited');
  assert.equal(draft.confidence, null);
  assert.deepEqual(draft.uncertainties, original.uncertainties);
  assert.equal(original.title, 'Interpretation b');
  assert.equal(model.editCandidate(draft, {title: 'Adjusted again', path: 'b.py', from_module: 'old.b', to_module: 'new.b', summary: 'Reason for b', uncertainties: ''}).provenance, draft.provenance);
});

test('clarification keeps all candidates by default and only resolves checked questions', () => {
  assert.equal(typeof model.clarificationPayload, 'function');
  const intent = {revision: 3, candidates: [candidate('a'), candidate('b')]};
  const result = model.clarificationPayload(intent, {question: 'Scope?', answer: 'Narrow scope.', retained: ['a', 'b'], resolved: {a: [1]}});
  assert.deepEqual(result.retained_candidate_ids, ['a', 'b']);
  assert.deepEqual(result.eliminated_candidate_ids, []);
  assert.deepEqual(result.resolved_uncertainties, {a: ['Keep the authority boundary?']});
  assert.equal(result.expected_revision, 3);
  assert.deepEqual(intent.candidates[0].uncertainties, ['Preserve behavior?', 'Keep the authority boundary?']);
});

test('clarification refuses accidental elimination of every alternative or stale IDs', () => {
  assert.equal(typeof model.clarificationPayload, 'function');
  const intent = {revision: 2, candidates: [candidate('a'), candidate('b')]};
  const values = {question: 'Scope?', answer: 'Narrow scope.', resolved: {}};
  assert.throws(() => model.clarificationPayload(intent, {...values, retained: []}), /Keep at least one/);
  assert.throws(() => model.clarificationPayload(intent, {...values, retained: ['missing']}), /changed/);
  assert.throws(() => model.clarificationPayload(intent, {...values, retained: ['a'], resolved: {a: [7]}}), /changed/);
  const result = model.clarificationPayload(intent, {...values, retained: ['a'], resolved: {b: [0]}});
  assert.deepEqual(result.eliminated_candidate_ids, ['b']);
  assert.deepEqual(result.resolved_uncertainties, {});
});

test('a resolved candidate can be selected without first eliminating its alternatives', () => {
  assert.equal(typeof model.nextAction, 'function');
  const intent = {status: 'clarification_required', candidates: [candidate('a', {uncertainties: []}), candidate('b')]};
  assert.equal(model.canSelect(intent, intent.candidates[0]), true);
  assert.equal(model.canSelect(intent, intent.candidates[1]), false);
  assert.match(model.nextAction(intent), /Select/);
  intent.status = 'selected';
  assert.equal(model.canSelect(intent, intent.candidates[0]), false);
  assert.match(model.nextAction(intent), /isolated/);
});

const valuesFor = item => ({title:item.title, summary:item.summary, ...item.structural_delta, uncertainties:item.uncertainties.join('\n')});

test('saved proposal revision retains every alternative and uses the inspected revision', () => {
  assert.equal(typeof model.revisionPayload, 'function');
  const intent={revision:7,status:'clarification_required',candidates:[candidate('a'),candidate('b')]};
  const before=JSON.stringify(intent);
  const payload=model.revisionPayload(intent,{candidateId:'a',values:{...valuesFor(intent.candidates[0]),to_module:'new.versioned'},reason:'The owner confirmed the versioned entry point.'});
  assert.equal(payload.expected_revision,7);
  assert.deepEqual(payload.retained_candidate_ids,['a','b']);
  assert.deepEqual(payload.eliminated_candidate_ids,[]);
  assert.deepEqual(payload.resolved_uncertainties,{});
  assert.deepEqual(payload.added_candidates,[]);
  assert.deepEqual(Object.keys(payload.candidate_revisions),['a']);
  assert.equal(payload.candidate_revisions.a.structural_delta.to_module,'new.versioned');
  assert.equal(payload.candidate_revisions.a.confidence,null);
  assert.match(payload.candidate_revisions.a.provenance,/model\/advisory; human-edited/);
  assert.deepEqual(payload.candidate_revisions.a.uncertainties,intent.candidates[0].uncertainties);
  assert.equal(JSON.stringify(intent),before);
});

test('an added alternative is human-authored and leaves server identity allocation intact', () => {
  assert.equal(typeof model.revisionPayload, 'function');
  const intent={revision:2,status:'ready_for_selection',candidates:[candidate('a'),candidate('b',{status:'eliminated'})]};
  const payload=model.revisionPayload(intent,{values:valuesFor(candidate('c')),reason:'A bounded adapter is another valid approach.'});
  assert.deepEqual(payload.retained_candidate_ids,['a']);
  assert.deepEqual(payload.candidate_revisions,{});
  assert.equal(payload.added_candidates.length,1);
  assert.equal(payload.added_candidates[0].id,undefined);
  assert.equal(payload.added_candidates[0].status,'active');
  assert.equal(payload.added_candidates[0].confidence,null);
  assert.equal(payload.added_candidates[0].provenance,'human-authored/added-alternative');
});

test('saved proposal editing rejects locked, eliminated, unchanged and over-limit updates', () => {
  assert.equal(typeof model.revisionPayload, 'function');
  const intent={revision:1,status:'clarification_required',candidates:[candidate('a'),candidate('b',{status:'eliminated'})]};
  const args={candidateId:'a',values:{...valuesFor(candidate('a')),title:'Adjusted'},reason:'The scope was corrected.'};
  assert.throws(()=>model.revisionPayload({...intent,status:'selected'},args),/selected|locked/i);
  assert.throws(()=>model.revisionPayload(intent,{...args,candidateId:'b'}),/active/i);
  assert.throws(()=>model.revisionPayload(intent,{...args,values:valuesFor(candidate('a'))}),/No proposal changes/i);
  assert.throws(()=>model.revisionPayload({...intent,candidates:Array.from({length:20},(_,i)=>candidate(String(i)))},{...args,candidateId:null}),/20/);
  assert.throws(()=>model.revisionPayload(intent,{...args,reason:' '}),/Explain/);
  assert.throws(()=>model.revisionPayload(intent,{...args,values:{...args.values,path:'../outside.py'}}),/repository-relative Python/);
  assert.throws(()=>model.revisionPayload(intent,{...args,values:{...args.values,to_module:'new-module'}}),/Python module/);
  assert.throws(()=>model.revisionPayload(intent,{...args,values:{...args.values,to_module:'old.a'}}),/differ/);
});

test('revision comparison names changes and rebase preserves concurrent fields the author did not edit', () => {
  assert.equal(typeof model.candidateChanges,'function');
  assert.equal(typeof model.rebaseCandidate,'function');
  const original=candidate('a'),latest=candidate('a',{summary:'A collaborator improved the explanation.'});
  const values={...valuesFor(original),to_module:'new.versioned'};
  const edited=model.editCandidate(original,values);
  assert.deepEqual(model.candidateChanges(original,edited),[{field:'to_module',label:'Replace with',before:'new.a',after:'new.versioned'}]);
  const rebased=model.rebaseCandidate(original,latest,values);
  assert.equal(rebased.summary,latest.summary);
  assert.equal(rebased.to_module,'new.versioned');
  assert.equal(original.summary,'Reason for a');
  assert.equal(latest.structural_delta.to_module,'new.a');
});

test('ambiguous save recovery recognizes only the exact attributed next-revision operation', () => {
  assert.equal(typeof model.recordedRevision,'function');
  const intent={revision:1,status:'clarification_required',candidates:[candidate('a'),candidate('b')]};
  const payload=model.revisionPayload(intent,{candidateId:'a',values:{...valuesFor(candidate('a')),title:'Adjusted'},reason:'The owner clarified the scope.'});
  const turn={intent_revision:2,question:payload.question,answer:payload.answer,actor:'architect@example.test',revised_candidate_ids:['a'],added_candidate_ids:[],after_candidates:[payload.candidate_revisions.a,candidate('b')]};
  assert.equal(model.recordedRevision({clarification_history:[turn]},payload,'architect@example.test'),true);
  assert.equal(model.recordedRevision({clarification_history:[{...turn,actor:'someone-else'}]},payload,'architect@example.test'),false);
  assert.equal(model.recordedRevision({clarification_history:[{...turn,intent_revision:3}]},payload,'architect@example.test'),false);
  assert.equal(model.recordedRevision({clarification_history:[{...turn,revised_candidate_ids:['a','b']}]},payload,'architect@example.test'),false,'Recovery must match the exact operation, not a larger concurrent edit');
});

test('reopening a busy composer does not lose the original button label', () => {
  const source = fs.readFileSync(path.join(__dirname, '../system/web/static/app.js'), 'utf8');
  const body = source.slice(source.indexOf('function setBusy('), source.indexOf('function setIconButtonFeedback('));
  const setBusy = vm.runInNewContext(`${body}\nsetBusy`, {esc: String, I18n});
  const attributes = new Map();
  const button = {innerHTML:'Draft with AI',dataset:{},disabled:false,setAttribute:(key,value)=>attributes.set(key,value),getAttribute:key=>attributes.get(key),removeAttribute:key=>attributes.delete(key)};
  setBusy(button, true, 'Interpreting…');
  setBusy(button, true, 'Interpreting…');
  setBusy(button, false);
  assert.equal(button.innerHTML, 'Draft with AI');
  assert.equal(button.disabled, false);
  assert.equal(attributes.has('aria-busy'), false);
});
