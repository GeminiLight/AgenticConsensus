/* Pure graph model: the browser and the regression tests use the same facts/layout. */
((root) => {
  const short = (value = "") => String(value).slice(0, 8);
  const clip = (value, length = 78) => value.length > length ? `${value.slice(0, length - 1).trimEnd()}…` : value;
  function reviewTone(review) {
    if (review.status === "committed") return "committed";
    if (["rejected", "rolled_back"].includes(review.status)) return "rejected";
    if (review.status === "rebase_required") return "stale";
    const finding=(review.findings || []).some(item=>item.status==='open'&&item.severity==='critical');
    const evidence=(review.evidence || []).some(item=>item.freshness==='stale'||item.outcome==='contests'||(item.kind==='tests'&&['not_run','fail','unknown'].includes(item.status)));
    return finding||evidence ? "attention" : "open";
  }
  function orderedReviews(reviews) {
    const priority = { attention: 0, stale: 1, open: 2, committed: 3, rejected: 3 };
    return [...reviews].sort((a, b) => priority[reviewTone(a)] - priority[reviewTone(b)]
      || (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0)
      || a.id.localeCompare(b.id));
  }
  function build(project, reviews, intents = []) {
    const nodes = [], edges = [], ids = new Set();
    const add = (data) => {
      if (ids.has(data.id)) return;
      ids.add(data.id);
      nodes.push({ data: { ...data, fullLabel: data.label, label: clip(data.label) } });
    };
    const link = (id, source, target, relation) => {
      if (ids.has(id) || !ids.has(source) || !ids.has(target)) return;
      ids.add(id);
      edges.push({ data: { id, source, target, relation, label: relation.replaceAll("_", " ") } });
    };
    add({ id: "state", type: "state", label: `Current state\nVersion ${project.version}`, status: "current", summary: `${project.name} at version ${project.version} · ${short(project.head_ref)}` });
    for (const claim of project.claims || []) {
      add({ id: `claim:${claim.id}`, type: "claim", label: claim.title, status: claim.status, claimId: claim.id, summary: claim.rationale || "" });
      link(`governs:${claim.id}`, "state", `claim:${claim.id}`, "governs");
    }
    for (const commitment of project.commitments || []) {
      add({id:`claim:${commitment.id}`,type:'claim',label:commitment.title,status:'recorded',claimId:commitment.id,summary:commitment.statement});
      link(`governs:${commitment.id}`,'state',`claim:${commitment.id}`,'governs');
    }
    for (const review of orderedReviews(reviews)) {
      const tone = reviewTone(review);
      const summary = review.intent_summary || review.summary || "Untitled change";
      const statusLabel = tone === "attention" ? "Needs attention" : tone === "stale" ? "Needs rebase" : review.status.replaceAll("_", " ");
      add({ id: `review:${review.id}`, type: "review", label: `${statusLabel[0].toUpperCase()}${statusLabel.slice(1)}\n${clip(summary, 64)}`, summary, status: review.status, tone, reviewId: review.id });
      const relation = { open: "proposes", committed: "commits", rolled_back: "rolls_back", rebase_required: "proposes", rejected: "rejected" }[review.status];
      if (relation) link(`${relation}:${review.id}`, `review:${review.id}`, "state", relation);
      for (const path of review.changed_paths || []) {
        add({ id: `artifact:${path}`, type: "artifact", label: path.split("/").slice(-2).join("/"), path, summary: path, status: "changed" });
        link(`changes:${review.id}:${path}`, `review:${review.id}`, `artifact:${path}`, "changes");
      }
      if (review.status === 'open') {
        for (const change of review.commitment_changes || []) {
          const commitment=change.after;
          add({id:`claim:${commitment.id}`,type:'claim',label:commitment.title,status:'proposed',claimId:commitment.id,summary:commitment.statement});
          link(`meaning:${review.id}:${commitment.id}`,`review:${review.id}`,`claim:${commitment.id}`,'proposes');
        }
      }
      for (const commitment of project.commitments || []) {
        for (const path of commitment.paths || []) {
          if ((review.changed_paths || []).includes(path)) link(`commitment-file:${path}:${commitment.id}`,`artifact:${path}`,`claim:${commitment.id}`,'carries');
        }
      }
      for (const delta of review.claim_deltas || []) {
        const relation = { contested: "contests", unobservable: "inconclusive", rejected: "contests", accepted: "supports", proposed: "proposes" }[delta.status] || "observes";
        link(`delta:${review.id}:${delta.claim_id}`, `review:${review.id}`, `claim:${delta.claim_id}`, relation);
        for (const anchor of delta.artifact_anchors || []) {
          link(`anchor:${review.id}:${anchor.path}:${delta.claim_id}`, `artifact:${anchor.path}`, `claim:${delta.claim_id}`, anchor.relation || "observes");
        }
      }
    }
    for (const intent of intents) {
      add({ id: `intent:${intent.id}`, type: "intent", label: `Intent\n${clip(intent.request, 64)}`, summary: intent.request, status: intent.status, intentId: intent.id });
      if (intent.realized_review_id) link(`realizes:${intent.id}`, `intent:${intent.id}`, `review:${intent.realized_review_id}`, "realizes");
    }
    layout(nodes, edges);
    return { nodes, edges };
  }
  function layout(nodes, edges) {
    const byId = new Map(nodes.map((node) => [node.data.id, node]));
    const placed = new Set();
    let cursor = 0;
    for (const review of nodes.filter((node) => node.data.type === "review")) {
      const files = edges.filter((edge) => edge.data.source === review.data.id && ["changes","changes_in"].includes(edge.data.relation))
        .map((edge) => byId.get(edge.data.target)).filter((node) => !placed.has(node.data.id));
      const intents = edges.filter((edge) => edge.data.target === review.data.id && edge.data.relation === "realizes")
        .map((edge) => byId.get(edge.data.source));
      const spacing=files.some(node=>node.data.type==='directory')?96:66;
      const height = Math.max(156 + intents.length * 100, files.length * spacing);
      review.position = { x: 340, y: cursor + height / 2 + intents.length * 40 };
      files.forEach((node, index) => {
        node.position = { x: 680, y: cursor + height / 2 + (index - (files.length - 1) / 2) * spacing };
        placed.add(node.data.id);
      });
      intents.forEach((node, index) => {
        node.position = { x: 340, y: review.position.y - (index + 1) * 114 };
        placed.add(node.data.id);
      });
      cursor += height + 56;
    }
    for (const intent of nodes.filter((node) => node.data.type === "intent" && !placed.has(node.data.id))) {
      intent.position = { x: 340, y: cursor + 50 };
      cursor += 140;
    }
    const claims = nodes.filter((node) => node.data.type === "claim");
    const center = Math.max(90, (cursor - 56) / 2);
    byId.get("state").position = { x: 0, y: center - claims.length * 60 };
    claims.forEach((node, index) => { node.position = { x: 0, y: center - claims.length * 60 + (index + 1) * 126 }; });
  }
  function matches(nodes, query) {
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return nodes.filter(({ data }) => terms.every((term) =>
      `${data.id} ${data.fullLabel} ${data.summary || ""} ${data.path || ""} ${(data.paths || []).join(' ')} ${data.status || ""}`.toLowerCase().includes(term)));
  }
  function neighborhood(ids, edges) {
    const selected = new Set(ids), context = new Set(ids);
    for (const { data } of edges) {
      if (selected.has(data.source)) context.add(data.target);
      if (selected.has(data.target)) context.add(data.source);
    }
    return context;
  }
  function preferredFocus(graph) {
    const nodes = graph.nodes.map(node => node.data);
    return (nodes.find(node => node.type === "review" && ["attention", "stale"].includes(node.tone))
      || nodes.find(node => node.type === "intent" && ["clarification_required", "ready_for_selection", "selected"].includes(node.status))
      || nodes.find(node => node.type === "review" && node.status === "open")
      || nodes.find(node => node.type === "intent")
      || nodes.find(node => node.type === "state"))?.id || null;
  }
  function scoped(graph, ids, { compact = false } = {}) {
    const nodes = graph.nodes.filter(node => ids.has(node.data.id)).map(node => ({...node, position: {...node.position}}));
    const edges = graph.edges.filter(edge => ids.has(edge.data.source) && ids.has(edge.data.target));
    if (compact) {
      const order = {state:0,claim:1,intent:2,review:3,directory:4,artifact:5};
      [...nodes].sort((a,b)=>order[a.data.type]-order[b.data.type]).forEach((node,index)=>{node.position={x:0,y:index*116};});
    } else if (nodes.length) layout(nodes, edges);
    return {nodes,edges};
  }
  function focused(graph, id, options) {
    const selected = graph.nodes.find(node => node.data.id === id);
    if (!selected) return {nodes:[],edges:[]};
    const ids = neighborhood([id], graph.edges);
    if (selected.data.type === "intent") {
      const reviews = graph.nodes.filter(node => node.data.type === "review" && ids.has(node.data.id));
      for (const related of neighborhood(reviews.map(node=>node.data.id),graph.edges)) ids.add(related);
    }
    if (graph.nodes.some(node=>node.data.id==="state")) ids.add("state");
    return scoped(graph,ids,options);
  }
  function directoryOverview(graph) {
    const anchored=new Set(graph.edges.filter(edge=>edge.data.relation!=='changes').flatMap(edge=>[edge.data.source,edge.data.target]));
    const folded=new Map(),groups=new Map();
    for(const node of graph.nodes) {
      if(node.data.type!=='artifact'||anchored.has(node.data.id))continue;
      const path=node.data.path, directory=path.includes('/')?path.slice(0,path.lastIndexOf('/')):'Repository root';
      const id=`directory:${directory}`;
      if(!groups.has(id))groups.set(id,{id,type:'directory',directory,paths:[],status:'changed'});
      groups.get(id).paths.push(path);folded.set(node.data.id,id);
    }
    const nodes=graph.nodes.filter(node=>!folded.has(node.data.id)).map(node=>({...node,position:{...node.position}}));
    for(const data of groups.values()) {
      data.paths.sort();data.label=`${data.directory}\n${data.paths.length} changed files`;data.fullLabel=data.label;data.summary=`${data.paths.length} changed files in ${data.directory}`;
      nodes.push({data});
    }
    const seen=new Set(),edges=[];
    for(const edge of graph.edges) {
      if(!folded.has(edge.data.target)){edges.push(edge);continue;}
      const target=folded.get(edge.data.target), id=`changes-in:${edge.data.source}:${target}`;
      if(seen.has(id))continue;seen.add(id);
      edges.push({data:{id,source:edge.data.source,target,relation:'changes_in',label:'changes in'}});
    }
    layout(nodes,edges);
    return {nodes,edges};
  }
  const model = { build, layout, matches, neighborhood, orderedReviews, reviewTone, preferredFocus, focused, scoped, directoryOverview };
  if (typeof module !== "undefined" && module.exports) module.exports = model;
  else root.CanvasModel = model;
})(globalThis);
