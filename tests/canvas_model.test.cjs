const assert = require("node:assert/strict");
const { test } = require("node:test");
const model = require("../system/web/static/canvas-model.js");
const project = { name: "Capability control", version: 42, head_ref: "abc123", claims: [{ id: "C1", title: "Scoped authority", status: "validated" }] };
const review = (id, values = {}) => ({ id, status: "open", created_at: "2026-10-01T00:00:00Z", intent_summary: `Change ${id}`, changed_paths: ["connectors/archive.py"], findings: [], ...values });

test("attention is prioritized without mutating the source review order", () => {
  const input = [review("new", { created_at: "2026-10-03T00:00:00Z" }), review("old", { findings: [{ status: "open", severity: "critical" }] }), review("stale", { status: "rebase_required" })];
  assert.deepEqual(model.orderedReviews(input).map((item) => item.id), ["old", "stale", "new"]);
  assert.deepEqual(input.map((item) => item.id), ["new", "old", "stale"]);
  assert.equal(model.reviewTone(review("resolved", { findings: [{ status: "resolved", severity: "critical" }] })), "open");
});

test("intent, proposal, shared artifact and claim remain linked with valid endpoints", () => {
  const graph = model.build(project, [review("one", { claim_deltas: [{ claim_id: "C1", status: "unobservable", artifact_anchors: [{ path: "connectors/archive.py", relation: "observes" }] }] }), review("two")], [{ id: "intent", request: "Use scoped capabilities", status: "realized", realized_review_id: "two" }]);
  const ids = new Set(graph.nodes.map((node) => node.data.id));
  assert.equal(ids.size, graph.nodes.length);
  assert.equal(graph.nodes.filter((node) => node.data.type === "artifact").length, 1);
  assert.equal(graph.edges.filter((edge) => edge.data.relation === "changes").length, 2);
  for (const { data } of graph.edges) assert.ok(ids.has(data.source) && ids.has(data.target));
  assert.ok(graph.edges.some(({ data }) => data.relation === "inconclusive"));
  assert.ok(graph.edges.some(({ data }) => data.source === "intent:intent" && data.target === "review:two" && data.relation === "realizes"));
});

test("search matches full paths and long text, preserves one-hop context, and recovers from no match", () => {
  const request = "A long original request ".repeat(8) + "distinctive-final-word";
  const graph = model.build(project, [review("one", { intent_summary: request })]);
  assert.equal(model.matches(graph.nodes, "DISTINCTIVE-final-word")[0].data.id, "review:one");
  const matches = model.matches(graph.nodes, "connectors archive");
  assert.deepEqual(matches.map((node) => node.data.id), ["artifact:connectors/archive.py"]);
  assert.deepEqual([...model.neighborhood(matches.map((node) => node.data.id), graph.edges)].sort(), ["artifact:connectors/archive.py", "review:one"]);
  assert.equal(model.matches(graph.nodes, "nonexistent").length, 0);
  assert.equal(model.matches(graph.nodes, "  ").length, graph.nodes.length);
  const longClaim = model.build({ ...project, claims: [{ id: "long", title: "Claim title ".repeat(20) + "tail-only" }] }, []);
  assert.equal(model.matches(longClaim.nodes, "tail-only")[0].data.id, "claim:long");
});

test("large and shared-file graphs have finite, non-overlapping object positions", () => {
  const reviews = Array.from({ length: 30 }, (_, i) => review(`r${i}`, { changed_paths: Array.from({ length: 6 }, (_, f) => `dir${i}/file${f}.py`).concat("shared.py") }));
  const intents = reviews.map((item) => ({ id: `intent-${item.id}`, request: `Request ${item.id}`, status: "realized", realized_review_id: item.id }));
  intents.push({ id: "unrealized", request: "Still ambiguous", status: "clarification_required" });
  const graph = model.build(project, reviews, intents);
  for (const [index, node] of graph.nodes.entries()) {
    assert.ok(Number.isFinite(node.position.x) && Number.isFinite(node.position.y));
    for (const other of graph.nodes.slice(index + 1)) {
      if (node.position.x === other.position.x) assert.ok(Math.abs(node.position.y - other.position.y) >= 66, `${node.data.id} overlaps ${other.data.id}`);
    }
  }
  assert.equal(graph.nodes.filter((node) => node.data.path === "shared.py").length, 1);
  assert.equal(graph.nodes.filter((node) => node.data.type === "review").length, 30);
});

