const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const modelPath = path.join(__dirname, '../system/web/static/diff-model.js');
const model = fs.existsSync(modelPath) ? require(modelPath) : {};
const patch = 'diff --git a/a.py b/a.py\nindex aaa..bbb 100644\n--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,3 @@\n-old\n+new\n+\n context\n';

test('a file view selects exactly one path and navigates the filtered set', () => {
  assert.equal(typeof model.fileView, 'function');
  const files = [{path:'a.py'}, {path:'src/b.py'}];
  const view = model.fileView(['a.py', 'src/b.py', 'empty.py'], files, 'src/b.py', '');
  assert.equal(view.selected.path, 'src/b.py');
  assert.equal(view.previous, 'a.py');
  assert.equal(view.next, 'empty.py');
  assert.equal(view.total, 3);
  const filtered = model.fileView(['a.py', 'src/b.py'], files, 'a.py', ' SRC/ ');
  assert.equal(filtered.selected.path, 'src/b.py');
  assert.equal(filtered.previous, null);
  assert.equal(filtered.next, null);
});

test('filter misses and missing/truncated patches do not silently show an unrelated file', () => {
  assert.equal(typeof model.fileView, 'function');
  const empty = model.fileView(['a.py'], [{path:'a.py'}], 'a.py', 'missing');
  assert.equal(empty.selected, null);
  const missing = model.fileView(['a.py', 'b.py'], [{path:'a.py'}], 'b.py', '');
  assert.equal(missing.selected.path, 'b.py');
  assert.equal(missing.selected.file, null);
  assert.equal(model.fileView([], [], null, '').selected, null);
});

test('parse keeps actual hunk lines and trailing empty additions, without phantom lines', () => {
  assert.equal(typeof model.parse, 'function');
  const [file] = model.parse(patch);
  assert.equal(file.additions, 2);
  assert.equal(file.deletions, 1);
  assert.deepEqual(file.rows.filter(r => r.kind === 'ctx'), [{kind:'ctx', text:'context', oldLine:2, newLine:3}]);
  assert.deepEqual(file.rows.find(r => r.kind === 'add' && r.text === ''), {kind:'add', text:'', newLine:2});
  assert.equal(model.parse(patch).length, 1);
});

test('empty, binary, mode-only and renamed files do not gain made-up code rows', () => {
  assert.equal(typeof model.parse, 'function');
  const text = 'diff --git a/empty.py b/empty.py\nnew file mode 100644\nindex 000..e69\ndiff --git a/pic.png b/pic.png\nBinary files a/pic.png and b/pic.png differ\ndiff --git a/run b/run\nold mode 100644\nnew mode 100755\ndiff --git a/old b/new\nsimilarity index 100%\nrename from old\nrename to new\n';
  const files = model.parse(text);
  assert.equal(files.length, 4);
  assert.equal(files[0].status, 'added');
  assert.equal(files[1].binary, true);
  assert.equal(files[3].status, 'renamed');
  assert.equal(files[3].oldPath, 'old');
  assert.ok(files.every(f => f.rows.every(r => r.kind === 'meta')));
});

test('Git quoted UTF-8 paths, spaces and no-newline markers are preserved', () => {
  assert.equal(typeof model.parse, 'function');
  const [file] = model.parse('diff --git "a/\\344\\270\\255.py" "b/\\344\\270\\255.py"\n--- "a/\\344\\270\\255.py"\n+++ "b/\\344\\270\\255.py"\n@@ -1 +1 @@\n-a\n+b\n\\ No newline at end of file\n');
  assert.equal(file.path, '中.py');
  assert.equal(file.rows.at(-1).text, '\\ No newline at end of file');
  assert.equal(model.parse('diff --git a/with space.py b/with space.py\n')[0].path, 'with space.py');
});

test('findings attach to target-side lines, while unknown locations stay explicit', () => {
  assert.equal(typeof model.annotations, 'function');
  const file = {path:'a.py', rows:[{kind:'del',oldLine:1}, {kind:'add',newLine:1}, {kind:'ctx',oldLine:2,newLine:2}]};
  const items = [{id:'new',path:'a.py',line:1}, {id:'outside',path:'a.py',line:50}, {id:'whole',path:'a.py'}, {id:'other',path:'b.py',line:1}];
  const result = model.annotations(file, items);
  assert.deepEqual(result.byRow[1].map(f => f.id), ['new']);
  assert.equal(result.byRow[0], undefined);
  assert.deepEqual(result.unplaced.map(f => f.id), ['outside','whole']);
  assert.equal(items.length, 4);
});

function rendering() {
  const source = fs.readFileSync(path.join(__dirname, '../system/web/static/app.js'), 'utf8');
  const helpers = source.slice(source.indexOf('const CODE_KEYWORDS'), source.indexOf('function renderDiffViewer('));
  return vm.runInNewContext(`${helpers}\nrenderDiffFile`, {
    DiffModel:model,
    esc:value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    sentence:value => String(value), uiIcon:() => '', controlTooltip:() => '',
    effectiveFindingStatus:(_review, item) => item.status || 'open',
  });
}

test('actual diff renderer places a finding after its code and escapes arbitrary content', () => {
  const render = rendering();
  const file = {path:'a.py',oldPath:'a.py',status:'modified',additions:1,deletions:0,rows:[{kind:'add',newLine:5,text:'target_line <unsafe>'}]};
  const html = render(file, {status:'open',findings:[{id:'f1',path:'a.py',line:5,severity:'critical',kind:'unobservable',message:'Finding <unsafe>',rule_id:'authority'}]});
  assert.ok(html.indexOf('target_line') < html.indexOf('Finding &lt;unsafe&gt;'));
  assert.match(html, /data-finding-location="f1"/);
  assert.ok(!html.includes('<unsafe>'));
});

