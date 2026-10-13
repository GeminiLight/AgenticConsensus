const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function factory(){const file=path.join(__dirname,'../system/web/static/paper-demo.js');assert.ok(fs.existsSync(file),'A session-bound paper transport is required');const c={module:{exports:{}},Response};vm.runInNewContext(fs.readFileSync(file,'utf8'),c);return c.module.exports;}
test('parallel callers carry the newest signed snapshot without overwriting each other',async()=>{
  const calls=[],saved=new Map();const create=factory();
  const transport=create({enabled:true,storage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)},fetch:async(url,options)=>{const request=JSON.parse(options.body);calls.push(request);return new Response(JSON.stringify({result:{step:calls.length},snapshot:'signed-'+calls.length}));}});
  transport.configure('session-a');
  const [a,b]=await Promise.all([transport.request('/api/projects',{},'session-a'),transport.request('/api/projects/p/reviews',{},'session-a')]);
  assert.equal(calls[0].snapshot,null);assert.equal(calls[1].snapshot,'signed-1');
  assert.equal((await a.json()).step,1);assert.equal((await b.json()).step,2);
  transport.configure('session-b');await transport.request('/api/projects',{},'session-b');assert.equal(calls[2].snapshot,null);
});
test('an answer arriving after sign-out cannot restore the old session',async()=>{
  const create=factory();let resolve;
  const transport=create({enabled:true,fetch:()=>new Promise(done=>{resolve=done;})});
  transport.configure('a');const pending=transport.request('/api/projects',{},'a');await Promise.resolve();transport.clear();
  resolve(new Response(JSON.stringify({result:[],snapshot:'old-state'})));
  await assert.rejects(pending,/session changed/i);
});
test('reload restores this session and a failed response keeps its last signed state',async()=>{
  const create=factory(),saved=new Map(),calls=[];
  const storage={getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
  const send=async(url,options)=>{calls.push(JSON.parse(options.body));return new Response(JSON.stringify(calls.length===1?{result:[],snapshot:'saved-state'}:{detail:'temporarily unavailable'}),{status:calls.length===1?200:503});};
  await create({enabled:true,storage,fetch:send}).request('/api/projects',{},'owner');
  const reloaded=create({enabled:true,storage,fetch:send});
  assert.equal((await reloaded.request('/api/projects',{},'owner')).status,503);
  await reloaded.request('/api/projects',{},'owner');
  assert.equal(calls[1].snapshot,'saved-state');assert.equal(calls[2].snapshot,'saved-state');
  reloaded.clear();assert.equal(saved.size,0);
});
