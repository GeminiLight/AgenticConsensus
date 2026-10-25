/* Human-authored project meaning, rendered from persisted review snapshots. */
window.CommitmentUI=(()=>{
  const m=I18n.mark;
  const counts={file:'{count} files','linked file':'{count} linked files','question raised':'{count} question raised','authored reading':'{count} authored readings','linked evidence record':'{count} linked evidence records'};
  const plural=(count,one)=>m(counts[one]||('{count} '+one+(count===1?'':'s')),{count});
  const statuses={missing:'Needs verification',stale:'Verification outdated',contested:'Conflicting evidence',waived:'Exception recorded',satisfied:'Evidence attached',unassessed:'Not assessed'};
  const drafts=new Map();
  const selections=new Map();
  const reviewSelections=new Map();
  const riskDisclosures=new Map();
  const inspections=new Map(),inspectorChoices=new Map();
  let inspectionRequest=null;
  let selectionFrame=null;
  function revealSelection(){
    cancelAnimationFrame(selectionFrame);
    selectionFrame=requestAnimationFrame(()=>{
      const choice=document.querySelector('[data-meaning-select][aria-pressed="true"]');
      const rail=choice?.closest('.meaning-list-group');
      if(!rail||rail.scrollWidth<=rail.clientWidth)return;
      const item=choice.getBoundingClientRect(),bounds=rail.getBoundingClientRect();
      const delta=item.left<bounds.left?item.left-bounds.left-2:item.right>bounds.right?item.right-bounds.right+2:0;
      if(delta)rail.scrollBy({left:delta,behavior:'instant'});
    });
  }
  const resourceKey=review=>`${review.id}:${review.revision}:${review.base_ref}:${review.target_ref}`;
  function locationMeaning(){
    const url=new URL(window.location.href);
    return url.searchParams.get('project')===state.activeProject?.id?url.searchParams.get('meaning'):null;
  }
  function rememberMeaning(key){
    const url=new URL(window.location.href);
    url.searchParams.set('meaning',key);
    window.history.replaceState(window.history.state,'',url);
  }
  function projectMeaning(project){return locationMeaning()||selections.get(project.id);}
  function currentMeaning(){return state.activeProject?CommitmentModel.workspace(state.activeProject,state.reviews,projectMeaning(state.activeProject)).selected:null;}
  function resourceFor(item){const review=state.reviews.find(r=>r.id===item.reviewId);return review?inspections.get(resourceKey(review)):null;}
  function inspectorChoice(item){
    if(!inspectorChoices.has(item.key)){
      const readings=(item.source_readings||[]).filter(note=>note.version_ref===item.targetRef&&item.after.paths.includes(note.path));
      const index=Math.max(0,readings.findIndex(note=>note.relation==='tension'));
      inspectorChoices.set(item.key,{tab:'source',view:'canvas',path:readings[index]?.path||item.after.paths[0],reading:readings.length?index:null,
        open:matchMedia('(min-width:1360px)').matches,scope:'linked',fileQuery:'',closedFolders:new Set(),positions:new Map()});
    }
    return inspectorChoices.get(item.key);
  }
  function rememberReading(){
    const pane=$('.meaning-code'),item=currentMeaning();if(!pane?.checkVisibility()||!item)return;
    const choice=inspectorChoice(item),path=$('#meaning-source-path')?.textContent;
    if(path)choice.positions.set(path,{query:$('#meaning-source-search')?.value||'',top:pane.scrollTop,left:pane.scrollLeft});
  }
  function textBlock(value){return value.length>260?`<details class="commitment-long"><summary>${esc(value.slice(0,210))}…</summary><p>${esc(value)}</p></details>`:`<p>${esc(value)}</p>`;}
  function historyView(item){
    const origin=state.reviews.find(review=>review.id===item.originReviewId);
    const change=origin?.commitment_changes?.find(change=>change.after.id===item.after.id);
    const record=change||item;
    const decision=origin?.decision_records?.filter(record=>record.action==='commit').at(-1);
    return `<section class="meaning-history"><p class="eyebrow">${m(origin?'Recorded agreement':'Proposed interpretation')}</p><h4>${m('Why this commitment')}</h4><dl><div><dt>${m('Original request')}</dt><dd>${esc(record.request||I18n.t('The original request is not linked in the available records.'))}</dd></div><div><dt>${m('Author’s reasoning')}</dt><dd>${esc(record.reason||I18n.t('No rationale linked to the available record.'))}</dd></div>${decision?`<div><dt>${m('Decision rationale')}</dt><dd>${esc(decision.reason||'—')}</dd></div>`:''}</dl><div class="meaning-history-meta">${m('Recorded by {actor}',{actor:record.recorded_by||'—'})}${decision?m('Agreed by {actor}',{actor:decision.actor}):m('Human agreement is still required.')}${origin?`<code>${m('Version {ref}',{ref:origin.target_ref.slice(0,8)})}</code>`:''}</div>${origin?`<p class="meaning-history-boundary">${m('This explains the agreement, not whether the current code still satisfies it.')}</p><button class="button" type="button" data-meaning-inspect="${esc(origin.id)}" data-meaning-commitment="${esc(item.after.id)}">${m('Open original review')} ${uiIcon('arrow-right')}</button>`:''}</section>`;
  }
  function continuityView(item){
    const current=item.kind==='agreed',origin=item.originTarget;
    return `<div class="meaning-continuity" role="group" aria-label="${I18n.t('Agreement and implementation versions')}" data-i18n-aria-label=Agreement%20and%20implementation%20versions><div class="meaning-origin"><span>${uiIcon('history')} ${m(origin?'Recorded agreement':'Request & interpretation')}</span><strong>${origin?esc(origin.slice(0,8)):m('No prior agreement')}</strong></div><span class="meaning-version-connector" aria-hidden="true"></span><div class="meaning-current" data-assessed="${Boolean(item.reviewId)}"><span>${m(current?'Current version':'Proposed target')}</span><strong>${esc(item.targetRef?.slice(0,8)||'—')}</strong><small>${m(current&&!item.reviewId?'No assessment for this version':current?'Evidence is version-bound':'Not yet admitted')}</small></div></div>`;
  }
  function nextStepView(item){
    const resource=resourceFor(item),step=CommitmentModel.nextStep(item,resource?.review,resource?.manifest,resource?.load||'loading');
    const messages={question:['Resolve the source question','An authored reading needs your attention. It is not an automated finding.','Inspect source'],
      missing:['Check this version','This commitment needs evidence for the selected version.','Inspect verification'],
      unassessed:['No assessment for this version','An earlier agreement does not establish current behavior.',item.reviewId?'Inspect verification':'Compare revisions'],
      stale:['Refresh the evidence','Earlier evidence does not cover this version.','Inspect verification'],
      contested:['Resolve conflicting evidence','Inspect the conflicting result before recording new evidence.','Inspect verification'],
      waived:['Review the recorded exception','An exception is not verification. Check its scope before deciding.','Open review'],
      satisfied:[item.kind==='agreed'?'Inspect current evidence':'Review the decision','Linked evidence is available. Approval remains a separate decision.','Open review'],
      recorded:['Approval recorded','This version has an attributed approval. Inspect its evidence or start a new change.','Inspect recorded decision'],
      loading:['Reading evidence…','Checking records for this exact version.','Loading…'],
      error:['Inspection unavailable','Reload the evidence before relying on this state.','Try again']};
    messages.rebase=['Review the changed baseline','The project has advanced. Compare versions before continuing.','Open review'];
    const [title,detail,label]=messages[step.status]||messages.unassessed;
    return `<div class="meaning-next-step" data-state="${esc(step.status)}"><span class="meaning-next-symbol">${uiIcon(step.status==='satisfied'?'shield-check':step.status==='question'?'git-rebase':'search')}</span><div><strong>${m(title)}</strong><p>${m(detail)}</p></div><button type="button" class="button button-primary" data-meaning-next="${esc(step.action)}"${step.action==='loading'?' disabled':''}>${m(label)} ${uiIcon('arrow-right')}</button></div>`;
  }
  function footprint(item){
    const resource=resourceFor(item),data=CommitmentModel.inspection(item,resource?.review,resource?.manifest,resource?.files);
    const max=Math.max(1,...data.files.map(file=>(file.changes?.additions||0)+(file.changes?.deletions||0)));
    return data.files.map(file=>{
      const c=file.changes,selected=inspectorChoice(item).tab==='source'&&inspectorChoice(item).path===file.path;
      return `<button type="button" class="meaning-file-node" data-meaning-file="${esc(file.path)}" aria-pressed="${selected}"${item.reviewId?'':' disabled'}><span class="meaning-file-glyph">${uiIcon('file-text')}</span><span class="meaning-file-name"><strong>${esc(file.path.split('/').at(-1))}</strong><small>${esc(file.path.includes('/')?file.path.slice(0,file.path.lastIndexOf('/')):'Repository root')}</small></span>${c?`<span class="meaning-file-change"><span><b>+${c.additions}</b><em>−${c.deletions}</em>${c.partial?'<small data-i18n=partial>partial</small>':''}</span><span class="meaning-footprint-meter" role="img" aria-label="${c.additions} lines added, ${c.deletions} removed${c.partial?', incomplete patch':''}"><i style="width:${100*c.additions/max}%"></i><i style="width:${100*c.deletions/max}%"></i></span></span>`:`<span class="meaning-file-unknown">${resource?.load==='ready'?'No patch':'—'}</span>`}${uiIcon('chevron-right')}</button>`;
    }).join('');
  }
  function inspectionContent(item,tab='source'){
    const resource=resourceFor(item),choice={...inspectorChoice(item),tab},data=CommitmentModel.inspection(item,resource?.review,resource?.manifest,resource?.files);
    let body='';
    if(choice.tab==='history')body=historyView(item);
    else if(!item.reviewId)body=`<div class="meaning-inspector-notice">${m('No assessment for this version')}<p>${m('An earlier agreement does not establish current behavior.')}</p><button class="button" type="button" data-meaning-next="new-review">${m('Compare revisions')}</button></div>`;
    else if(!resource||resource.load==='loading')body='<div class="meaning-inspector-notice" role="status"><span class="button-spinner" aria-hidden="true"></span> <span data-i18n=Reading%20the%20review%20snapshot%E2%80%A6>Reading the review snapshot…</span></div>';
    else if(resource.load==='error')body=`<div class="meaning-inspector-notice" role="alert"><strong data-i18n=Couldn%E2%80%99t%20load%20inspection>Couldn’t load inspection</strong><p>${esc(resource.error)}</p><button class="button" type="button" data-meaning-retry data-i18n=Try%20again>Try again</button></div>`;
    else if(choice.tab==='source'){
      const reading=selectedReading(item);
      const file=resource.files.find(f=>f.path===choice.path);
      const rows=file?.rows||[],visible=rows.slice(0,1800);
      body=`${reading?`<details class="reading-inspection-context"><summary>${m(reading.relation==='tension'?'Author-raised question':'Authored source reading')} · L${reading.start_line}–${reading.end_line}</summary><p>${esc(reading.summary)}</p><details><summary data-i18n=Captured%20excerpt>Captured excerpt</summary><pre>${esc(reading.excerpt)}</pre></details></details>`:''}<div class="meaning-source-head"><span id="meaning-source-path">${esc(choice.path)}</span><small>${m('Target {ref} · read-only patch',{ref:resource.review.target_ref.slice(0,8)})}</small></div><label class="meaning-source-find">${uiIcon('search')}<input id="meaning-source-search" type="search" placeholder="Find in this patch…" aria-label="Find in this patch" autocomplete="off" data-i18n-placeholder=Find%20in%20this%20patch%E2%80%A6 data-i18n-aria-label=Find%20in%20this%20patch><span id="meaning-source-matches" role="status"></span></label>${resource.truncated||file?.partial||rows.length>visible.length?'<p class="meaning-source-limit" data-i18n=Partial%20patch%20%C2%B7%20search%20covers%20displayed%20lines%20only.>Partial patch · search covers displayed lines only.</p>':''}<div class="meaning-code" tabindex="0" role="region" aria-label="Selected file patch" data-i18n-aria-label=Selected%20file%20patch>${!file?'<p class="meaning-inspector-notice" data-i18n=No%20patch%20is%20available%20for%20this%20file%20in%20this%20review.>No patch is available for this file in this review.</p>':file.binary?'<p class="meaning-inspector-notice" data-i18n=Binary%20file%20%C2%B7%20text%20cannot%20be%20displayed.>Binary file · text cannot be displayed.</p>':visible.map(row=>`<div class="meaning-code-line${reading&&row.newLine>=reading.start_line&&row.newLine<=reading.end_line?' source-anchor':''}" data-source-line="${row.newLine??''}" data-kind="${esc(row.kind)}"><span aria-hidden="true">${row.newLine??row.oldLine??''}</span><span aria-hidden="true">${row.kind==='add'?'+':row.kind==='del'?'−':''}</span><code>${highlightCode(row.text,codeLanguage(choice.path))}</code></div>`).join('')}</div><div class="meaning-inspector-bottom"><button type="button" class="text-button" data-meaning-full-diff="${esc(choice.path)}" data-meaning-review="${esc(item.reviewId)}">${I18n.mark("Open full review diff")} ${uiIcon('arrow-right')}</button></div>`;
    }else{
      body=`<div class="meaning-verification"><div class="meaning-evidence-state" data-status="${esc(data.status)}"><span class="meaning-evidence-symbol">${uiIcon(data.status==='satisfied'?'shield-check':'search')}</span><div><strong>${m(statuses[data.status]||data.status)}</strong><p>${plural(data.evidence.length,'linked evidence record')}</p></div></div><div class="meaning-checks"><h4><span data-i18n=Verification%20plan>Verification plan</span> <span data-i18n=Not%20a%20test%20result>Not a test result</span></h4><ol>${item.after.verification.split(/\n+/).filter(Boolean).map((line,index)=>`<li><span>${String(index+1).padStart(2,'0')}</span><p>${esc(line)}</p></li>`).join('')}</ol></div><div class="meaning-records"><h4 data-i18n=Attached%20evidence>Attached evidence</h4>${data.evidence.length?data.evidence.map(record=>`<article class="meaning-evidence-record"><span>${esc(sentence(record.kind))} · ${esc(record.status)}</span><p>${esc(record.summary||record.id)}</p></article>`).join(''):'<p data-i18n=No%20evidence%20is%20linked%20to%20this%20commitment.%20Code%20changes%20alone%20do%20not%20verify%20the%20behavior.>No evidence is linked to this commitment. Code changes alone do not verify the behavior.</p>'}</div>${resource.manifest.blockers?.length?`<details class="meaning-gate"><summary>${m('{count} review-level approval blockers',{count:resource.manifest.blockers.length})}</summary><ul>${resource.manifest.blockers.map(line=>`<li>${esc(line)}</li>`).join('')}</ul></details>`:''}<div class="meaning-inspector-bottom"><button type="button" class="button" data-meaning-verify="${esc(item.reviewId)}" data-meaning-obligation="${esc(data.obligation?.obligation_id||item.obligation_id||'')}">${I18n.mark("Open verification")} ${uiIcon('arrow-right')}</button></div></div>`;
    }
    return body;
  }
  function fileTreeView(item){
    const choice=inspectorChoice(item),resource=resourceFor(item),snapshot=choice.scope==='project';
    const files=snapshot?(state.projectTree?.entries||[]).filter(entry=>entry.kind==='file').map(entry=>entry.path):choice.scope==='linked'?item.after.paths:
      [...new Set([...item.after.paths,...(resource?.review?.changed_paths||[])])];
    const query=choice.fileQuery.toLocaleLowerCase(),paths=files.filter(path=>path.toLocaleLowerCase().includes(query));
    const render=nodes=>nodes.map(node=>node.kind==='directory'?`<details class="meaning-tree-folder" data-meaning-folder="${esc(node.path)}"${query||!choice.closedFolders.has(node.path)?' open':''}><summary><span class="file-tree-chevron" aria-hidden="true">›</span><span class="file-tree-folder" aria-hidden="true"></span><span>${esc(node.name)}</span></summary><div>${render(node.children)}</div></details>`:
      `<button type="button" class="meaning-tree-file" data-meaning-tree-file="${esc(node.path)}" title="${esc(node.path)}" aria-pressed="${!snapshot&&choice.path===node.path}">${uiIcon('file-text')}<span>${esc(node.name)}</span>${!snapshot&&item.after.paths.includes(node.path)?`<i title="${I18n.t('Linked to this commitment')}" aria-label="${I18n.t('Linked to this commitment')}"></i>`:''}</button>`).join('');
    let content=render(buildProjectTree(paths.map(path=>({kind:'file',path}))));
    if(snapshot&&state.projectTreeLoading)content=`<p class="meaning-tree-notice" role="status">${m('Loading…')}</p>`;
    else if(snapshot&&state.projectTree?.error)content=`<p class="meaning-tree-notice" role="alert">${m('Project snapshot unavailable')}</p><button class="text-button" type="button" data-meaning-tree-retry>${m('Try again')}</button>`;
    else if(!paths.length)content=`<p class="meaning-tree-notice">${m(query?'No matching files':'No files available')}</p>`;
    const ref=snapshot?state.projectTree?.revision:item.targetRef;
    return `<section class="meaning-file-browser"><div class="meaning-files-heading"><label class="sr-only" for="meaning-file-scope">${m('File version')}</label><select id="meaning-file-scope"><option value="linked" data-i18n=Linked%20files${choice.scope==='linked'?' selected':''}>${I18n.t('Linked files')}</option><option value="review" data-i18n=Review%20files${choice.scope==='review'?' selected':''}>${I18n.t('Review files')}</option><option value="project" data-i18n=Project%20snapshot${snapshot?' selected':''}>${I18n.t('Project snapshot')}</option></select><code>${esc(ref?.slice(0,8)||'—')}</code></div><label class="meaning-tree-search">${uiIcon('search')}<input id="meaning-file-search" type="search" value="${esc(choice.fileQuery)}" placeholder="${I18n.t('Find files…')}" aria-label="${I18n.t('Find files…')}" data-i18n-placeholder=Find%20files%E2%80%A6 data-i18n-aria-label=Find%20files%E2%80%A6></label><div class="meaning-file-tree" aria-label="${I18n.t('Files')}" data-i18n-aria-label=Files>${content}</div><p class="meaning-tree-boundary">${m(snapshot?'Project baseline · opens in a separate reader':'Proposed changes · linked files marked with a dot')}${snapshot&&state.projectTree?.truncated?` · ${m('Partial file list')}`:''}</p></section>`;
  }
  function inspectorView(item){
    const resource=resourceFor(item),choice=inspectorChoice(item);
    const context=`<div class="meaning-inspector-context"><strong title="${esc(item.after.title)}">${esc(item.after.title)}</strong><button type="button" data-inspector-expand aria-pressed="${Boolean(choice.expanded)}" aria-controls="meaning-inspector-content">${uiIcon('panel-right')}<span data-reading-focus-label>${m(choice.expanded?'Back to comparison':'Focus reading')}</span></button><button type="button" class="meaning-close" data-inspector-close aria-label="Close inspection" data-i18n-aria-label=Close%20inspection>${uiIcon('x-circle')}</button></div>`;
    return `<aside id="meaning-inspector" class="meaning-inspector" data-load="${resource?.load||(!item.reviewId?'ready':'loading')}" aria-label="Inspect the selected commitment" data-i18n-aria-label=Inspect%20the%20selected%20commitment>${context}${fileTreeView(item)}<div class="meaning-source-toolbar"><span>${uiIcon('code')} ${m('Source')}</span><button type="button" class="meaning-refresh" data-meaning-retry aria-label="Refresh source and evidence"${item.reviewId?'':' disabled'} data-i18n-aria-label=Refresh%20source%20and%20evidence>${uiIcon('refresh')}</button></div><div id="meaning-inspector-content" role="region" aria-label="${I18n.t('Source')}" data-i18n-aria-label=Source tabindex="0">${inspectionContent(item)}</div></aside>`;
  }

  function alignmentData(item){const resource=resourceFor(item),review=resource?.review||state.reviews.find(r=>r.id===item.reviewId)||{};return CommitmentModel.alignment(item,review,resource?.manifest);}
  function selectedReading(item){const choice=inspectorChoice(item);return choice.reading==null?null:alignmentData(item).readings[choice.reading];}
  function focusView(item,project,index,total){
    const review=state.reviews.find(review=>review.id===item.reviewId),data=alignmentData(item),proposed=item.kind==='proposal',choice=inspectorChoice(item);
    const labels={supports:'Consistent reading',tension:'Question to resolve',context:'Context'};
    const readings=data.readings.map((note,i)=>`<button type="button" class="alignment-reading" data-source-reading="${i}" data-relation="${esc(note.relation)}" aria-controls="meaning-inspector" aria-pressed="${Boolean(choice.open&&choice.tab==='source'&&choice.reading===i)}"><span class="reading-card-top"><span class="reading-symbol">${uiIcon(note.relation==='tension'?'git-rebase':'file-text')}</span><span class="reading-relation"><i></i>${m(labels[note.relation])}</span></span><strong>${esc(note.label)}</strong><p>${esc(note.summary)}</p><span class="reading-card-source"><code>${esc(note.path.split('/').at(-1))}</code><span>L${note.start_line}–${note.end_line}</span>${uiIcon('arrow-right')}</span></button>`).join('');
    const unread=data.unreadPaths.map(path=>`<button type="button" class="alignment-reading" data-meaning-file="${esc(path)}" data-relation="unread"${item.reviewId?'':' disabled'}><span class="reading-card-top"><span class="reading-symbol">${uiIcon('file-text')}</span><span class="reading-relation" data-i18n=Not%20interpreted>Not interpreted</span></span><strong>${esc(path.split('/').at(-1))}</strong><p data-i18n=This%20file%20is%20linked%2C%20but%20no%20source%20reading%20has%20been%20recorded.>This file is linked, but no source reading has been recorded.</p><span class="reading-card-source"><code>${esc(path)}</code>${uiIcon('arrow-right')}</span></button>`).join('');
    const count=data.readings.length+data.unreadPaths.length;
    const paths=Array.from({length:Math.min(count,3)},(_,i)=>{const x=(i+.5)*900/Math.min(count,3);return `<path d="M450 0V22 Q450 32 ${x===450?450:x<450?440:460} 32 H${x} V64" data-relation="${data.readings[i]?.relation||'context'}"/><circle cx="${x}" cy="64" r="3" data-relation="${data.readings[i]?.relation||'context'}"/>`;}).join('');
    return `<article id="meaning-focus" class="meaning-focus alignment-focus" data-meaning-key="${esc(item.key)}" data-inspector-open="${Boolean(choice.open)}" data-inspector-expanded="${Boolean(choice.open&&choice.expanded)}" aria-label="${esc(item.after.title)}"><div class="meaning-focus-main">
      <header class="alignment-heading"><div><div class="alignment-eyebrow"><span>${esc(project.name)}</span><span>${m('Commitment {index} / {total}',{index:String(index+1).padStart(2,'0'),total:String(total).padStart(2,'0')})}</span></div><h3 id="meaning-title">${esc(item.after.title)}</h3><div class="meaning-heading-detail"><span>${data.questions?plural(data.questions,'question raised'):m('Read the implementation and its evidence')}</span><button type="button" class="text-button" data-meaning-history>${m('Original request')} ${uiIcon('arrow-right')}</button></div></div><span class="alignment-authority" data-kind="${item.kind}"><i></i>${m(proposed?'Proposed':item.kind==='recheck'?'Recheck':'Agreed')}</span></header>
      <div class="meaning-workbar"><div class="meaning-view-tabs" role="tablist" aria-label="${I18n.t('Workspace views')}" data-i18n-aria-label=Workspace%20views>${[['canvas','network','Relationship canvas','Canvas'],['changes','file-text','Changes','Changes'],['evidence','shield-check','Verification','Evidence'],['history','history','History','History']].map(([tab,icon,label,compact])=>`<button type="button" id="meaning-view-${tab}" role="tab" aria-selected="${choice.view===tab}" aria-controls="meaning-pane-${tab}" tabindex="${choice.view===tab?'0':'-1'}" data-meaning-view="${tab}">${uiIcon(icon)}<span class="meaning-view-full">${m(label)}</span><span class="meaning-view-short">${m(compact)}</span></button>`).join('')}</div><button type="button" class="meaning-files-toggle" data-meaning-files-toggle aria-expanded="${Boolean(choice.open)}" aria-controls="meaning-inspector">${uiIcon('panel-right')}${m('Files')}</button></div>
      <div class="meaning-workspace-content">
      <div id="meaning-pane-canvas" class="meaning-view-pane" role="tabpanel" aria-labelledby="meaning-view-canvas" tabindex="0"${choice.view==='canvas'?'':' hidden'}>
      <section class="alignment-canvas" aria-label="Source-to-meaning correspondence" data-i18n-aria-label=Source-to-meaning%20correspondence><div class="alignment-canvas-caption"><span>${uiIcon('network')} ${I18n.mark("Meaning across the implementation")}</span><span>${review?esc(review.target_ref.slice(0,8)):'Recorded snapshot'}</span></div>
        <div class="alignment-contract"><div class="alignment-contract-mark" aria-hidden="true">C<span>${index+1}</span></div><div><span class="alignment-contract-label">${m(proposed?'What we propose to agree':item.kind==='recheck'?'Must remain true':'What is currently agreed')}</span><p>${esc(item.after.statement)}</p></div><span class="alignment-contract-tag">${item.kind==='recheck'?m('Baseline'):proposed?m('Draft'):'v'+project.version}</span></div>
        <svg class="alignment-connectors" viewBox="0 0 900 68" preserveAspectRatio="none" aria-hidden="true">${paths}<path class="alignment-stem" d="M450 0V68"/></svg>
        <div class="alignment-readings" style="--reading-columns:${Math.min(count,3)}">${readings}${unread}</div>
        <div class="alignment-map-legend"><span><i data-relation="tension"></i> <span data-i18n=Author-raised%20question>Author-raised question</span></span><span><i></i> <span data-i18n=Source%20reading%20%C2%B7%20not%20verification>Source reading · not verification</span></span><button type="button" class="text-button" data-alignment-reason>${I18n.mark("Read rationale")} ${uiIcon('arrow-right')}</button></div>
      </section>
      </div>
      <section id="meaning-pane-changes" class="meaning-view-pane meaning-changes-pane" role="tabpanel" aria-labelledby="meaning-view-changes" tabindex="0"${choice.view==='changes'?'':' hidden'}><h4>${m('Files linked to this commitment')}</h4><p>${m('Select a file to read its proposed changes.')}</p><div class="meaning-file-stack">${footprint(item)}</div></section>
      <section id="meaning-pane-evidence" class="meaning-view-pane" role="tabpanel" aria-labelledby="meaning-view-evidence" tabindex="0"${choice.view==='evidence'?'':' hidden'}>${inspectionContent(item,'evidence')}</section>
      <section id="meaning-pane-history" class="meaning-view-pane" role="tabpanel" aria-labelledby="meaning-view-history" tabindex="0"${choice.view==='history'?'':' hidden'}>${continuityView(item)}${historyView(item)}${item.before?`<section class="meaning-previous-agreement"><h4>${m('Previously agreed')}</h4><p>${esc(item.before.statement)}</p></section>`:''}</section>
      </div>
      <div class="meaning-review-actions"><span>${m(proposed?'Human agreement is still required.':item.kind==='recheck'?'The meaning is unchanged. Its implementation still needs review.':'Authorized state · evidence remains inspectable.')}</span>${item.kind!=='agreed'&&item.reviewId?`<button type="button" class="text-button" data-meaning-edit="${esc(item.reviewId)}" data-meaning-commitment="${esc(item.after.id)}">${m(proposed?'Revise interpretation':'Propose revision')}</button>`:''}${item.reviewId?`<button type="button" class="text-button" data-meaning-inspect="${esc(item.reviewId)}" data-meaning-commitment="${esc(item.after.id)}">${m('Open review')} ${uiIcon('arrow-right')}</button>`:''}</div>
      <footer class="meaning-focus-footer" id="meaning-next-step">${nextStepView(item)}</footer>
      </div>${inspectorView(item)}</article>`;
  }
  function meaningWorkspace(project,reviews){
    const data=CommitmentModel.workspace(project,reviews,projectMeaning(project));
    if(!data.selected)return '';
    selections.set(project.id,data.selected.key);
    const list=(items,label)=>`<div class="meaning-list-group"><h3>${m(label)}<span>${items.length}</span></h3>${items.map(item=>`<button type="button" class="meaning-choice" data-meaning-select="${esc(item.key)}" aria-pressed="${item.key===data.selected.key}" aria-controls="meaning-focus"><span class="meaning-choice-number">${String(data.cards.indexOf(item)+1).padStart(2,'0')}</span><span><strong>${esc(item.after.title)}</strong><small>${m(sentence(item.after.category))}<i>·</i>${plural(item.after.paths.length,'file')}</small></span>${uiIcon('chevron-right')}</button>`).join('')}</div>`;
    queueMicrotask(()=>{loadInspection();revealSelection();});
    const proposals=data.pending.filter(item=>item.kind==='proposal'),rechecks=data.pending.filter(item=>item.kind==='recheck');
    return `<section class="meaning-workspace" aria-label="Project meaning workspace" data-i18n-aria-label=Project%20meaning%20workspace><div class="meaning-workspace-body"><aside class="meaning-index" aria-label="Select a commitment" data-i18n-aria-label=Select%20a%20commitment><div class="meaning-index-heading">${uiIcon('git-rebase')}<span data-i18n=Commitments>Commitments</span><button type="button" data-state-start aria-label="Describe a commitment" data-i18n-aria-label=Describe%20a%20commitment>${uiIcon('plus')}</button></div>
      ${proposals.length?list(proposals,'Awaiting agreement'):''}${rechecks.length?list(rechecks,'Recheck existing commitments'):''}${data.authorized.length?list(data.authorized,'Agreed state'):''}
      ${data.unframed.length?`<section class="meaning-unframed" aria-labelledby="unframed-heading"><h3 id="unframed-heading">${m('Unmapped changes')}<span>${data.unframed.length}</span></h3><p>${m('No commitment is linked yet.')}</p><div>${data.unframed.map(review=>`<button type="button" data-commitment-review="${esc(review.id)}"><span>${uiIcon('git-rebase')}<strong>${esc(review.intent_summary||review.summary||I18n.t('Untitled change'))}</strong>${uiIcon('arrow-right')}</span><small>${plural((review.changed_paths||[]).length,'file')}</small></button>`).join('')}</div></section>`:''}
      <div class="meaning-index-footer"><span><i></i>${m('{count} agreed · version {version}',{count:data.authorized.length,version:project.version})}</span><p data-i18n=Only%20an%20authorized%20decision%20changes%20the%20shared%20state.>Only an authorized decision changes the shared state.</p></div></aside>${focusView(data.selected,project,data.cards.indexOf(data.selected),data.cards.length)}</div></section>`;
  }
  function refreshInspection(){
    const item=currentMeaning();if(!item||!$('#meaning-inspector'))return;
    const active=document.activeElement;
    const restore=active?.hasAttribute('data-meaning-retry')?'.meaning-refresh':active?.hasAttribute('data-meaning-file')?`[data-meaning-file="${CSS.escape(active.dataset.meaningFile)}"]`:active?.id&&active.closest('#meaning-inspector')?`#${CSS.escape(active.id)}`:null;
    $('#meaning-inspector').outerHTML=inspectorView(item);$('.meaning-file-stack').innerHTML=footprint(item);
    $('#meaning-focus').dataset.inspectorOpen=String(Boolean(inspectorChoice(item).open));
    $('#meaning-focus').dataset.inspectorExpanded=String(Boolean(inspectorChoice(item).open&&inspectorChoice(item).expanded));
    $('#meaning-pane-evidence').innerHTML=inspectionContent(item,'evidence');
    $('#meaning-next-step').innerHTML=nextStepView(item);
    $('[data-meaning-files-toggle]').setAttribute('aria-expanded',String(Boolean(inspectorChoice(item).open)));
    const choice=inspectorChoice(item);document.querySelectorAll('[data-source-reading]').forEach(card=>card.setAttribute('aria-pressed',String(Boolean(choice.open&&choice.tab==='source'&&choice.reading===Number(card.dataset.sourceReading)))));
    const saved=choice.positions.get(choice.path),search=$('#meaning-source-search');
    if(saved&&search){search.value=saved.query;search.dispatchEvent(new Event('input',{bubbles:true}));}
    requestAnimationFrame(()=>{const line=$('.meaning-code-line.source-anchor'),pane=$('.meaning-code');if(!pane)return;if(saved){pane.scrollTop=saved.top;pane.scrollLeft=saved.left;}else if(selectedReading(item)&&line){const rect=line.getBoundingClientRect(),bounds=pane.getBoundingClientRect();pane.scrollTop+=rect.top-bounds.top-50;}});
    if(restore)document.querySelector(restore)?.focus({preventScroll:true});
  }
  function setMeaningView(view){
    const item=currentMeaning();if(!item)return;
    inspectorChoice(item).view=view;
    document.querySelectorAll('[data-meaning-view]').forEach(button=>{const selected=button.dataset.meaningView===view;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;});
    document.querySelectorAll('.meaning-view-pane').forEach(pane=>pane.hidden=pane.id!==`meaning-pane-${view}`);
    const tab=document.querySelector(`[data-meaning-view="${view}"]`);tab?.focus({preventScroll:true});
    $('.meaning-workspace-content').scrollTop=0;
  }
  async function loadInspection(force=false){
    const item=currentMeaning(),review=state.reviews.find(r=>r.id===item?.reviewId);if(!item||!review||!$('#meaning-inspector'))return;
    const key=resourceKey(review);if(!force&&inspections.has(key)&&(inspections.get(key).load!=='loading'||inspectionRequest?.key===key))return refreshInspection();
    inspectionRequest?.controller.abort();
    const context={key,controller:new AbortController(),owner:state.auth?.user?.id,session:state.csrfToken,projectId:state.activeProject.id};inspectionRequest=context;
    const current=()=>inspectionRequest===context&&state.activeProject?.id===context.projectId&&state.auth?.user?.id===context.owner&&state.csrfToken===context.session;
    inspections.set(key,{load:'loading'});refreshInspection();
    try{
      const options={signal:context.controller.signal};
      const [fresh,manifest,patch]=await Promise.all([api(`/api/reviews/${review.id}`,options),api(`/api/reviews/${review.id}/package`,options),api(`/api/reviews/${review.id}/diff`,options)]);
      const after=await api(`/api/reviews/${review.id}`,options);
      if(!current())return;
      if(resourceKey(fresh)!==key||resourceKey(after)!==key||manifest.package_id!==review.id||patch.review_id!==review.id)throw new Error('The review changed. Reload the project before inspecting this version.');
      const files=DiffModel.parse(patch.diff||'');if(patch.truncated&&files.length)files.at(-1).partial=true;
      inspections.set(key,{load:'ready',review:fresh,manifest,files,truncated:patch.truncated});
    }catch(error){if(!current())return;inspections.set(key,{load:'error',error:error.message});}
    finally{if(current()){inspectionRequest=null;refreshInspection();}}
  }
  function projectView(project,reviews){
    const data=CommitmentModel.projectState(project,reviews);
    const unframed=CanvasModel.orderedReviews(data.unframed);
    if(state.projectLoadError||state.reviewsLoading)return `<div class="state-loading" role="status">${state.projectLoadError?'Project state unavailable. Retry the project to continue.':'Reading the project state…'}</div>`;
    if(data.pending.length||data.authorized.length)return meaningWorkspace(project,reviews);
    return `<div class="state-overview-grid">
      <section class="state-pending"><header><div><p class="eyebrow">${m('Review queue')}</p><h3>${m(unframed.length?'Choose a change to review':'Start with a code change')}</h3><p>${m('Understand the change, check the evidence, then decide.')}</p></div><span class="count">${unframed.length}</span></header>
        ${unframed.length?unframed.map(review=>`<button type="button" class="state-proposal" data-commitment-review="${esc(review.id)}"><span class="state-proposal-meta"><span>${plural((review.changed_paths||[]).length,'changed file')}</span><span class="status-pill status-${esc(review.status)}" data-tone="${esc(canvasReviewTone(review))}">${m(canvasReviewTone(review)==='attention'?'Needs attention':canvasReviewTone(review)==='stale'?reviewStatusLabel(review.status):'Open')}</span></span><strong>${esc(review.intent_summary||review.summary||I18n.t('Untitled change'))}</strong><small>${m('Open decision brief')} ${uiIcon('arrow-right')}</small></button>`).join(''):`<div class="state-empty"><p>${m('Choose a pull request or compare revisions to see what needs attention.')}</p>${!document.body.classList.contains('viewer-mode')?`<button type="button" class="button" data-state-start>${m('Start a change')} ${uiIcon('arrow-right')}</button>`:''}</div>`}
      </section>
      <section class="state-agreements"><header><div><p class="eyebrow">${m('Project agreement')}</p><h3>${m('What should stay true')}</h3></div></header>
        <div class="state-empty"><span class="state-empty-symbol" aria-hidden="true">${uiIcon('shield-check')}</span><h4>${m('No agreed commitments yet')}</h4><p>${m('A commitment records the behavior or boundary this project must preserve. Draft one from a review, then verify it before approval.')}</p></div>
        ${(project.claims||[]).length?`<div class="state-existing-rules"><span>${m('{count} configured rules',{count:project.claims.length})}</span><button type="button" class="text-button" data-open-project-view="governance">${m('Inspect rules')} ${uiIcon('arrow-right')}</button></div>`:''}
      </section>
    </div>`;
  }
  function reviewView(review,manifest){
    const rows=CommitmentModel.reviewRows(review,manifest),editable=review.status==='open'&&!document.body.classList.contains('viewer-mode');
    // The decision brief already offers the first-draft action. Keep this panel
    // for actual commitments instead of repeating an empty three-step tutorial.
    if (!rows.length) return '';
    const key=locationMeaning(),prefix=key?.slice(0,key.indexOf(':'));
    const linkedId=prefix===review.id||prefix==='agreed'?key.slice(key.indexOf(':')+1):null;
    const selected=rows.find(row=>row.id===linkedId)||rows.find(row=>row.id===reviewSelections.get(review.id))||rows[0];
    if(selected)reviewSelections.set(review.id,selected.id);
    return `<section class="commitment-workbench module" id="review-commitments" aria-labelledby="commitment-workbench-title"><header class="commitment-workbench-head"><div><p class="eyebrow" data-i18n=Meaning%20of%20this%20change>Meaning of this change</p><h3 id="commitment-workbench-title">${m(rows.length?'Project commitments':'What should this change mean?')}</h3></div>${editable?'<button type="button" class="button button-with-icon" data-propose-commitment="">'+uiIcon('plus')+'<span data-i18n=Describe%20commitment>Describe commitment</span></button>':''}</header>
      ${rows.length>1?`<nav class="commitment-switcher" aria-label="Select a project commitment">${rows.map((row,index)=>`<button type="button" data-review-meaning="${esc(row.id)}" aria-pressed="${row.id===selected.id}"><span>${String(index+1).padStart(2,'0')}</span>${esc(row.after.title)}<i data-status="${esc(row.status)}"></i></button>`).join('')}</nav>`:''}
      ${rows.length?[selected].map(row=>`<article class="commitment-comparison" data-commitment-id="${esc(row.id)}"><header><div><span class="commitment-category">${m(sentence(row.after.category))}</span><h4>${esc(row.after.title)}</h4></div><span class="commitment-state" data-status="${esc(row.status)}">${m(statuses[row.status]||row.status)}</span></header>
      ${row.request?`<details class="commitment-context"><summary data-i18n=Request%20%26%20interpretation>Request & interpretation</summary><blockquote>${esc(row.request)}</blockquote><p>${esc(row.reason)}</p><small>Proposed by ${esc(row.recordedBy)} · approval is separate</small></details>`:''}
      ${row.changed?`<div class="commitment-diff"><div class="commitment-before"><span class="commitment-column-label" data-i18n=Agreed%20at%20baseline>Agreed at baseline</span>${row.before?textBlock(row.before.statement):'<p class="commitment-unrecorded" data-i18n=No%20prior%20commitment%20recorded>No prior commitment recorded</p>'}</div><span class="commitment-diff-arrow" aria-hidden="true">${uiIcon('arrow-right')}</span><div class="commitment-after"><span class="commitment-column-label">${m(review.status==='committed'?'Accepted in this review':'Proposed interpretation')}</span>${textBlock(row.after.statement)}</div></div>`:`<div class="commitment-invariant"><span class="commitment-invariant-mark">${uiIcon('shield-check')}</span><div><span class="commitment-column-label">${m('Must remain true')}</span>${textBlock(row.after.statement)}<small>${m(review.status==='open'?'The meaning is unchanged. Its implementation still needs review.':'The meaning is unchanged in this review.')}</small></div></div>`}
      <footer><div class="commitment-source-paths">${row.after.paths.map(path=>(review.changed_paths||[]).includes(path)?`<button type="button" class="text-button" data-open-changed-file="${esc(path)}">${uiIcon('file-text')}${esc(path)}</button>`:`<span>${esc(path)}</span>`).join('')}</div><div>${row.obligationId?`<button type="button" class="text-button" data-commitment-evidence="${esc(row.obligationId)}">${I18n.mark("Inspect verification")} ${uiIcon('arrow-right')}</button>`:''}${editable?`<button type="button" class="text-button" data-propose-commitment="${esc(row.id)}">${m(row.changed?'Edit proposal':'Propose revision')}</button>`:''}</div></footer><p class="commitment-verification"><span data-i18n=To%20verify>To verify</span>${esc(row.after.verification)}</p></article>`).join(''):
      `<div class="commitment-review-empty"><div><span>01</span><strong data-i18n=Interpret%20the%20request>Interpret the request</strong><p data-i18n=State%20the%20behavior%20or%20boundary%20being%20agreed.>State the behavior or boundary being agreed.</p></div><div><span>02</span><strong data-i18n=Connect%20the%20implementation>Connect the implementation</strong><p data-i18n=Link%20the%20files%20that%20carry%20that%20commitment.>Link the files that carry that commitment.</p></div><div><span>03</span><strong data-i18n=Define%20the%20evidence>Define the evidence</strong><p data-i18n=Make%20clear%20what%20must%20be%20checked%20before%20acceptance.>Make clear what must be checked before acceptance.</p></div></div>`}
      </section>`;
  }
  function setSurface(surface){
    const canvas=document.querySelector('.project-canvas');if(!canvas)return;
    canvas.dataset.surface=surface;
    canvas.querySelectorAll('[data-state-surface]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.stateSurface===surface)));
    if(surface==='relations')requestAnimationFrame(()=>{
      projectCanvasInstance?.resize();
      const current=CommitmentModel.workspace(state.activeProject,state.reviews,selections.get(state.activeProject.id)).selected;
      const id=current?`claim:${current.after.id}`:null;
      if(id&&projectCanvasData.nodes.some(node=>node.data.id===id)){canvasState.query='';$('#canvas-search').value='';selectCanvasObject(id,null,{revealDetails:false});}
      else fitProjectCanvas({fitAll:true});
    });
    ReviewMotion.enter(surface==='state'?$('#project-state-overview'):$('.project-canvas-body'),'panel');
  }
  function key(id){return `${state.auth?.user?.id}:${state.activeReview?.id}:${id||'new'}`;}
  function readingEditor(note={}){
    const paths=[...document.querySelectorAll('#commitment-files input')].map(input=>input.value);
    return `<fieldset class="source-reading-edit"><legend data-i18n=Source%20interpretation>Source interpretation</legend><div class="reading-editor-top"><label><span data-i18n=Label>Label</span><input data-reading-field="label" maxlength="80" value="${esc(note.label||'')}" required placeholder="e.g. Generation service" data-i18n-placeholder=e.g.%20Generation%20service></label><label><span data-i18n=Relationship>Relationship</span><select data-reading-field="relation"><option value="context"${note.relation==='context'?' selected':''} data-i18n=Context>Context</option><option value="supports"${note.relation==='supports'?' selected':''} data-i18n=Consistent%20reading>Consistent reading</option><option value="tension"${note.relation==='tension'?' selected':''} data-i18n=Question%20to%20resolve>Question to resolve</option></select></label><button type="button" class="icon-button" data-reading-remove aria-label="Remove this source reading" data-i18n-aria-label=Remove%20this%20source%20reading>${uiIcon('x-circle')}</button></div><div class="reading-editor-location"><label><span data-i18n=File>File</span><select data-reading-field="path">${paths.map(path=>`<option value="${esc(path)}"${note.path===path?' selected':''}>${esc(path)}</option>`).join('')}</select></label><label><span data-i18n=First%20line>First line</span><input type="number" min="1" data-reading-field="start_line" value="${note.start_line||1}" required></label><label><span data-i18n=Last%20line>Last line</span><input type="number" min="1" data-reading-field="end_line" value="${note.end_line||1}" required></label></div><label><span data-i18n=What%20does%20this%20code%20mean%3F>What does this code mean?</span><textarea data-reading-field="summary" maxlength="300" rows="2" required>${esc(note.summary||'')}</textarea></label></fieldset>`;
  }
  function readEditor(){return [...document.querySelectorAll('.source-reading-edit')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-reading-field]')].map(input=>[input.dataset.readingField,input.type==='number'?Number(input.value):input.value])));}
  function open(id=''){
    const review=state.activeReview;if(!review||review.status!=='open'||document.body.classList.contains('viewer-mode'))return;
    const form=$('#commitment-form');if(form.getAttribute('aria-busy')==='true')return;
    const row=CommitmentModel.reviewRows(review,state.manifest).find(item=>item.id===id);
    const draft=drafts.get(key(id));form.reset();form.dataset.commitmentId=id;form.dataset.commitmentDraft=key(id);
    const values=draft||{request:row?.request||review.intent_summary,title:row?.after.title||'',statement:row?.after.statement||'',category:row?.after.category||'behavior',reason:row?.reason||'',verification:row?.after.verification||''};
    for(const field of ['request','title','statement','category','reason','verification'])form.elements[field].value=values[field]||'';
    const paths=[...new Set([...(review.changed_paths||[]),...(row?.before?.paths||[]),...(row?.after?.paths||[])])];
    const selected=draft?.paths||row?.after.paths||[];
    $('#commitment-files').innerHTML=paths.map(path=>`<label><input type="checkbox" name="paths" value="${esc(path)}"${selected.includes(path)?' checked':''}><span>${esc(path)}</span></label>`).join('');
    $('#commitment-source-readings').innerHTML=(draft?.source_readings||row?.sourceReadings||[]).map(readingEditor).join('');
    $('.source-readings-editor').open=false;
    I18n.setText($('#commitment-dialog-title'),id?'Revise the proposed commitment':'Describe a project commitment');
    $('#commitment-error').textContent='';$('#commitment-reload').hidden=true;
    $('#commitment-draft-result').replaceChildren();
    showDialog('#commitment-dialog');
  }
  function remember(){
    const form=$('#commitment-form');if(!form.dataset.commitmentDraft)return;
    const values=Object.fromEntries(new FormData(form));values.paths=new FormData(form).getAll('paths');values.source_readings=readEditor();drafts.set(form.dataset.commitmentDraft,values);
  }
  let draftGeneration=0;
  const riskPending=new Map(),riskErrors=new Map();
  function currentRiskResult(review){
    return state.aiRuns.find(run=>run.review_id===review.id&&run.review_revision===review.revision&&run.project_version===state.activeProject?.version&&['commitment_draft','risk_analysis'].includes(run.feature))?.result;
  }
  function adviceMarkup(result){
    const model=result.method==='model';
    const sources=result.sources||[];
    const citationLabel=id=>{const s=sources.find(item=>item.id===id),e=(result.recorded_checks||[]).find(item=>item.id===id);return s?`${esc(s.path)}:${s.start_line} @${esc(s.revision.slice(0,8))}`:e?`${m('Recorded check')}: ${esc(e.kind)} · ${esc(e.status)} · ${esc(e.freshness)}`:'';};
    return `<p class="ai-advice-origin"><strong>${m(model?'AI advice · not verification':'AI analysis unavailable · local draft only')}</strong>${model?` · ${esc(result.model)}`:''}</p>
      ${model?`<ul class="ai-risk-list">${(result.risks||[]).map(r=>`<li data-severity="${esc(r.severity)}"><strong><span>${m({high:'High risk',medium:'Medium risk',low:'Low risk'}[r.severity]||'Risk')}</span> ${esc(r.title)}</strong><p>${esc(r.detail)}</p><p class="ai-risk-check">${m('Check next:')} ${esc(r.check)}</p><small>${(r.citation_ids||[]).map(citationLabel).join(' · ')}</small></li>`).join('')}</ul>${!result.risks?.length?`<p>${m('No specific risk identified in the supplied context. This is not a safety guarantee.')}</p>`:''}`:`<p>${m('No model risk assessment was completed. Retry or inspect the source manually.')}</p>`}
      <details class="ai-advice-sources"><summary>${m('Sources and limitations')}</summary><ul>${sources.map(s=>`<li><code>${esc(s.path)}:${s.start_line} @${esc(s.revision.slice(0,8))}</code><pre>${esc(s.excerpt)}</pre></li>`).join('')}${(result.recorded_checks||[]).map(e=>`<li>${citationLabel(e.id)}<p>${esc(e.summary)}</p></li>`).join('')}</ul>${(result.limitations||[]).map(line=>`<p>${esc(line)}</p>`).join('')}</details>`;
  }
  function riskView(review){
    const result=currentRiskResult(review),key=resourceKey(review),busy=riskPending.has(key),error=riskErrors.get(key);
    const expanded=riskDisclosures.get(key)??Boolean(result||busy||error);
    const status=busy?'Analyzing risks…':error?'Analysis needs attention':result?(result.method==='model'?'Advice available':'AI analysis unavailable · local draft only'):'Optional · not analyzed';
    return `<details class="ai-risk-panel" data-risk-panel data-risk-key="${esc(key)}"${expanded?' open':''}><summary><strong>${m('AI risk analysis')}</strong><span role="status">${m(status)}</span></summary><div class="ai-risk-body"><div class="ai-risk-heading"><p class="field-hint">${m('Uses the configured model with limited request, source and check records. Advice cannot approve a change.')}</p>${!document.body.classList.contains('viewer-mode')?`<button type="button" class="button" data-analyze-risks ${busy?'disabled':''}>${m(busy?'Analyzing risks…':result?'Analyze again':'Analyze risks')}</button>`:''}</div><div aria-busy="${busy}">${busy?`<p>${m('Reading source and checks; your work stays editable…')}</p>`:''}${error?`<p role="alert">${esc(error)}</p>`:''}${result?adviceMarkup(result):`<p>${m('Not analyzed · passing tests do not establish requirement coverage.')}</p>`}</div></div></details>`;
  }
  function rememberAdvice(result,review,feature,projectVersion){
    state.aiRuns.unshift({id:result.run_id,project_id:review.project_id,review_id:review.id,review_revision:review.revision,project_version:projectVersion,feature,result});
  }
  function refreshRiskPanel(){
    const panel=$('[data-risk-panel]');if(!panel||!state.activeReview)return;
    const restoreFocus=panel.contains(document.activeElement);
    riskDisclosures.set(panel.dataset.riskKey,panel.open);
    panel.outerHTML=riskView(state.activeReview);
    if(restoreFocus)($('[data-risk-panel] [data-analyze-risks]:not(:disabled)')||$('[data-risk-panel] > summary'))?.focus({preventScroll:true});
  }
  async function analyzeRisks(){
    const review=state.activeReview;if(!review)return;
    const key=resourceKey(review),version=state.activeProject.version,selection=state.selectionVersion;
    if(riskPending.has(key))return;
    const operation={};riskPending.set(key,operation);riskErrors.delete(key);refreshRiskPanel();
    try{
      const result=await api(`/api/reviews/${review.id}/risk-analysis`,{method:'POST',body:JSON.stringify({expected_revision:review.revision,language:I18n.language==='en'?'en':'zh'})});
      if(riskPending.get(key)!==operation||selection!==state.selectionVersion||state.activeReview?.id!==review.id||state.activeReview?.revision!==review.revision||state.activeProject?.version!==version)return;
      rememberAdvice(result,review,'risk_analysis',version);
    }catch(error){if(riskPending.get(key)===operation)riskErrors.set(key,I18n.t('Risk analysis failed. Your review is unchanged; retry when ready.')+' '+error.message);}
    finally{if(riskPending.get(key)===operation){riskPending.delete(key);refreshRiskPanel();}}
  }
  function draftFingerprint(){return JSON.stringify([...new FormData($('#commitment-form'))])+JSON.stringify(readEditor());}
  function applyGeneratedDraft(result){
    const form=$('#commitment-form'),values=result.proposal;
    for(const name of ['request','title','statement','category','reason','verification'])form.elements[name].value=values[name];
    form.querySelectorAll('input[name="paths"]').forEach(input=>input.checked=values.paths.includes(input.value));
    $('#commitment-source-readings').innerHTML=values.source_readings.map(readingEditor).join('');
    remember();
  }
  async function generateDraft(){
    const form=$('#commitment-form'),review=state.activeReview,button=$('#draft-commitment-button');
    if(!review||review.status!=='open'||button.disabled)return;
    const generation=++draftGeneration,revision=review.revision,keyAtStart=form.dataset.commitmentDraft,projectVersion=state.activeProject.version;
    const before=draftFingerprint(),wasEmpty=!['title','statement','reason','verification'].some(name=>form.elements[name].value.trim());
    const output=$('#commitment-draft-result');setBusy(button,true,'Drafting…');I18n.setText(output,'Reading the request and versioned source…');
    try{
      const result=await api(`/api/reviews/${review.id}/commitment-draft`,{method:'POST',body:JSON.stringify({expected_revision:revision,request:form.elements.request.value,language:I18n.language==='en'?'en':'zh'})});
      if(generation!==draftGeneration||!$('#commitment-dialog').open||state.activeReview?.id!==review.id||state.activeReview?.revision!==revision||state.activeProject?.version!==projectVersion||form.dataset.commitmentDraft!==keyAtStart)return;
      rememberAdvice(result,review,'commitment_draft',projectVersion);refreshRiskPanel();
      const automatic=wasEmpty&&draftFingerprint()===before;
      if(automatic)applyGeneratedDraft(result);
      output.removeAttribute('data-i18n');output.innerHTML=`<p><strong>${m(automatic?'Draft ready · edit and confirm below':'Your edits are kept. Review the new draft before replacing them.')}</strong></p>${!automatic?`<blockquote>${esc(result.proposal.statement)}</blockquote><button type="button" class="button" data-apply-generated-draft>${m('Use this draft')}</button>`:''}<p class="ai-advice-origin">${m(result.method==='model'?'AI advice · not verification':'AI analysis unavailable · local draft only')}${result.model?' · '+esc(result.model):''}</p><details><summary>${m('Review risks and sources')} · ${result.risks?.length||0}</summary>${adviceMarkup(result)}</details>`;
      output.querySelector('[data-apply-generated-draft]')?.addEventListener('click',event=>{if(state.activeReview?.id!==review.id||state.activeReview?.revision!==revision)return;applyGeneratedDraft(result);event.currentTarget.previousElementSibling?.remove();event.currentTarget.remove();I18n.setText(output.querySelector('p strong'),'Draft ready · edit and confirm below');});
    }catch(error){if(generation===draftGeneration&&$('#commitment-dialog').open){output.removeAttribute('data-i18n');output.textContent=I18n.t('Draft unavailable. Your edits are kept; retry or continue manually.')+' '+error.message;}}
    finally{if(generation===draftGeneration)setBusy(button,false);}
  }
  function bind(){
    document.addEventListener('toggle',event=>{
      if(event.target.matches?.('[data-risk-panel]'))riskDisclosures.set(event.target.dataset.riskKey,event.target.open);
    },true);
    $('#draft-commitment-button').addEventListener('click',generateDraft);
    $('#commitment-dialog').addEventListener('close',()=>{draftGeneration++;setBusy($('#draft-commitment-button'),false);});
    window.addEventListener('resize',revealSelection,{passive:true});
    document.addEventListener('click',async event=>{
      if(event.target.closest('[data-analyze-risks]'))return analyzeRisks();
      if(event.target.closest('[data-draft-commitment]')){open();return generateDraft();}
      if(event.target.closest('.meaning-workspace'))rememberReading();
      if(event.target.closest('[data-meaning-tree-retry]')){
        const projectId=state.activeProject.id,version=state.selectionVersion;
        state.projectTreeLoading=true;refreshInspection();
        try{const tree=await loadProjectTree(projectId);if(version===state.selectionVersion)state.projectTree=tree;}
        catch(error){if(version===state.selectionVersion)state.projectTree={error:error.message,entries:[]};}
        finally{if(version===state.selectionVersion){state.projectTreeLoading=false;refreshInspection();$('#meaning-file-scope')?.focus({preventScroll:true});}}return;
      }
      const view=event.target.closest('[data-meaning-view]');if(view)return setMeaningView(view.dataset.meaningView);
      if(event.target.closest('[data-meaning-files-toggle]')){
        const item=currentMeaning(),choice=inspectorChoice(item);if(choice.open)return closeInspector();
        Object.assign(choice,{open:true,opener:'[data-meaning-files-toggle]'});refreshInspection();
        if(matchMedia('(max-width:900px)').matches)$('#meaning-inspector').scrollIntoView({block:'start',behavior:'instant'});
        $('#meaning-file-search')?.focus({preventScroll:true});return;
      }
      const treeFile=event.target.closest('[data-meaning-tree-file]');if(treeFile){
        const item=currentMeaning(),choice=inspectorChoice(item),path=treeFile.dataset.meaningTreeFile;
        if(choice.scope==='project'){try{await openSnapshotFile(path);}catch(error){toast(error.message);}return;}
        Object.assign(choice,{path,reading:null,open:true,opener:`[data-meaning-tree-file="${CSS.escape(path)}"]`});refreshInspection();
        if(event.detail===0)$('#meaning-inspector-content').focus({preventScroll:true});return;
      }
      const next=event.target.closest('[data-meaning-next]');if(next){
        const item=currentMeaning(),action=next.dataset.meaningNext;
        if(action==='loading')return;
        if(action==='retry')return loadInspection(true);
        if(action==='new-review')return startNewReview();
        if(action==='review')return document.querySelector('.meaning-review-actions [data-meaning-inspect]')?.click();
        if(action==='source'){setMeaningView('canvas');const resource=resourceFor(item),step=CommitmentModel.nextStep(item,resource?.review,resource?.manifest,'ready');document.querySelector(`[data-source-reading="${step.readingIndex}"]`)?.click();}
        else return setMeaningView('evidence');
        inspectorChoice(item).opener='[data-meaning-next]';return;
      }
      if(event.target.closest('[data-meaning-history]'))return setMeaningView('history');
      if(event.target.closest('[data-reading-add]')){if(document.querySelectorAll('.source-reading-edit').length>=12)return toast('A proposal can include up to 12 source readings.');$('#commitment-source-readings').insertAdjacentHTML('beforeend',readingEditor());$('.source-readings-editor').open=true;$('#commitment-source-readings').lastElementChild.querySelector('input').focus();remember();return;}
      const removeReading=event.target.closest('[data-reading-remove]');if(removeReading){removeReading.closest('.source-reading-edit').remove();$('[data-reading-add]').focus();remember();return;}
      const readingCard=event.target.closest('[data-source-reading]');if(readingCard){const item=currentMeaning(),index=Number(readingCard.dataset.sourceReading),note=alignmentData(item).readings[index];if(!note)return;const choice=inspectorChoice(item);if(choice.reading!==index)choice.positions.delete(note.path);Object.assign(choice,{tab:'source',path:note.path,reading:index,scope:'linked',fileQuery:'',open:true,opener:`[data-source-reading="${index}"]`});for(const folder of choice.closedFolders)if(note.path.startsWith(folder+'/'))choice.closedFolders.delete(folder);refreshInspection();ReviewMotion.enter($('#meaning-inspector-content'),'panel');if(event.detail===0||matchMedia('(max-width:900px)').matches){$('#meaning-inspector').scrollIntoView({block:'start',behavior:'instant'});$('#meaning-inspector-content').focus({preventScroll:true});}return;}
      if(event.target.closest('[data-inspector-close]'))return closeInspector();
      if(event.target.closest('[data-inspector-expand]'))return toggleReadingFocus();
      if(event.target.closest('[data-alignment-correspondence]')){const card=$('.alignment-reading[data-relation="tension"]')||$('.alignment-reading');if(card){card.click();inspectorChoice(currentMeaning()).opener='[data-alignment-correspondence]';}return;}
      if(event.target.closest('[data-alignment-evidence]'))return setMeaningView('evidence');
      if(event.target.closest('[data-alignment-reason]'))return setMeaningView('history');
      const reviewChoice=event.target.closest('[data-review-meaning]');if(reviewChoice){reviewSelections.set(state.activeReview.id,reviewChoice.dataset.reviewMeaning);rememberMeaning(`${state.activeReview.id}:${reviewChoice.dataset.reviewMeaning}`);renderReview();document.querySelector(`[data-review-meaning="${CSS.escape(reviewChoice.dataset.reviewMeaning)}"]`)?.focus({preventScroll:true});ReviewMotion.enter($('.commitment-comparison'),'panel');return;}
      const choice=event.target.closest('[data-meaning-select]');if(choice){selections.set(state.activeProject.id,choice.dataset.meaningSelect);rememberMeaning(choice.dataset.meaningSelect);$('#project-state-overview').innerHTML=projectView(state.activeProject,state.reviews);document.querySelector(`[data-meaning-select="${CSS.escape(choice.dataset.meaningSelect)}"]`)?.focus({preventScroll:true});ReviewMotion.enter($('#meaning-focus'),'panel');return;}
      const file=event.target.closest('[data-meaning-file]');if(file){const item=currentMeaning();Object.assign(inspectorChoice(item),{tab:'source',path:file.dataset.meaningFile,reading:null,open:true,opener:`[data-meaning-file="${CSS.escape(file.dataset.meaningFile)}"]`});refreshInspection();ReviewMotion.enter($('#meaning-inspector-content'),'panel');if(event.detail===0||matchMedia('(max-width:900px)').matches){$('#meaning-inspector').scrollIntoView({block:'start',behavior:'instant'});$('#meaning-inspector-content').focus({preventScroll:true});}return;}
      if(event.target.closest('[data-meaning-retry]'))return loadInspection(true);
      const target=event.target.closest('[data-meaning-inspect],[data-meaning-verify],[data-meaning-full-diff],[data-meaning-edit]');if(target){
        const id=target.dataset.meaningReview||target.dataset.meaningInspect||target.dataset.meaningVerify||target.dataset.meaningEdit;
        const meaning=currentMeaning(),commitmentId=target.dataset.meaningCommitment||meaning?.after.id;
        if(commitmentId)reviewSelections.set(id,commitmentId);
        if(meaning&&!locationMeaning())rememberMeaning(meaning.key);
        try{await selectReview(id);if(state.activeReview?.id!==id||state.viewMode!=='review')return;
          if(target.dataset.meaningFullDiff)return openChangedFile(target.dataset.meaningFullDiff);
          if(target.dataset.meaningEdit)return open(target.dataset.meaningCommitment);
          if(target.hasAttribute('data-meaning-verify'))return focusEvidenceObligation(target.dataset.meaningObligation||'');
          setReviewWorkspaceTab('overview');document.querySelector(`[data-commitment-id="${CSS.escape(target.dataset.meaningCommitment)}"]`)?.scrollIntoView({block:'center'});
        }catch(error){toast(error.message);}return;
      }
      const propose=event.target.closest('[data-propose-commitment]');if(propose)return open(propose.dataset.proposeCommitment);
      const surface=event.target.closest('[data-state-surface]');if(surface)return setSurface(surface.dataset.stateSurface);
      const review=event.target.closest('[data-commitment-review]');if(review)return selectReview(review.dataset.commitmentReview).catch(e=>toast(e.message));
      const rules=event.target.closest('.state-existing-rules [data-open-project-view]');if(rules)return setProjectView(rules.dataset.openProjectView);
      const start=event.target.closest('[data-state-start]');if(start){const next=state.reviews.find(r=>r.status==='open');if(!next)return startNewReview();try{await selectReview(next.id);return open();}catch(error){toast(error.message);return;}}
      const evidence=event.target.closest('[data-commitment-evidence]');if(evidence)focusEvidenceObligation(evidence.dataset.commitmentEvidence);
    });
    document.addEventListener('input',event=>{
      if(event.target.id==='meaning-file-search'){
        const item=currentMeaning();inspectorChoice(item).fileQuery=event.target.value;
        const template=document.createElement('template');template.innerHTML=fileTreeView(item);
        $('.meaning-file-tree').replaceWith(template.content.querySelector('.meaning-file-tree'));return;
      }
      if(event.target.id!=='meaning-source-search')return;
      const query=event.target.value.trim().toLowerCase(),rows=[...document.querySelectorAll('.meaning-code-line')];
      const matches=rows.filter(row=>{const match=Boolean(query)&&row.querySelector('code').textContent.toLowerCase().includes(query);row.classList.toggle('search-match',match);return match;});
      I18n.setText($('#meaning-source-matches'),query?'{count} matching lines':'',{count:matches.length});
      if(matches[0]){const pane=$('.meaning-code'),line=matches[0].getBoundingClientRect(),bounds=pane.getBoundingClientRect();pane.scrollTop+=line.top-bounds.top-pane.clientHeight/2+line.height/2;}
    });
    document.addEventListener('keydown',event=>{
      const tab=event.target.closest('[data-meaning-view]');
      if(tab&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const tabs=['canvas','changes','evidence','history'],index=tabs.indexOf(tab.dataset.meaningView),value=event.key==='Home'?tabs[0]:event.key==='End'?tabs.at(-1):tabs[(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];setMeaningView(value);}
      if(event.key==='Escape'&&event.target.closest('#meaning-inspector')){event.preventDefault();if(inspectorChoice(currentMeaning()).expanded)toggleReadingFocus();else closeInspector();}
    });
    document.addEventListener('change',event=>{if(event.target.id==='meaning-file-scope'){rememberReading();const choice=inspectorChoice(currentMeaning());choice.scope=event.target.value;choice.fileQuery='';refreshInspection();$('#meaning-file-scope').focus({preventScroll:true});}});
    document.addEventListener('toggle',event=>{if(event.target.matches?.('[data-meaning-folder]')){const item=currentMeaning();if(!item)return;const choice=inspectorChoice(item);if(choice.fileQuery)return;const path=event.target.dataset.meaningFolder;event.target.open?choice.closedFolders.delete(path):choice.closedFolders.add(path);}},true);
    const form=$('#commitment-form');form.addEventListener('input',remember);form.addEventListener('change',remember);
    form.addEventListener('invalid',event=>{const details=event.target.closest('.source-readings-editor');if(details)details.open=true;},true);
    $('#commitment-reload').onclick=async()=>{remember();const id=form.dataset.commitmentId,reviewId=state.activeReview?.id;$('#commitment-dialog').close();try{await selectReview(reviewId);open(id);}catch(error){toast(error.message);}};
    form.addEventListener('submit',async event=>{
      event.preventDefault();if(form.getAttribute('aria-busy')==='true')return;
      const values=Object.fromEntries(new FormData(form));values.paths=new FormData(form).getAll('paths');values.source_readings=readEditor();
      if(!values.paths.length){I18n.setText($('#commitment-error'),"Select at least one file that carries this commitment.");return;}
      remember();const button=event.submitter;let operation;setBusy(button,true,'Saving proposal…');form.setAttribute('aria-busy','true');
      try{
        operation=requireReviewOperation(form);const draftKey=form.dataset.commitmentDraft;
        await api(`/api/reviews/${operation.reviewId}/commitments`,{method:'POST',body:JSON.stringify({...values,commitment_id:form.dataset.commitmentId||null,expected_revision:operation.revision,actor:state.auth.user.actor})});
        drafts.delete(draftKey);await completeReviewOperation(form,operation,'Commitment proposed — verification and approval remain separate');
      }catch(error){if(!operation||reviewOperations.get(form)===operation){$('#commitment-error').textContent=error.message;$('#commitment-reload').hidden=false;}}
      finally{form.removeAttribute('aria-busy');setBusy(button,false);}
    });
  }
  function toggleReadingFocus(){
    const item=currentMeaning();if(!item)return;
    const choice=inspectorChoice(item);choice.expanded=!choice.expanded;
    const pane=$('.meaning-code'),scroll=pane?.scrollTop;
    $('#meaning-focus').dataset.inspectorExpanded=String(choice.expanded);
    const button=$('[data-inspector-expand]');button.setAttribute('aria-pressed',String(choice.expanded));
    I18n.setText($('[data-reading-focus-label]'),choice.expanded?'Back to comparison':'Focus reading');
    if(pane)pane.scrollTop=scroll;
    button.focus({preventScroll:true});
    if(matchMedia('(max-width:900px)').matches)$('#meaning-inspector').scrollIntoView({block:'start',behavior:'instant'});
  }
  function closeInspector(){const item=currentMeaning();if(!item)return;rememberReading();const choice=inspectorChoice(item);choice.open=false;choice.expanded=false;refreshInspection();const original=document.querySelector(choice.opener||'[data-meaning-files-toggle]'),opener=original?.checkVisibility()?original:$('[data-meaning-files-toggle]');opener?.focus({preventScroll:true});if(matchMedia('(max-width:900px)').matches)opener?.scrollIntoView({block:'center',behavior:'instant'});}
  function clear(){inspectionRequest?.controller.abort();inspectionRequest=null;inspections.clear();inspectorChoices.clear();drafts.clear();selections.clear();reviewSelections.clear();const form=$('#commitment-form');form?.reset();if(form)delete form.dataset.commitmentDraft;$('#commitment-dialog')?.close();}
  return {projectView,reviewView,setSurface,bind,riskView,clear:()=>{riskPending.clear();riskErrors.clear();riskDisclosures.clear();clear();}};
})();
