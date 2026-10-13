/* Buildless progressive enhancement; the English page also works without JS. */
const english = Object.fromEntries([...document.querySelectorAll('[data-i18n]')].map(el => [el.dataset.i18n, el.textContent]));
const chinese = {
  skip:'跳到正文',navApproach:'思路',navStart:'开始使用',eyebrow:'开源 · 研究原型',
  hero1:'与智能体一起开发。',hero2:'依据证据做决定。',
  heroDescription:'为人和 AI 的编程协作建立共享、可追溯的项目状态。将请求、代码、需求和证据，连接到推动项目前进的人工决定。',
  runLocally:'本地运行',viewSource:'查看源码',heroFootnote:'本地优先。模型建议可选。决定权交给人。',
  projectState:'项目状态',intentLabel:'01 / 请求',intentValue:'要改变什么？',requirementLabel:'02 / 需求',requirementValue:'保留已约定的要求',versionBound:'绑定版本',
  codeLabel:'03 / 代码',codeValue:'检查这次修改',immutableRevision:'Git 版本',decisionLabel:'04 / 证据 → 决定',decisionValue:'先验证，再授权。',mapFooter:'连贯的记录，可检查的来龙去脉。',
  approachEyebrow:'基本思路',approachTitle:'让协作有一个共同的项目状态。',approachDescription:'对话可以解释修改。项目还需要记录：要满足什么、检查了哪个版本、谁授权了下一步。',
  step1Title:'保留原始意图',step1Description:'把原始请求、候选解释和澄清记录，与提出的修改保存在一起。',
  step2Title:'绑定验证证据',step2Description:'依据明确的需求检查代码和测试结果。区分缺少的验证与来自旧版本的证据。',
  step3Title:'记录人工决定',step3Description:'检查项目权限和状态版本后，由获授权的人记录决定，保留审计轨迹。',
  exampleEyebrow:'一个小例子',exampleTitle:'测试通过了，需求覆盖了吗？',exampleDescription:'智能体为公开的参与者导出添加所属机构。现有测试都通过，但展开整个字典也泄露了私密字段。',
  promiseLabel:'约定的需求',promise:'公开导出不得包含邮箱和内部备注。',exampleNote:'来自合成案例的示意状态。此面板不执行测试，也不记录决定。',
  illustration:'示意',proposal:'提出的修改',revision:'修订后的修改',existingTests:'现有测试',existingTestsValue:'通过，但未覆盖私密字段',pass:'通过',privacyCheck:'隐私需求',privacyCheckValue:'仍需当前版本的验证',missing:'缺少',
  proposalDecision:'人工决定：要求进行针对性修订',carriedRequirement:'隐私需求',carriedRequirementValue:'延续到新的版本',retained:'保留',newEvidence:'当前版本的证据',newEvidenceValue:'添加并检查隐私负例测试',pending:'待验证',revisionDecision:'审批等待新证据和明确授权',
  startEyebrow:'体验工作台',startTitle:'从自己的电脑开始。',startDescription:'打开一个合成项目，检查它的修改，沿着证据做出人工决定。核心演示无需模型密钥。',localFirst:'本地优先',fullGuide:'阅读完整指南',quickstart:'快速开始',copy:'复制',
  openLocal:'打开 http://127.0.0.1:8765。创建首个账户时，使用演示审计身份 security-lead@example.test。',resetNote:'再次打开工作区时运行 serve 即可。demo --reset 会重建演示数据。',
  scopeTitle:'这是一个范围明确的早期原型。',scopeDescription:'当前源代码分析聚焦 Python import，自动实现限于一种 import 替换。GitHub 接入读取版本快照。记录决定不会合并拉取请求。可选的模型建议没有授权权力。',
  securityBoundary:'了解安全边界',footerDescription:'人和 AI 编程协作的共享项目状态。',contribute:'参与贡献'
};
let language = 'en';
function setLanguage(next) {
  language = next;
  document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en';
  const words = next === 'zh' ? chinese : english;
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = words[el.dataset.i18n] ?? english[el.dataset.i18n]; });
  const switcher = document.getElementById('language');
  switcher.textContent = next === 'zh' ? 'EN' : '中文';
  switcher.setAttribute('aria-label', next === 'zh' ? 'Switch to English' : '切换到中文');
  document.querySelector('.state-map').setAttribute('aria-label', next === 'zh' ? '示意项目状态：请求连接到需求、代码修改、证据和获授权的人工决定' : 'Illustrative project state: intent connects to a requirement, a code change, evidence, and an authorized human decision');
  document.querySelector('.example-tabs').setAttribute('aria-label', next === 'zh' ? '比较两个示意版本' : 'Compare illustrative revisions');
  try { localStorage.setItem('agenticconsensus.website.language', next); } catch { /* Storage is optional. */ }
}
const switcher = document.getElementById('language');
switcher.hidden = false;
switcher.addEventListener('click', () => setLanguage(language === 'en' ? 'zh' : 'en'));
try { setLanguage(localStorage.getItem('agenticconsensus.website.language') === 'zh' ? 'zh' : 'en'); } catch { setLanguage('en'); }

const tabs = [...document.querySelectorAll('[role="tab"]')];
document.querySelector('.example-tabs').hidden = false;
function selectTab(tab, focus = false) {
  tabs.forEach(item => {
    const selected = item === tab;
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
    document.getElementById(item.dataset.panel).hidden = !selected;
  });
  if (focus) tab.focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', event => {
    let target;
    if (event.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
    if (event.key === 'ArrowLeft') target = tabs[(index - 1 + tabs.length) % tabs.length];
    if (event.key === 'Home') target = tabs[0];
    if (event.key === 'End') target = tabs[tabs.length - 1];
    if (target) { event.preventDefault(); selectTab(target, true); }
  });
});

const copy = document.getElementById('copy');
copy.hidden = false;
let copyTimer;
copy.addEventListener('click', async () => {
  const status = document.getElementById('copy-status');
  try {
    await navigator.clipboard.writeText(document.getElementById('install').textContent.trim());
    copy.textContent = language === 'zh' ? '已复制' : 'Copied';
    status.textContent = language === 'zh' ? '启动命令已复制' : 'Quick-start commands copied';
  } catch {
    const range = document.createRange();
    range.selectNodeContents(document.getElementById('install'));
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    status.textContent = language === 'zh' ? '命令已选中，请手动复制' : 'Commands selected; copy them manually';
  }
  clearTimeout(copyTimer);
  copyTimer = setTimeout(() => { copy.textContent = language === 'zh' ? chinese.copy : english.copy; status.textContent = ''; }, 3500);
});
