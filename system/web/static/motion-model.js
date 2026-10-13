/* Presentation only. Motion cannot execute checks or change governed records. */
(function(root,factory){const motion=factory();if(typeof module==='object'&&module.exports)module.exports=motion;else root.ReviewMotion=motion;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  const ease='cubic-bezier(0.22, 1, 0.36, 1)';
  const media=typeof window!=='undefined'?window.matchMedia('(prefers-reduced-motion: reduce)'):null;
  const running=new Set();
  const byNode=new WeakMap();
  const reduced=()=>Boolean(media?.matches);
  function entryPlan(kind='panel',{reduced:quiet=false,index=0}={}) {
    if(quiet)return null;
    const shapes={panel:[6,0.99,220],dialog:[10,0.97,240],inspector:[12,1,260],tile:[5,0.98,280]};
    const [offset,scale,duration]=shapes[kind]||shapes.panel;
    return {keyframes:[{opacity:0,transform:kind==='inspector'?`translateX(${offset}px)`:`translateY(${offset}px) scale(${scale})`},{opacity:1,transform:'none'}],options:{duration,easing:ease,delay:kind==='tile'?Math.min(72,Math.max(0,index)*12):0,fill:'none'}};
  }
  function layoutPlan(before,after,{reduced:quiet=false}={}) {
    const valid=r=>r&&['x','y','width','height'].every(key=>Number.isFinite(r[key]))&&r.width>0&&r.height>0;
    if(quiet||!valid(before)||!valid(after))return null;
    if(['x','y','width','height'].every(key=>Math.abs(before[key]-after[key])<0.1))return null;
    return {keyframes:[{transform:`translate(${before.x-after.x}px, ${before.y-after.y}px) scale(${before.width/after.width}, ${before.height/after.height})`,transformOrigin:'0 0'},{transform:'none',transformOrigin:'0 0'}],options:{duration:300,easing:ease,fill:'none'}};
  }
  function play(node,plan) {
    byNode.get(node)?.cancel();
    if(!plan||reduced()||!node?.isConnected||typeof node.animate!=='function')return null;
    const animation=node.animate(plan.keyframes,plan.options);
    byNode.set(node,animation);running.add(animation);
    animation.finished.then(()=>running.delete(animation),()=>running.delete(animation));
    return animation;
  }
  function enter(node,kind='panel',index=0){return play(node,entryPlan(kind,{reduced:reduced(),index}));}
  function capture(container){return new Map([...container?.querySelectorAll('[data-open-changed-file]')||[]].map(node=>[node.dataset.openChangedFile,node.getBoundingClientRect().toJSON()]));}
  function reflow(container,before){container?.querySelectorAll('[data-open-changed-file]').forEach((node,index)=>{const old=before.get(node.dataset.openChangedFile);play(node,old?layoutPlan(old,node.getBoundingClientRect().toJSON(),{reduced:reduced()}):entryPlan('tile',{reduced:reduced(),index}));});}
  function indicator(container,selector){
    const active=container?.querySelector(selector);if(!active||!active.getClientRects().length)return;
    let mark=container.querySelector(':scope > .motion-indicator');
    if(!mark){mark=document.createElement('span');mark.className='motion-indicator';mark.setAttribute('aria-hidden','true');container.prepend(mark);}
    mark.style.width=`${active.offsetWidth}px`;mark.style.transform=`translateX(${active.offsetLeft}px)`;
  }
  function disclosures(container){container?.querySelectorAll('details').forEach(detail=>{
    if(detail.dataset.motionBound)return;detail.dataset.motionBound='true';
    detail.addEventListener('toggle',()=>{if(detail.open){const body=[...detail.children].find(child=>child.tagName!=='SUMMARY');enter(body,'panel');}});
  });}
  media?.addEventListener?.('change',()=>{if(reduced()){running.forEach(animation=>animation.cancel());running.clear();}});
  return {entryPlan,layoutPlan,enter,capture,reflow,indicator,disclosures};
});