test("empty projects and missing intent review links remain honest and renderable", () => {
  const graph = model.build({ ...project, claims: [] }, [], [{ id: "pending", request: "Unrealized", status: "selected", realized_review_id: "missing" }]);
  assert.deepEqual(graph.nodes.map((node) => node.data.type), ["state", "intent"]);
  assert.equal(graph.edges.length, 0);
  assert.ok(graph.nodes.every((node) => Number.isFinite(node.position.y)));
});

test("the initial focus chooses attention, unresolved intent, open change, then state", () => {
  const pending = { id: "ambiguous", request: "Clarify the authority boundary", status: "clarification_required" };
  let graph = model.build(project, [review("open"), review("blocked", { status: "rebase_required" })], [pending]);
  assert.equal(model.preferredFocus(graph), "review:blocked");
  graph = model.build(project, [review("open")], [pending]);
  assert.equal(model.preferredFocus(graph), "intent:ambiguous");
  assert.equal(model.preferredFocus(model.build(project, [review("open")], [])), "review:open");
  assert.equal(model.preferredFocus(model.build(project, [], [])), "state");
});

test("focusing a change retains its state, claim, intent and files without unrelated changes", () => {
  const graph = model.build(project, [review("one", { claim_deltas: [{claim_id:"C1",status:"unobservable"}] }), review("two", {changed_paths:["other.py"]})], [{id:"intent",request:"Use scoped capabilities",status:"realized",realized_review_id:"one"}]);
  const before = JSON.stringify(graph);
  const focused = model.focused(graph, "review:one");
  assert.deepEqual(focused.nodes.map(n=>n.data.id).sort(), ["state","claim:C1","review:one","intent:intent","artifact:connectors/archive.py"].sort());
  const ids = new Set(focused.nodes.map(n=>n.data.id));
  assert.ok(focused.edges.every(e=>ids.has(e.data.source)&&ids.has(e.data.target)));
  assert.equal(JSON.stringify(graph), before, "Scoping and framing never mutate the project graph");
  assert.ok(model.focused(graph,"intent:intent").nodes.some(n=>n.data.id==="artifact:connectors/archive.py"), "Realized intent keeps implementation context");
});

test("compact focus uses one readable flow and preserves every direct relationship", () => {
  const graph = model.build(project, [review("one", {changed_paths:Array.from({length:20},(_,i)=>`dir/file${i}.py`),claim_deltas:[{claim_id:"C1",status:"proposed"}]})]);
  const focused = model.focused(graph, "review:one", {compact:true});
  assert.equal(focused.nodes.length,23);
  assert.equal(new Set(focused.nodes.map(n=>n.position.x)).size,1);
  const ys=focused.nodes.map(n=>n.position.y).sort((a,b)=>a-b);
  assert.ok(ys.slice(1).every((y,i)=>y-ys[i]>=100));
  assert.equal(model.focused(graph,"missing").nodes.length,0, "A missing object is not silently replaced with another change");
});

test("known missing tests and stale evidence are visible as attention, not an approval judgment",()=>{
  const missing=review('missing',{evidence:[{kind:'tests',status:'not_run',freshness:'current'}]});
  assert.equal(model.reviewTone(missing),'attention');
  assert.equal(model.reviewTone(review('stale',{evidence:[{kind:'git',status:'pass',freshness:'stale'}]})),'attention');
  assert.equal(model.reviewTone(review('unknown')),'open','Absent list data cannot invent a failed check');
  assert.equal(model.reviewTone({...missing,status:'committed'}),'committed');
});

