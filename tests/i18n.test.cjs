const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const file=require('node:path').join(__dirname,'../system/web/static/i18n.js');
function load(saved=null,denyStorage=false){
  const writes=[];const context={module:{exports:{}},localStorage:{getItem(){if(denyStorage)throw Error('blocked');return saved;},setItem(k,v){if(denyStorage)throw Error('blocked');writes.push([k,v]);}}};
  vm.runInNewContext(fs.existsSync(file)?fs.readFileSync(file,'utf8'):'module.exports={}',context);
  return {i18n:context.module.exports,writes};
}
test('Chinese is the default and English is an explicit persisted choice',()=>{
  const {i18n,writes}=load();assert.equal(i18n.language,'zh-CN');
  assert.equal(i18n.t('Project state'),'项目共识');
  i18n.setLanguage('en');assert.equal(i18n.t('Project state'),'Project state');
  assert.deepEqual(writes,[['agentic-consensus-language','en']]);
  assert.equal(load('en').i18n.language,'en');
  assert.equal(load('unsupported').i18n.language,'zh-CN');
});
test('blocked storage does not prevent switching language',()=>{
  const {i18n}=load(null,true);assert.equal(i18n.language,'zh-CN');
  assert.doesNotThrow(()=>i18n.setLanguage('en'));assert.equal(i18n.language,'en');
});
test('paper demo can default to English without changing the normal app default',()=>{
  const context={module:{exports:{}},document:{documentElement:{dataset:{defaultLanguage:'en'}},readyState:'loading',addEventListener(){}}};
  vm.runInNewContext(fs.readFileSync(file,'utf8'),context);
  assert.equal(context.module.exports.language,'en');
  assert.equal(load().i18n.language,'zh-CN');
});
test('English language controls use an English accessible label',()=>{
  const {i18n}=load('en'); const attrs={};
  const button={textContent:'',closest:()=>null,dataset:{},hasAttribute:k=>k==='data-language-switch',getAttribute:k=>attrs[k]??null,setAttribute:(k,v)=>{attrs[k]=v;},matches:()=>true,querySelectorAll:()=>[]};
  i18n.apply(button);
  assert.equal(button.textContent,'ZH');
  assert.equal(attrs['aria-label'],'Switch to Chinese');
});
test('message formatting translates labels but preserves interpolated user content',()=>{
  const {i18n}=load();assert.equal(i18n.t('Recorded by {actor}',{actor:'Project state'}),'记录者：Project state');
  assert.equal(i18n.t('Unknown message'),'Unknown message');
  assert.equal(i18n.t('{count} linked files',{count:3}),'关联 3 个文件');
});
test('HTML messages escape parameters and carry explicit localization metadata',()=>{
  const {i18n}=load();const html=i18n.mark('Recorded by {actor}',{actor:'<script>"&'});
  assert.match(html,/data-i18n=/);assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);
});
test('explicit display counts and relative times translate without touching arbitrary sentences',()=>{
  const {i18n}=load();assert.equal(i18n.t('3 missing evidence records'),'缺少 3 条证据');
  assert.equal(i18n.t('1 month ago'),'1 个月前');
  assert.equal(i18n.t('The user wrote: 3 missing evidence records'),'The user wrote: 3 missing evidence records');
  i18n.setLanguage('en');assert.equal(i18n.t('{count} files',{count:1}),'1 file');
});
test('canvas labels translate system framing, never the user title or file name',()=>{
  const {i18n}=load();assert.equal(typeof i18n.canvasLabel,'function');
  assert.equal(i18n.canvasLabel({type:'claim',label:'Project state'}),'Project state');
  assert.equal(i18n.canvasLabel({type:'artifact',label:'Open'}),'Open');
  assert.equal(i18n.canvasLabel({type:'review',status:'open',label:'Open\nProject state'}),'进行中\nProject state');
  assert.equal(i18n.canvasLabel({type:'state',label:'Current state\nVersion 1'}),'当前共识\n版本 1');
});
test('continuity and next-action labels support Chinese and English',()=>{
  const {i18n}=load();
  for(const key of ['Current version','Decision history','Recheck existing commitments','Check this version','Resolve the source question','No assessment for this version'])assert.notEqual(i18n.t(key),key);
  assert.equal(i18n.t('Version {ref}',{ref:'abc123'}),'版本 abc123');
  i18n.setLanguage('en');assert.equal(i18n.t('Current version'),'Current version');
});