test('actual diff renderer describes a metadata-only file instead of presenting metadata as code', () => {
  const html = rendering()({path:'empty.py',oldPath:'empty.py',status:'added',additions:0,deletions:0,rows:[{kind:'meta',text:'new file mode 100644'}]}, {status:'open',findings:[]});
  assert.match(html, /Empty file added/);
  assert.ok(!html.includes('<table'));
  assert.match(html, /Patch metadata/);
});

test('a partial file never claims an empty file and incomplete hunks are marked partial', () => {
  const html = rendering()({path:'large.py',oldPath:'large.py',status:'added',additions:0,deletions:0,partial:true,rows:[{kind:'meta',text:'new file mode 100644'}]}, {status:'open',findings:[]});
  assert.ok(!html.includes('Empty file added'));
  assert.match(html, /incomplete/i);
  assert.equal(model.parse(patch.slice(0, patch.indexOf(' context')))[0].partial, true);
});

test('the review opens with files as context, with the assistant still available on demand', () => {
  const source = fs.readFileSync(path.join(__dirname, '../system/web/static/app.js'), 'utf8');
  const stateSource = source.slice(0, source.indexOf('let trustSigningPackage'));
  const initial = vm.runInNewContext(`${stateSource}\nstate`, {window:{matchMedia:() => ({matches:true}), location:{search:''}}, URLSearchParams});
  assert.equal(initial.inspectorTab, 'files');
});

test('a late diff response cannot overwrite a newer review revision or end its loading state', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../system/web/static/app.js'), 'utf8');
  const body = source.slice(source.indexOf('async function loadDiffText('), source.indexOf('function renderChangedFiles('));
  const state = {activeReview:{id:'r1',revision:2},diffRequestVersion:2,diffText:'newer',diffLoading:true,diffPromise:'new request'};
  const load = vm.runInNewContext(`${body}\nloadDiffText`, {state,api:async () => ({diff:patch}),parseUnifiedDiff:model.parse,$:() => null,renderDiffViewer:() => {}});
  const result = await load({id:'r1',revision:1}, 1);
  assert.equal(result, null);
  assert.equal(state.diffText, 'newer');
  assert.equal(state.diffLoading, true);
  assert.equal(state.diffPromise, 'new request');
});

function viewerHarness(overrides = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../system/web/static/app.js'), 'utf8');
  const body = source.slice(source.indexOf('function renderDiffViewer('), source.indexOf('function renderDiffNavigation('));
  const viewer = {innerHTML:'',dataset:{path:'a.py'},scrollTop:400,querySelectorAll:() => []};
  const state = {activeReview:{changed_paths:['a.py','b.py'],findings:[]},diffPath:'b.py',diffQuery:'',diffFiles:[{path:'a.py'},{path:'b.py'}],...overrides};
  const render = vm.runInNewContext(`${body}\nrenderDiffViewer`, {state,DiffModel:model,$:selector => selector === '#diff-viewer' ? viewer : null,esc:String,renderDiffNavigation:() => {},renderDiffFile:file => file.path,renderInspectorChangedFiles:() => {}});
  return {viewer, render};
}

test('changing files resets code scroll while rerendering the same file preserves position', () => {
  const {viewer, render} = viewerHarness();
  render();
  assert.equal(viewer.innerHTML, 'b.py');
  assert.equal(viewer.scrollTop, 0);
  viewer.scrollTop = 250;
  render();
  assert.equal(viewer.scrollTop, 250);
});

test('a failed diff request explains recovery in the working pane', () => {
  const {viewer, render} = viewerHarness({diffError:'Failed to fetch'});
  render();
  assert.match(viewer.innerHTML, /Couldn’t load the code changes/);
  assert.match(viewer.innerHTML, /connection/);
  assert.match(viewer.innerHTML, /Try again/);
});

test('closing the raw patch does not hide the warning that the available diff is truncated', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../system/web/static/app.js'), 'utf8');
  const body = source.slice(source.indexOf('async function loadDiff(button)'), source.indexOf('function openTestConfiguration('));
  const classes = () => { const values = new Set(); return {contains:key => values.has(key),toggle:(key,force) => force ? values.add(key) : values.delete(key)}; };
  const output = {classList:classes()}, note = {classList:classes()};
  const button = {dataset:{loaded:'true'},setAttribute:() => {},focus:() => {}};
  const load = vm.runInNewContext(`${body}\nloadDiff`, {state:{activeReview:{id:'r1'},diffTruncated:true},$:selector => selector === '#unified-diff' ? output : note});
  await load(button);
  assert.equal(output.classList.contains('hidden'), true);
  assert.equal(note.classList.contains('hidden'), false);
});

test('file counts are unknown until parsed, not guessed from the scaled Git stat bars', () => {
  const source = fs.readFileSync(path.join(__dirname, '../system/web/static/app.js'), 'utf8');
  const body = source.slice(source.indexOf('function changedFileStats('), source.indexOf('function parseUnifiedDiff('));
  const state = {diffFiles:[]};
  const stats = vm.runInNewContext(`${body}\nchangedFileStats`, {state});
  const review = {changed_paths:['a.py'],patch_summary:' a.py | 100 +++---'};
  assert.equal(stats(review)[0].additions, null);
  assert.equal(stats(review)[0].deletions, null);
  assert.equal(stats(review)[0].changeType, 'Changed');
  state.diffFiles = [{path:'a.py',additions:12,deletions:4,status:'modified',partial:true}];
  assert.equal(stats(review)[0].additions, 12);
  assert.equal(stats(review)[0].partial, true);
});