test("directory overview preserves actual membership while reducing an unanchored file fan-out",()=>{
  assert.equal(typeof model.directoryOverview,'function');
  const source=model.build({...project,claims:[]},[review('one',{changed_paths:['App.tsx','components/Card.tsx','components/Hint.tsx','services/ai.ts']})]);
  const before=JSON.stringify(source),graph=model.directoryOverview(source);
  const groups=graph.nodes.filter(n=>n.data.type==='directory');
  assert.deepEqual(groups.map(n=>[n.data.directory,n.data.paths]).sort(),[['Repository root',['App.tsx']],['components',['components/Card.tsx','components/Hint.tsx']],['services',['services/ai.ts']]].sort());
  assert.equal(graph.nodes.length,5);
  assert.equal(graph.edges.filter(e=>e.data.relation==='changes_in').length,3);
  const ids=new Set(graph.nodes.map(n=>n.data.id));
  assert.ok(graph.edges.every(e=>ids.has(e.data.source)&&ids.has(e.data.target)));
  assert.ok(graph.nodes.every(n=>Number.isFinite(n.position.x)&&Number.isFinite(n.position.y)));
  assert.equal(JSON.stringify(source),before);
});

test("overview never folds away anchored relationships or duplicates shared files",()=>{
  const source=model.build(project,[review('one',{changed_paths:['components/Card.tsx','shared.ts'],claim_deltas:[{claim_id:'C1',status:'proposed',artifact_anchors:[{path:'components/Card.tsx',relation:'observes'}]}]}),review('two',{changed_paths:['shared.ts']})]);
  const graph=model.directoryOverview(source);
  assert.ok(graph.nodes.some(n=>n.data.id==='artifact:components/Card.tsx'));
  assert.ok(graph.edges.some(e=>e.data.relation==='observes'));
  assert.equal(graph.nodes.find(n=>n.data.type==='directory').data.paths.length,1);
  assert.equal(graph.edges.filter(e=>e.data.relation==='changes_in').length,2);
});

test("directory search finds full member paths and empty projects remain honest",()=>{
  const source=model.build({...project,claims:[]},[review('one',{changed_paths:['services/geminiService.ts']})]);
  const graph=model.directoryOverview(source);
  assert.equal(model.matches(graph.nodes,'geminiService.ts')[0].data.type,'directory');
  assert.deepEqual(model.directoryOverview(model.build({...project,claims:[]},[])).nodes.map(n=>n.data.type),['state']);
});

test("authorized commitments and proposed interpretations stay distinct in the project graph",()=>{
  const agreed={id:'meaning',title:'Checkout total',statement:'The accepted meaning',paths:['checkout.py']};
  const proposed={id:'new-meaning',title:'Receipt',statement:'A proposed meaning',paths:['checkout.py']};
  const current={...project,commitments:[agreed]};
  const change=review('one',{changed_paths:['checkout.py'],commitment_baseline:[agreed],commitment_changes:[{before:agreed,after:{...agreed,statement:'Not yet agreed'}},{before:null,after:proposed}],claim_deltas:[{claim_id:'new-meaning',status:'proposed',artifact_anchors:[{path:'checkout.py',relation:'realizes'}]}]});
  const graph=model.build(current,[change]);
  assert.equal(graph.nodes.find(n=>n.data.id==='claim:meaning')?.data.summary,'The accepted meaning');
  assert.equal(graph.nodes.find(n=>n.data.id==='claim:new-meaning')?.data.status,'proposed');
  assert.ok(graph.edges.some(e=>e.data.source==='state'&&e.data.target==='claim:meaning'&&e.data.relation==='governs'));
  assert.ok(!graph.edges.some(e=>e.data.source==='state'&&e.data.target==='claim:new-meaning'));
  assert.ok(graph.edges.some(e=>e.data.source==='artifact:checkout.py'&&e.data.target==='claim:meaning'));
  assert.ok(graph.edges.some(e=>e.data.source==='review:one'&&e.data.target==='claim:new-meaning'));
  const closed=model.build({...project,commitments:[]},[{...change,status:'rejected'}]);
  assert.ok(!closed.nodes.some(n=>n.data.id==='claim:new-meaning'),'Rejected proposals do not appear as active project commitments');
});
