const assert=require('node:assert/strict');
const {test}=require('node:test');
const {existsSync}=require('node:fs');
const path=require('node:path').resolve(__dirname,'../system/web/static/motion-model.js');
const motion=existsSync(path)?require(path):{};

test('motion uses bounded interaction timings rather than delaying a task',()=>{
  assert.equal(typeof motion.entryPlan,'function');
  for(const kind of ['panel','dialog','inspector','tile']) {
    const plan=motion.entryPlan(kind);
    assert.ok(plan.options.duration>=120 && plan.options.duration<=360);
    assert.equal(plan.keyframes.at(-1).opacity,1);
    assert.equal(plan.options.fill,'none');
  }
});

test('reduced-motion entry plans never create hidden or moving content',()=>{
  assert.equal(motion.entryPlan('panel',{reduced:true}),null);
  assert.equal(motion.layoutPlan({x:0,y:0,width:10,height:10},{x:20,y:20,width:20,height:20},{reduced:true}),null);
});

test('layout motion follows actual old and new rectangles without mutating them',()=>{
  const before={x:10,y:30,width:100,height:60},after={x:40,y:10,width:200,height:120};
  const snapshot=JSON.stringify([before,after]);
  const plan=motion.layoutPlan(before,after);
  assert.equal(plan.keyframes[0].transform,'translate(-30px, 20px) scale(0.5, 0.5)');
  assert.equal(plan.keyframes.at(-1).transform,'none');
  assert.equal(plan.options.duration,300);
  assert.equal(JSON.stringify([before,after]),snapshot);
});

test('unavailable geometry and unchanged layouts are not invented as motion',()=>{
  const rect={x:0,y:0,width:100,height:60};
  assert.equal(motion.layoutPlan(rect,rect),null);
  for(const bad of [null,{...rect,width:0},{...rect,x:NaN},{...rect,height:Infinity}]) assert.equal(motion.layoutPlan(bad,rect),null);
});

test('stagger is bounded so the last tile stays responsive',()=>{
  const first=motion.entryPlan('tile',{index:0}),last=motion.entryPlan('tile',{index:1000});
  assert.equal(first.options.delay,0);
  assert.ok(last.options.delay<=72);
  assert.equal(last.options.duration,first.options.duration);
});
