const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const filename = path.join(__dirname, '../system/web/static/assistant-model.js');
const model = fs.existsSync(filename) ? require(filename) : {};
const project = {id:'p',version:42};
const review = {id:'a',project_id:'p',revision:1,target_ref:'target',findings:[{id:'f',path:'connector.py'}],changed_paths:['connector.py'],evidence:[{id:'e'}],evidence_obligations:[{id:'o'}],decision_records:[]};
const run = {id:'run',feature:'review_copilot',review_id:'a',project_id:'p',review_revision:1,project_version:42,quality_flags:[]};

test('question drafts and answer selection belong to one review in one authenticated session', () => {
  assert.equal(typeof model.createSession,'function');
  const session = model.createSession();
  session.syncOwner('user','csrf');
  const a = session.get(review,project);
  a.question = 'Which record is missing?';
  a.deliberate = false;
  a.runId = 'run';
  assert.equal(session.get({...review,id:'b'},project).question,'');
  assert.equal(session.get(review,project),a);
  assert.equal(session.get(review,project).question,'Which record is missing?');
  session.syncOwner('user','new-csrf');
  assert.equal(session.owns(a),false,'A fresh sign-in by the same person must clear transient state');
  assert.equal(session.get(review,project).question,'');
});

test('one operation owns pending state; completion cannot affect a newer or revoked session', () => {
  assert.equal(typeof model.createSession,'function');
  const session = model.createSession(); session.syncOwner('u','c');
  const a = session.get(review,project);
  const op = session.begin(a,review,project,'ask');
  assert.ok(op);
  assert.equal(session.begin(a,review,project,'plan'),null);
  assert.equal(session.finish(op,'Ready','success'),true);
  const next = session.begin(a,review,project,'plan');
  assert.equal(session.finish(op,'Old error','error'),false);
  assert.equal(a.pending,next);
  session.syncOwner(null,null);
  assert.equal(session.finish(next,'Ready','success'),false);
});

test('current answers require review, project, version, revision and nonlegacy provenance', () => {
  assert.equal(typeof model.isCurrent,'function');
  assert.equal(model.isCurrent(run,review,project),true);
  for (const change of [{review_id:'b'},{project_id:'q'},{review_revision:2},{project_version:41},{quality_flags:['legacy_unversioned_context']}]) {
    assert.equal(model.isCurrent({...run,...change},review,project),false);
  }
  assert.equal(model.isCurrent(null,review,project),false);
});

test('operation view ownership includes target context, not merely the review ID', () => {
  assert.equal(typeof model.contextMatches,'function');
  const session = model.createSession(); session.syncOwner('u','c');
  const op = session.begin(session.get(review,project),review,project,'ask');
  assert.equal(model.contextMatches(op,review,project),true);
  assert.equal(model.contextMatches(op,{...review,revision:2},project),false);
  assert.equal(model.contextMatches(op,{...review,target_ref:'new'},project),false);
  assert.equal(model.contextMatches(op,review,{...project,version:43}),false);
});

test('sources navigate only to actual records; model IDs cannot become arbitrary links or actions', () => {
  assert.equal(typeof model.sourceTarget,'function');
  assert.deepEqual(model.sourceTarget({id:'finding:f'},review,project,{}),{kind:'finding',id:'f',path:'connector.py'});
  assert.deepEqual(model.sourceTarget({id:'evidence:e'},review,project,{}),{kind:'evidence',id:'e'});
  assert.deepEqual(model.sourceTarget({id:'obligation:o'},review,project,{}),{kind:'obligation',id:'o'});
  assert.deepEqual(model.sourceTarget({id:'admission:tests'},review,project,{admission_checks:[{key:'tests'}]}),{kind:'admission',id:'tests'});
  assert.equal(model.sourceTarget({id:'finding:not-real'},review,project,{}),null);
  assert.equal(model.sourceTarget({id:'https://evil.test'},review,project,{}),null);
  assert.equal(model.sourceTarget({id:'workflow:approve'},review,project,{}),null);
});

test('error recovery distinguishes changed context, access, availability and connectivity', () => {
  assert.equal(typeof model.errorMessage,'function');
  assert.match(model.errorMessage({status:409,message:'Context changed'}),/changed.*refresh/i);
  assert.match(model.errorMessage({status:403,message:'Denied'}),/permission/i);
  assert.match(model.errorMessage({status:503,message:'Unavailable'}),/retry/i);
  assert.doesNotMatch(model.errorMessage({status:503,message:'Unavailable'}),/configuration/i);
  assert.match(model.errorMessage({message:'Failed to fetch'}),/connection/i);
  assert.match(model.errorMessage({status:422,message:'Question is too long'}),/Question is too long/);
});
