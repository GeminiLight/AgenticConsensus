/* Isolated, temporary paper cases: the server signs records, never credentials. */
(function(root){
  function create({enabled=false,fetch:send,storage}={}){
    const key='consensus-paper-session-v1';let owner=null,snapshot=null,queue=Promise.resolve(),generation=0;
    function clear(){owner=null;snapshot=null;generation++;queue=Promise.resolve();try{storage?.removeItem(key);}catch{}}
    function configure(next){
      if(next===owner)return;
      owner=next;snapshot=null;generation++;queue=Promise.resolve();
      try{const saved=JSON.parse(storage?.getItem(key)||'null');if(saved?.owner===owner)snapshot=saved.snapshot;else storage?.removeItem(key);}catch{}
    }
    function request(path,options={},csrf){
      if(!enabled||path.startsWith('/api/auth/'))return send(path,options);
      configure(csrf);const current=generation;
      const run=async()=>{
        if(current!==generation)throw new Error('The demo session changed. Reload before continuing.');
        const response=await send('/api/paper-demo/dispatch',{method:'POST',credentials:'same-origin',signal:options.signal,
          headers:{Accept:'application/json','Content-Type':'application/json','X-CSRF-Token':csrf},
          body:JSON.stringify({path,method:String(options.method||'GET').toUpperCase(),body:options.body?JSON.parse(options.body):null,snapshot})});
        const envelope=await response.json().catch(()=>({detail:'The demo service could not respond. Your last session state is kept.'}));
        if(current!==generation)throw new Error('The demo session changed. Reload before continuing.');
        if(typeof envelope.snapshot==='string'){
          snapshot=envelope.snapshot;
          try{storage?.setItem(key,JSON.stringify({owner,snapshot}));}catch{}
        }
        return new Response(JSON.stringify(envelope.result??envelope),{status:response.status,headers:{'Content-Type':'application/json'}});
      };
      const result=queue.then(run);queue=result.catch(()=>{});return result;
    }
    return {request,configure,clear};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports=create;
  else{
    let storage;try{storage=root.sessionStorage;}catch{}
    root.PaperDemo=create({enabled:root.document.documentElement.dataset.paperDemo==='true',fetch:root.fetch.bind(root),storage});
  }
})(typeof globalThis!=='undefined'?globalThis:this);
