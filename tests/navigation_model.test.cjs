const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = path.join(__dirname, '../system/web/static/navigation-model.js');
const model = fs.existsSync(file) ? require(file) : {};

const first = {id:'r1', project_id:'p1', status:'open'};
const second = {id:'r2', project_id:'p1', status:'open'};
const decided = {id:'r3', project_id:'p1', status:'committed'};
const other = {id:'r9', project_id:'p2', status:'open'};

function session() {
  assert.equal(typeof model.createSession, 'function');
  return model.createSession();
}

test('returning from Project or Rules reopens the same review and section', () => {
  const nav = session();
  assert.equal(nav.remember('p1', 'r2', 'evidence'), true);
  const restored = nav.restore('p1', [first, second, decided]);
  assert.equal(restored.review, second);
  assert.equal(restored.section, 'evidence');
  nav.remember('p1', 'r2', 'audit');
  assert.equal(nav.restore('p1', [first, second]).section, 'audit');
  nav.remember('p1', 'r3', 'changes');
  assert.deepEqual(nav.restore('p1', [first, second, decided]), {review:decided, section:'changes'});
});

test('without a remembered review the first eligible review opens at its overview', () => {
  const nav = session();
  assert.deepEqual(nav.restore('p1', [first, second]), {review:first, section:'overview'});
  assert.equal(nav.remember('p1', 'r2'), true);
  assert.deepEqual(nav.restore('p1', [first, second]), {review:second, section:'overview'});
});

test('each project keeps its own place and never receives another project review', () => {
  const nav = session();
  nav.remember('p1', 'r2', 'changes');
  nav.remember('p2', 'r9', 'evidence');
  assert.deepEqual(nav.restore('p1', [first, second]), {review:second, section:'changes'});
  assert.deepEqual(nav.restore('p2', [other]), {review:other, section:'evidence'});

  const p2Review = {id:'r8', project_id:'p2'};
  assert.deepEqual(nav.restore('p2', [second, p2Review]), {review:p2Review, section:'overview'});
  assert.equal(nav.restore('p2', [first, second]), null);
  assert.equal(nav.restore('p3', [first, other]), null);
});

test('a remembered ID in another project scope is not restored by ID alone', () => {
  const nav = session();
  nav.remember('p2', 'r2', 'audit');
  const local = {id:'r7', project_id:'p2'};
  assert.deepEqual(nav.restore('p2', [second, local]), {review:local, section:'overview'});
});

test('reviews without project_id are accepted within the caller scope', () => {
  const nav = session();
  const unscoped = {id:'r5'};
  nav.remember('p1', 'r5', 'changes');
  assert.deepEqual(nav.restore('p1', [first, unscoped]), {review:unscoped, section:'changes'});
});

test('filtered-out or removed reviews are not invented, and a cleared filter restores them', () => {
  const nav = session();
  nav.remember('p1', 'r2', 'evidence');

  const filtered = nav.restore('p1', [first]);
  assert.deepEqual(filtered, {review:first, section:'overview'});
  assert.notEqual(filtered.review.id, 'r2');

  assert.deepEqual(nav.restore('p1', [first, second]), {review:second, section:'evidence'});

  const removed = nav.restore('p1', [first, decided]);
  assert.deepEqual(removed.review, first);
  assert.equal(removed.section, 'overview');
});

test('the returned review is the caller object, and mutating a result does not change the session', () => {
  const nav = session();
  nav.remember('p1', 'r2', 'evidence');
  const restored = nav.restore('p1', [first, second]);
  assert.equal(restored.review, second);
  restored.section = 'audit';
  assert.equal(nav.restore('p1', [first, second]).section, 'evidence');
});

test('invalid sections fall back to overview', () => {
  const nav = session();
  for (const section of ['decision', 'Evidence', '', null, 42, '__proto__', 'constructor']) {
    nav.remember('p1', 'r2', section);
    assert.equal(nav.restore('p1', [first, second]).section, 'overview', String(section));
  }
  nav.remember('p1', 'r2', undefined);
  assert.equal(nav.restore('p1', [first, second]).section, 'overview');
  assert.deepEqual([...model.SECTIONS], ['overview', 'changes', 'evidence', 'audit']);
  assert.ok(Object.isFrozen(model.SECTIONS));
});

test('invalid identities are ignored instead of overwriting a remembered place', () => {
  const nav = session();
  nav.remember('p1', 'r2', 'evidence');
  for (const [projectId, reviewId] of [['', 'r1'], ['p1', ''], ['p1', null], [null, 'r1'], [undefined, undefined], ['p1', 7]]) {
    assert.equal(nav.remember(projectId, reviewId, 'audit'), false);
  }
  assert.deepEqual(nav.restore('p1', [first, second]), {review:second, section:'evidence'});
});

test('empty, missing or malformed review lists return null', () => {
  const nav = session();
  nav.remember('p1', 'r2', 'evidence');
  for (const input of [[], undefined, null, 'r2', {id:'r2'}, [null, {}, {id:''}, {id:42}]]) {
    assert.equal(nav.restore('p1', input), null);
  }
  assert.equal(nav.restore('', [first]), null);
  assert.equal(nav.restore(undefined, [first]), null);
  assert.deepEqual(nav.restore('p1', [null, {}, second]), {review:second, section:'evidence'});
});

test('clear forgets every project, as on sign out', () => {
  const nav = session();
  nav.remember('p1', 'r2', 'evidence');
  nav.remember('p2', 'r9', 'audit');
  nav.clear();
  assert.deepEqual(nav.restore('p1', [first, second]), {review:first, section:'overview'});
  assert.deepEqual(nav.restore('p2', [other]), {review:other, section:'overview'});
});

test('sessions are independent and in memory only', () => {
  const one = session();
  const two = session();
  one.remember('p1', 'r2', 'evidence');
  assert.deepEqual(two.restore('p1', [first, second]), {review:first, section:'overview'});
  assert.doesNotMatch(fs.readFileSync(file, 'utf8'), /localStorage|sessionStorage|indexedDB|document\.cookie/);
});
