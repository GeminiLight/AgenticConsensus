/* Snapshot-bound projections. Text and generic test passes are not verification. */
(function(root,factory){const model=factory();if(typeof module==='object'&&module.exports)module.exports=model;else root.CommitmentModel=model;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  function primaryObligation(rows) {
    const priority=['contested','stale','missing','unknown','unassessed','waived','satisfied'];
    const rank=status=>priority.includes(status)?priority.indexOf(status):3;
    return [...rows].sort((a,b)=>rank(a.status)-rank(b.status))[0];
  }
  function reviewRows(review,manifest={}) {
    const changes=new Map((review.commitment_changes||[]).map(change=>[change.after.id,change]));
    const baseline=new Map((review.commitment_baseline||[]).map(item=>[item.id,item]));
    const ids=[...new Set([...baseline.keys(),...changes.keys()])];
    return ids.flatMap(id=>{
      const change=changes.get(id),before=change?change.before:baseline.get(id),after=change?.after||before;
      if(!change&&!after.paths.some(path=>(review.changed_paths||[]).includes(path)))return [];
      const evidence=primaryObligation((manifest.obligation_statuses||[]).filter(item=>item.claim_id===id&&(!change?.obligation_id||item.obligation_id===change.obligation_id)));
      return [{id,before,after,changed:Boolean(change),request:change?.request||'',reason:change?.reason||'',
        sourceReadings:change?.source_readings||[],recordedBy:change?.recorded_by||'',status:evidence?.status||'unassessed',obligationId:evidence?.obligation_id||change?.obligation_id||null}];
    });
  }
  function projectState(project,reviews=[]) {
    const open=reviews.filter(review=>review.status==='open');
    return {authorized:project.commitments||[],unframed:open.filter(review=>!reviewRows(review).length),pending:open.flatMap(review=>reviewRows(review).map(row=>{
      const change=(review.commitment_changes||[]).find(change=>change.after.id===row.id);
      return {...(change||{before:row.before,after:row.after}),kind:change?'proposal':'recheck',reviewId:review.id,reviewTitle:review.intent_summary,targetRef:review.target_ref};
    }))};
  }
  function workspace(project,reviews=[],selectedKey=null) {
    const data=projectState(project,reviews);
    const same=(left,right)=>['id','title','statement','category','verification'].every(key=>left[key]===right[key])&&JSON.stringify(left.paths)===JSON.stringify(right.paths);
    const ordered=[...reviews].sort((a,b)=>(b.base_version||0)-(a.base_version||0)||String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
    const originFor=item=>item&&ordered.find(review=>review.status==='committed'&&(review.commitment_changes||[]).some(change=>same(change.after,item)));
    const provenance=(source,item)=>{
      const change=source?.commitment_changes.find(change=>same(change.after,item));
      const decision=(source?.decision_records||[]).filter(record=>record.action==='commit').at(-1);
      return {originReviewId:source?.id||null,originTarget:source?.target_ref||null,originReadings:change?.source_readings||[],
        request:change?.request||'',reason:change?.reason||'',recorded_by:change?.recorded_by||'',decidedBy:decision?.actor||''};
    };
    const pending=data.pending.map(change=>({...provenance(originFor(change.before),change.before),...change,key:`${change.reviewId}:${change.after.id}`}));
    const authorized=data.authorized.map(item=>{
      const source=originFor(item);
      // An origin explains the decision; only an exact governed target can describe current applicability.
      const current=project.head_ref?ordered.find(review=>{
        if(review.status!=='committed'||review.target_ref!==project.head_ref)return false;
        const change=(review.commitment_changes||[]).find(change=>change.after.id===item.id);
        const snapshot=change?.after||(review.commitment_baseline||[]).find(row=>row.id===item.id);
        return snapshot&&same(snapshot,item);
      }):source;
      const change=current?.commitment_changes?.find(change=>same(change.after,item));
      return {...provenance(source,item),key:`agreed:${item.id}`,kind:'agreed',after:item,before:null,
        targetRef:project.head_ref||current?.target_ref||null,applicability:current?'current':'unassessed',
        source_readings:change?.source_readings||[],reviewId:current?.id||null,reviewTitle:current?.intent_summary||''};
    });
    const cards=[...pending,...authorized];
    return {pending,authorized,unframed:data.unframed,cards,selected:cards.find(card=>card.key===selectedKey)||cards[0]||null,
      linkedPaths:[...new Set(cards.flatMap(card=>card.after.paths))]};
  }
  function inspection(item,review={},manifest={},patches=[]) {
    const obligations=(manifest.obligation_statuses||[]).filter(row=>row.claim_id===item.after.id&&(!item.obligation_id||row.obligation_id===item.obligation_id));
    const obligation=primaryObligation(obligations);
    const evidenceIds=new Set(obligations.flatMap(row=>row.evidence_ids||[]));
    const evidence=(review.evidence||[]).filter(record=>evidenceIds.has(record.id));
    const files=item.after.paths.map(path=>{
      const patch=patches.find(file=>file.path===path);
      return {path,changes:patch?{additions:patch.additions,deletions:patch.deletions,partial:Boolean(patch.partial)}:null};
    });
    return {status:obligation?.status||'unassessed',obligation,obligations,evidence,files,totalChanges:files.reduce((sum,file)=>sum+(file.changes?file.changes.additions+file.changes.deletions:0),0)};
  }
  function assessment(item,review={},manifest={},load='ready') {
    if(load==='ready'&&item.targetRef&&review.target_ref!==item.targetRef)load='error';
    const ready=Boolean(item.reviewId)&&load==='ready'&&(!item.targetRef||review.target_ref===item.targetRef);
    const data=ready?inspection(item,review,manifest):null;
    const blockers=ready?(manifest.admission_checks||[]).filter(check=>check.status==='block').length:0;
    const decision=!item.reviewId?'unassessed':load==='error'?'error':!ready?'loading':review.status==='open'?(manifest.committable===true?'pending':manifest.committable===false?'blocked':'unassessed'):review.status||'unassessed';
    return {target:item.targetRef||review.target_ref||null,evidence:!item.reviewId?'unassessed':load==='error'?'error':!ready?'loading':data.status,
      supported:data?.obligations.filter(row=>row.status==='satisfied').length||0,total:data?.obligations.length||0,
      records:data?.evidence.length||0,decision,blockers:ready&&review.status==='open'?(blockers||(manifest.blockers||[]).length):0};
  }
  function alignment(item,review={},manifest={}) {
    const readings=(item.source_readings||[]).filter(note=>note.version_ref===review.target_ref&&item.after.paths.includes(note.path));
    return {readings,questions:readings.filter(note=>note.relation==='tension').length,
      agreed:item.kind==='agreed'||item.kind==='recheck',evidenceStatus:inspection(item,review,manifest).status,
      unreadPaths:item.after.paths.filter(path=>!readings.some(note=>note.path===path))};
  }
  function nextStep(item,review={},manifest={},load='ready') {
    if(!item.reviewId)return {action:'new-review',status:'unassessed'};
    if(load==='error')return {action:'retry',status:'error'};
    if(load!=='ready')return {action:'loading',status:'loading'};
    if((manifest.admission_checks||[]).some(check=>check.key==='base_version'&&check.status==='block'))return {action:'review',status:'rebase'};
    const data=alignment(item,review,manifest),readingIndex=data.readings.findIndex(note=>note.relation==='tension');
    if(readingIndex!==-1)return {action:'source',status:'question',readingIndex};
    if(!['satisfied','waived'].includes(data.evidenceStatus))return {action:'evidence',status:data.evidenceStatus};
    if(data.evidenceStatus==='satisfied'&&review.status==='committed')return {action:'review',status:'recorded'};
    return {action:'review',status:data.evidenceStatus};
  }
  return {reviewRows,projectState,workspace,inspection,alignment,nextStep,assessment};
});
