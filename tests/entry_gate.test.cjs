const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const source = readFileSync(join(__dirname, '../system/web/static/entry.js'), 'utf8');

// Virtual time covers the slow-start race without delaying the test suite.
// Resource-failure classification and layout are tested in the real browser.
function entry(protocol = 'http:') {
  const nodes = new Map(['entry-gate','entry-title','entry-copy','entry-retry','entry-service-address'].map(id => [
    `#${id}`, {hidden: false, dataset: {}, textContent: '', addEventListener() {}},
  ]));
  const events = new Map();
  const timers = new Map();
  const classes = new Set(['entry-pending']);
  const document = {
    documentElement: {dataset: {}},
    body: {classList: {remove: name => classes.delete(name)}},
    querySelector: selector => nodes.get(selector),
    addEventListener: (name, fn) => events.set(name, fn),
  };
  const window = {location: {protocol, origin: 'http://127.0.0.1:8776'}, addEventListener() {}};
  runInNewContext(source, {window, document, setTimeout: (fn, delay) => {timers.set(1, {fn, delay}); return 1;}, clearTimeout: id => timers.delete(id)});
  return {window, document, nodes, timers, classes, mount: () => events.get('DOMContentLoaded')()};
}

test('slow startup offers recovery after ten seconds, with no credential form exposed', () => {
  const app = entry();
  app.mount();
  assert.equal(app.nodes.get('#entry-gate').dataset.state, 'loading');
  const timeout = [...app.timers.values()][0];
  assert.equal(timeout.delay, 10000);
  timeout.fn();
  assert.equal(app.nodes.get('#entry-gate').dataset.state, 'error');
  assert.match(app.nodes.get('#entry-copy').textContent, /taking longer/);
  assert.equal(app.nodes.get('#entry-retry').textContent, 'Try again');
  assert.equal(app.classes.has('entry-pending'), true);
});

test('a late successful response can recover the slow-start screen', () => {
  const app = entry();
  app.mount();
  [...app.timers.values()][0].fn();
  app.window.EntryGate.ready();
  assert.equal(app.nodes.get('#entry-gate').hidden, true);
  assert.equal(app.classes.has('entry-pending'), false);
  assert.equal(app.timers.size, 0);
  app.window.EntryGate.fail('An obsolete failure');
  assert.equal(app.nodes.get('#entry-gate').hidden, true);
});

test('a failure before DOM readiness remains actionable after mount', () => {
  const app = entry();
  app.window.EntryGate.fail('The service is unavailable. Try again.');
  app.mount();
  assert.equal(app.nodes.get('#entry-gate').dataset.state, 'error');
  assert.match(app.nodes.get('#entry-copy').textContent, /service is unavailable/);
  assert.equal(app.timers.size, 0);
});

test('direct-file entry never dismisses its service-launch guide or starts a timer', () => {
  const app = entry('file:');
  app.mount();
  app.window.EntryGate.ready();
  app.window.EntryGate.fail('Unavailable');
  assert.equal(app.document.documentElement.dataset.entry, 'file');
  assert.equal(app.nodes.get('#entry-gate').hidden, false);
  assert.equal(app.classes.has('entry-pending'), true);
  assert.equal(app.timers.size, 0);
});
