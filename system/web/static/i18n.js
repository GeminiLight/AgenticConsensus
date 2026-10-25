/* Explicit UI messages only. Never translate project records, code, or form values. */
(function(root){
  'use strict';
  const messages={
    'No reading':'尚无解读',
    'Selected interpretation':'已选解释',
    'Files without a reading':'尚未解读的文件',
    'No commitment linked':'尚未关联约定',
    'Draft commitment':'起草约定',
    'Configured checks passed.':'已通过配置的检查。',
    'Follow-up':'复审',
    'Approval requires all blocking checks to pass.':'处理全部阻碍项后才可批准。',
    'No outstanding evidence items':'没有待处理的证据事项',
    'Other checks need attention. Return to Decision.':'其他检查仍需处理，请返回决策页。',
    '{requirements} requirements · {findings} findings':'{requirements} 项要求 · {findings} 个问题',
    'Approval is recorded separately.':'批准需另行记录。',
    'No outstanding requirements.':'没有待处理的证据要求。',
    'No open findings.':'没有待处理的问题。',
    'Verification details':'验证详情',
    'Add commitment':'添加约定',
    'Proposed requirement':'拟议要求',
    'Proposed by {actor}':'提案人：{actor}',
    'Not analyzed':'尚未分析',
    'Advice from the request, source and checks. Approval remains yours.':'依据需求、源码和检查提供建议，由你决定是否批准。',
    'Analyze the current version for risks.':'分析当前版本的风险。',
    'Pending reviews':'待评审变更',
    'No reviews yet':'暂无评审',
    'Define the behavior this project must preserve.':'明确项目必须保持的行为。',
    'Implementation check':'实现检查',
    'Implementation':'实现',
    'Checked':'已检查',
    'Implementation ready for review':'实现已就绪，可以评审',
    'Open linked review':'打开关联评审',
    'Compare Python import changes.':'比较 Python 导入变更。',
    'Decision brief':'决策摘要',
    'Your decision':'你的决定',
    'Approval is blocked by a check. You can still request an update or reject.':'检查尚未通过，仍可请求修改或拒绝。',
    'Recorded as {authorities} under {policy}.':'以 {authorities} 身份，依据 {policy} 记录决定。',
    'Recorded under {policy}.':'依据 {policy} 记录决定。',
    'Rolling back restores the previous project state.':'回滚将恢复上一个项目状态。',
    'Define what this change must preserve':'明确这次变更必须保持什么',
    'Turn the request into a requirement you can check.':'将需求整理为可以检查的约定。',
    'Back to decision':'返回决策',
    'Inspect the records, then return to your decision.':'核对证据后，返回决策。',
    'Read the change alongside its findings.':'结合发现的问题，查看代码变更。',
    'Optional · not analyzed':'可选 · 尚未分析',
    'Advice available':'已有分析建议',
    'Analysis needs attention':'分析需要处理',
    'Review queue':'待评审变更',
    'Choose a change to review':'选择一个变更开始评审',
    'Start with a code change':'从代码变更开始',
    'Understand the change, check the evidence, then decide.':'理解变更，核对证据，再做决定。',
    'Choose a pull request or compare revisions to see what needs attention.':'选择拉取请求或比较版本，查看需要处理的问题。',
    'Project agreement':'项目约定',
    'What should stay true':'哪些约定必须保持',
    'A commitment records the behavior or boundary this project must preserve. Draft one from a review, then verify it before approval.':'约定记录项目必须保持的行为或边界。可以从评审中起草，并在批准前验证。',
    '{count} configured rules':'已配置 {count} 条规则',
    'All':'全部',
    'Update needed':'需要更新',
    'Open decision brief':'打开决策摘要',
    'Decided':'已决策',
    'Recorded check':'已记录的检查',
    'Review risks and sources':'查看风险与出处',
    'AI draft when available · local fallback · confirm before saving':'使用已配置的 AI 起草，失败时使用本地草稿；核对后再保存',
    'AI advice · not verification':'AI 建议 · 不代表验证通过',
    'AI analysis unavailable · local draft only':'AI 分析未完成 · 当前仅为本地草稿',
    'No model risk assessment was completed. Retry or inspect the source manually.':'本次没有完成模型风险分析。可以重试，或手动核对源码。',
    'High risk':'高风险','Medium risk':'中风险','Low risk':'低风险','Check next:':'建议验证：',
    'No specific risk identified in the supplied context. This is not a safety guarantee.':'在有限上下文中未识别到具体风险，但这不保证变更安全。',
    'AI risk analysis':'AI 风险分析','Analyzing risks…':'正在分析风险…','Analyze again':'重新分析','Analyze risks':'分析风险',
    'Uses the configured model with limited request, source and check records. Advice cannot approve a change.':'将有限的需求、源码和检查记录发送给已配置的模型。分析建议不能替代人工批准。',
    'Reading source and checks; your work stays editable…':'正在核对源码与检查记录，你仍可继续操作…',
    'Not analyzed · passing tests do not establish requirement coverage.':'尚未分析 · 测试通过不等于需求已被验证。',
    'Risk analysis failed. Your review is unchanged; retry when ready.':'风险分析失败，评审记录没有改变，可以稍后重试。',
    'This review has its own evidence and decision records. Previous-version notes remain historical.':'此轮评审有独立的证据与决定记录；上一版本的笔记仅作历史参考。',
    'Follow-up reviews':'后续复审',
    'The baseline has advanced. Start a new review against the current project version.':'项目基线已更新，请针对当前项目版本发起新的评审。',
    'Checks pass · requirements unverified':'检查通过，需求仍待验证',
    'Checks permit a decision · verification incomplete':'检查允许决策，但验证尚不完整',
    'Recorded requirements have evidence':'已记录的需求有对应证据',
    'Only the configured checks have passed. This is not a guarantee that the change meets every requirement.':'目前仅已配置的检查通过，不代表变更满足全部需求。',
    'Requirements still to verify':'还需要验证的需求',
    'No behavioral requirements are recorded.':'尚未记录需要验证的行为要求。',
    'Evidence covers the recorded requirements, not every possible risk.':'证据覆盖已记录的需求，并不排除所有风险。',
    'Your change intent has not yet been turned into a verifiable requirement.':'这次变更的需求尚未形成可验证的约定。',
    'Draft a verifiable commitment':'起草可验证的约定',
    'Draft from request and source':'根据需求与源码起草',
    'Local draft · review before saving · not verification':'本地草稿 · 确认后保存 · 不代表验证通过',
    'Drafting…':'正在起草…',
    'Reading the request and versioned source…':'正在读取需求与对应版本的源码…',
    'Draft ready · edit and confirm below':'草稿已填入，请在下方核对、修改并确认',
    'Your edits are kept. Review the new draft before replacing them.':'已保留你的编辑。请先查看新草稿，再决定是否替换。',
    'Use this draft':'使用这份草稿',
    'Sources and limitations':'出处与局限',
    'Draft unavailable. Your edits are kept; retry or continue manually.':'暂时无法起草。你的编辑已保留，可重试或继续手动填写。',
    'Revision history':'修订衔接',
    'Following up on the previous review':'继续上一轮评审',
    'Open previous review':'查看上一轮评审',
    'Requirements carried forward. Evidence and approval must be collected again for this target.':'约定已继承；这一版本需要重新提供证据并确认批准。',
    'Questions from the previous version · not current findings':'上一版本的问题与笔记 · 不代表当前检查结果',
    'Ready to review the fix?':'修改完成后，继续复审',
    'Choose the revised commit. Keep the request and requirements; do not start over.':'选择修改后的版本即可，需求和约定无需重新填写。',
    'Review revised version':'复审修改后的版本',
    'Open follow-up review':'查看后续复审',
    'Approval recorded':'这一版本已批准',
    'This version has an attributed approval. Inspect its evidence or start a new change.':'这一版本已记录批准及确认者，可以查看证据或发起下一项变更。',
    'Inspect recorded decision':'查看已记录的决定',
    'Enter the revised target before analyzing.':'请先填写修改后的目标版本。',
    'Relationship canvas':'关系画布','Workspace views':'工作区视图','History':'历史',
    'Read the implementation and its evidence':'核对实现与验证依据','Files linked to this commitment':'与此约定相关的文件',
    'Select a file to read its proposed changes.':'选择文件，在右侧核对本次变更。',
    'Review files':'本次评审文件','Linked files':'关联文件','File version':'文件版本','Find files…':'查找文件…',
    'Linked to this commitment':'与此约定关联','No files available':'暂无可查看文件',
    'Project snapshot unavailable':'项目快照暂不可用','Partial file list':'文件列表不完整',
    'Project baseline · opens in a separate reader':'项目基线版本 · 在独立阅读器中打开',
    'Proposed changes · linked files marked with a dot':'本次提议变更 · 圆点标记关联文件',
    'Focus reading':'专注阅读','Back to comparison':'返回对照',
    'The meaning is unchanged in this review.':'本次评审没有修改这一约定。',
    'Next step':'下一步','Review the changed baseline':'先核对已变化的基线','The project has advanced. Compare versions before continuing.':'项目已进入新版本，请先比较基线再继续。',
    'Current version':'当前版本','Decision history':'形成历史','Recheck existing commitments':'实现待复核','Check this version':'检查这一版实现','Resolve the source question':'先确认源码中的疑问','No assessment for this version':'这一版本尚无对应评估','Version {ref}':'版本 {ref}',
    'Recorded agreement':'约定形成时','Why this commitment':'为什么这样约定','Decision rationale':'决策理由','Agreed by {actor}':'确认者：{actor}',
    'This explains the agreement, not whether the current code still satisfies it.':'这里保留当初决定的依据；当前实现是否仍满足约定，需要另看对应版本的证据。',
    'Open original review':'打开原始评审','Agreement and implementation versions':'约定与实现的版本','No prior agreement':'尚无已确认约定','Proposed target':'本次提议版本','Evidence is version-bound':'证据与此版本对应','Not yet admitted':'尚未接受此变更',
    'An authored reading needs your attention. It is not an automated finding.':'作者标出了一处待确认问题，可直接查看对应源码。',
    'Inspect source':'查看源码','This commitment needs evidence for the selected version.':'需要为这一版本补充支持此约定的证据。',
    'An earlier agreement does not establish current behavior.':'此前确认过约定，不代表当前实现已得到验证。',
    'Refresh the evidence':'更新验证依据','Earlier evidence does not cover this version.':'已有证据未覆盖这一版本。','Resolve conflicting evidence':'检查证据冲突','Inspect the conflicting result before recording new evidence.':'先检查冲突结果，再决定如何补充证据。',
    'Review the recorded exception':'检查已记录的例外','An exception is not verification. Check its scope before deciding.':'例外不等于验证，请先核对其适用范围。',
    'Inspect current evidence':'查看当前验证依据','Review the decision':'检查并做出决定','Linked evidence is available. Approval remains a separate decision.':'已有关联证据，是否批准仍需单独决定。',
    'Checking records for this exact version.':'正在核对这一版本的记录。','Reload the evidence before relying on this state.':'请重新读取证据后再判断。',
    'Recheck':'待复核','The meaning is unchanged. Its implementation still needs review.':'约定未变，本次实现仍需评审。',
    'What should I inspect before approving?':'批准前，我应该检查什么？',
    'Remove the legacy billing dependency without changing how rates are calculated.':'移除旧的计费依赖，但保持费率计算方式不变。',
    'Preserve behavior, limit access, or follow an architectural decision. Include the context needed to interpret your request.':'说明需要保持的行为、访问限制或架构决定，并补充理解需求所需的背景。',
    'Must this migration preserve the current rate semantics?':'这次迁移是否必须保持现有的费率计算规则？',
    'Preserve rate semantics. We still need to check whether the adapter can remain.':'保持费率计算规则不变；还需要确认是否可以保留适配器。',
    'Why this interpretation is authorized to enter realization.':'说明为什么选择这一理解并授权进入实现。',
    'What should this change do, and what must stay true?':'这次变更要实现什么？什么必须保持不变？',
    'Why this decision is justified':'说明做出这一决定的依据',
    'What you checked, the observed result, and any limitations':'说明检查内容、观察到的结果，以及检查的局限',
    'Sections':'页面','Actions':'操作','Workspace':'工作区','Canvas':'画布','Layout':'布局','Appearance':'外观','External':'外部链接','Clipboard':'剪贴板','Import':'导入','Pull request':'拉取请求','Compare revisions':'比较版本','Register a local repository':'注册本地仓库','No matching command.':'没有匹配的操作。','Go to Decision':'前往决策','Go to Changes':'前往变更','Go to Evidence':'前往证据','Go to Audit':'前往审计','Approve and record this change':'批准并记录此变更','Request an update':'请求更新','Reject this change':'拒绝此变更','Configure and run tests':'配置并运行测试','Roll back the approval':'回退批准','Jump to a review, section, or action…':'查找评审、页面或操作…','Command palette':'快捷操作','Commands':'操作列表',
    'Current state':'当前共识','Current state\nVersion {version}':'当前共识\n版本 {version}','Attention first':'优先显示待处理项','Needs rebase':'需要更新基线','Project overview':'项目概览','Inspect evidence and open findings before recording a decision.':'记录决定前，请检查证据与待处理问题。','A review records a proposed transition, not a merge.':'评审记录拟议的状态变更，并不执行合并。','Locate on map →':'在图中定位 →','No reviews yet. Use New review to compare a change against this state.':'暂无评审。使用新建评审，比较相对当前状态的变更。','Clarify an ambiguous request before implementing it.':'实现前先澄清存在歧义的需求。','Find a change, request, or file…':'查找变更、需求或文件…','Zoom in':'放大','Zoom out':'缩小','Canvas zoom':'画布缩放','Show panel':'展开面板','Hide inspector':'隐藏详情','Hide review inspector':'隐藏评审详情',
    'proposes':'提出','changes':'变更','realizes':'实现','constrains':'约束','affects':'影响','contains':'包含','changes in':'变更位于','depends on':'依赖','governed by':'受约束于',
    'Evidence for this decision':'本次决策的证据','No outstanding evidence requirements or findings':'暂无待处理的证据要求或问题','{count} items need attention':'{count} 项需要关注','{requirements} evidence requirements and {findings} open findings. Passing tests alone do not clear these items.':'{requirements} 项证据要求，{findings} 个待处理问题。仅通过测试不能解决这些事项。','Evidence coverage is not approval. Check Decision for the full admission result.':'证据覆盖不等于批准。请在决策页查看完整的准入结果。','Back to Decision':'返回决策','To resolve':'待处理','Coverage':'覆盖情况','Evidence to collect':'待收集的证据','No outstanding evidence requirements. Review any findings below and check Decision before approving.':'暂无待补充的证据要求。批准前请检查下方问题与决策页。','Findings to review':'待评审的问题','No open findings were recorded. This does not establish evidence coverage.':'未记录待处理问题，但这不代表证据已充分覆盖。','Covered requirements':'已有证据覆盖的要求','Resolved or waived findings':'已解决或豁免的问题','Inspect what ran, what it established, and which revision it covers. A passing run can still be inconclusive.':'查看执行了什么、得出了什么，以及覆盖哪个版本。运行通过仍可能无法得出结论。','Search evidence records':'搜索证据记录','Find a record or source…':'查找记录或来源…','Filter evidence records':'筛选证据记录','All records':'全部记录','Needs attention':'需要关注','Refresh records':'刷新记录','The project rules this change affects. These observations are not automatically accepted changes to those rules.':'此变更影响的项目规则。这里的观察不代表规则变更已被接受。','No claim-level evidence obligation is declared for this proposal.':'此提案尚未声明规则级证据要求。',
    'Any authorized attestation source':'任何获授权的证明来源','No qualifying record supports this requirement for the target revision.':'目标版本尚无符合要求的记录支持此项要求。','Linked evidence is outdated or invalidated. Collect fresh evidence for the current target revision.':'关联证据已过期或失效，请为当前目标版本收集新证据。','Linked evidence conflicts with this requirement. Investigate the result before attaching new evidence.':'关联证据与此要求存在冲突，请先调查结果再附加新证据。','Qualifying evidence covers the target revision. This is not an approval of the review.':'符合要求的证据覆盖了目标版本，但不代表评审已获批准。','A time-limited waiver covers this requirement. It is not verified evidence.':'此要求目前有时限豁免，不等于已验证的证据。','Coverage status is unavailable. Refresh the review before relying on this requirement.':'无法获取覆盖状态，请刷新评审后再判断。','Coverage status is unavailable. Check Decision before continuing.':'覆盖状态不可用，请先检查决策页。','Signed verification':'签名验证','Authorized record':'授权记录','Requirement details':'要求详情','Requirement ID':'要求标识','Accepted source':'接受的来源','Exception policy':'例外策略','An authorized, bounded waiver is allowed.':'允许获得授权且范围受限的豁免。','Mandatory. A waiver is not allowed.':'强制要求，不允许豁免。','Evidence IDs':'证据标识','Waiver IDs':'豁免标识','View linked records':'查看关联记录','Satisfied':'已满足','Waived':'已豁免','Contested':'有争议','Needs disposition':'等待处理决定',
    'Approval is blocked by:':'批准前需要处理：','tests that have not run':'测试尚未运行','failing tests':'测试未通过','a stale base':'基线已过期','incomplete structure analysis':'结构分析未完成',
    'See the requirements and the records behind them.':'查看各项要求及其依据记录。','Inspect recorded decision':'查看决策记录','Inspect review history':'查看评审历史','Read proposed changes':'查看提议的变更','Inspect critical finding':'查看严重问题','Inspect evidence freshness':'查看证据是否有效','Inspect changed baseline':'查看基线变化','Inspect critical check':'查看关键检查','Inspect test result':'查看测试结果','Inspect structure check':'查看结构检查','Inspect overlapping proposal':'查看重叠提案','Inspect blocking check':'查看阻碍检查',
    'Structure checks inspect changed Python imports and configured project rules. Tests run only when a command is configured. This does not prove behavioral correctness or replace human review.':'结构检查针对变更中的 Python 导入和已配置规则。仅在配置命令后运行测试；这些检查不能证明全部行为正确，也不能替代人工评审。',
    'Request':'需求','Claims':'规则','Linked':'已关联','Summary only':'仅有摘要','Versioned intent map':'版本化的需求记录','No intent map linked':'未关联需求记录','Referenced in this review':'本评审引用的规则','None linked to this review':'未关联到本评审','Changed file':'变更文件','No records':'暂无记录','Tests not run':'测试未运行','Tests failed':'测试未通过','Inspect source records':'查看原始记录','Recorded':'已记录','Unattributed':'缺少责任主体','No final decision':'尚无最终决定','Inspect actor and rationale':'查看决策者与理由','No matching decision record':'无匹配的决策记录','partial':'部分',
    'Open the review workspace':'打开评审工作区','This file is the interface, not the running app. Open the local service to sign in and load your projects.':'这是界面文件，还不是运行中的应用。请打开本地服务，登录后加载项目。',
    'From the project folder, activate your Python environment and start the service:':'在项目目录中启用 Python 环境，然后启动服务：','Keep that terminal open, then use the button above. If you chose another port, open the address printed in the terminal.':'保持服务终端打开，再使用上方按钮。如果使用了其他端口，请打开终端中显示的地址。','JavaScript is required to use the workspace. Enable it, then reload the app’s address.':'工作区需要 JavaScript。请启用后重新加载。',
    'Select a pull request':'选择拉取请求','Its decision, blockers, evidence, and changed files will appear here.':'这里会显示决策、阻碍项、证据和文件变更。','Close inspector':'关闭详情','Assistant':'助手','Loading snapshot…':'正在加载快照…','Project snapshot':'项目快照','Then ask a question grounded in its evidence.':'随后可基于其中的证据提问。',
    'Project rules':'项目规则','What must stay true when code changes, and which evidence this project accepts.':'代码变化时必须保持什么，以及项目接受哪些证据。','Project governance':'项目治理','Governed claims':'受治理的规则','Evidence trust':'证据信任','Trusted signing keys':'受信任的签名密钥','Control which signed evidence this project can accept.':'管理此项目可以接受哪些签名证据。','Manage keys and history':'管理密钥与历史','Add trust root':'添加信任根','Trust history':'信任历史','Recorded events':'已记录的事件',
    'Compare Python import alternatives, clarify a choice, then review its implementation.':'比较 Python 导入替换方案，澄清选择，再评审实现。','No intent maps yet.':'暂无需求记录。','Agreed commitments and the changes awaiting a decision.':'查看已确认的约定与等待决策的变更。',
    'Find on canvas':'在画布中查找','Fit map':'适配画布','Hide panel':'收起面板','Drag to pan · + / − to zoom · 0 to fit. Select an object to inspect its relationships.':'拖动平移 · + / − 缩放 · 0 适配视图。选择对象查看关联。','Affected directories':'受影响的目录','View all':'查看全部','Shared state':'共同状态','State':'状态','Intent':'需求','Directory':'目录',
    'Review assistant':'评审助手','Advice, not approval. Inspect the sources before you decide.':'建议不等于批准。做决定前请核查来源。','Ask about this review, or start from a suggestion below.':'针对当前评审提问，或从下方建议开始。','What blocks approval?':'哪些问题阻碍批准？','Summarize risk':'总结风险','Find evidence gaps':'查找证据缺口','Your question':'你的问题','Answer options':'回答选项','Local records':'本地记录','A separate critique and synthesis use additional model calls and may take longer.':'独立复核与综合会增加模型调用，可能需要更长时间。','Ask assistant':'询问助手','Missing or stale records?':'记录缺失或已过期？','Find recorded gaps':'查看已记录的缺口','No model call. Lists next checks; does not run them.':'不调用模型。仅列出待检查项，不执行检查。','Project AI metrics':'项目 AI 指标','Inspect recorded run statistics':'查看运行统计','Recorded activity in this project':'项目中已记录的活动','Recent runs ·':'最近运行 ·','Grounding check rate':'依据检查比例','Citation ID match':'引用标识匹配率','Avg latency':'平均耗时','Feedback':'反馈','Includes local explanations and model runs. Matching a citation ID confirms a record exists, not that it supports the answer. These statistics are not independent proof of answer correctness.':'包括本地解释和模型运行。引用标识匹配仅说明记录存在，不代表它支持回答。这些统计不能独立证明回答正确。',
    'Decision provenance':'决策来源','Audit graph':'审计关系图','Trace this change from proposal and evidence to the recorded decision.':'追溯变更从提案、证据到决策记录的过程。','Graph':'关系图','Relation table':'关系表','Focus graph':'聚焦关系图','Download SVG':'下载 SVG','Decision trail':'决策链路','proposal → authority':'提案 → 授权','Evidence coverage':'证据覆盖','sources → claim':'来源 → 规则','Full contract':'完整关系','every relation':'全部关联','Find an element':'查找对象','Find':'查找','Press / to search':'按 / 搜索','Fit graph':'适配关系图','Follow proposal, authority, and disposition.':'追溯提案、授权与处理结果。','Proposal':'提案','Artifacts':'产物','Policy':'策略','Drag to pan · scroll or pinch to zoom · select an element for its relation path':'拖动平移 · 滚动或双指缩放 · 选择对象查看关联路径','supports':'支持','contests':'质疑','authorizes':'授权','governs':'约束','Selected element':'所选对象','Explore the decision path':'查看决策路径','Ready':'就绪','Show all':'显示全部','Select an element to isolate its immediate relations, status, and provenance.':'选择对象，聚焦它的直接关联、状态和来源。','Connected records':'关联记录','No element selected.':'尚未选择对象。',
    'Review a pull request':'评审拉取请求','Choose a repository and an open pull request to inspect its changes and evidence.':'选择仓库及未关闭的拉取请求，查看变更与证据。','Local path':'本地路径','Sign in with GitHub':'使用 GitHub 登录','Only repositories you explicitly grant are listed.':'仅显示你明确授权的仓库。','Connect GitHub':'连接 GitHub','Manage access':'管理访问权限','Disconnect':'断开连接','Retry connection check':'重新检查连接','Find repository':'查找仓库','Connect GitHub to load repositories.':'连接 GitHub 后加载仓库。','Repository':'仓库','Change':'更改','Choose an open pull request':'选择未关闭的拉取请求','Find pull request':'查找拉取请求','Select a repository first.':'请先选择仓库。','Absolute repository path':'仓库绝对路径','Display label':'显示名称','Optional':'可选','Used in exports instead of the local path.':'导出时用此名称代替本地路径。','Revision':'版本','Review settings':'评审设置','Defaults are ready; add tests or policy only when needed.':'默认设置已就绪，可按需添加测试或策略。','Defaults applied':'已使用默认设置','Project name':'项目名称','Test command':'测试命令','Quoted arguments are supported; commands never run through a shell.':'支持带引号的参数；命令不会通过 shell 执行。','Policy & access':'策略与访问','Secure defaults ready':'安全默认设置已就绪','Policy ID':'策略标识','Default authority':'默认授权主体','Authorized identities':'已授权身份','People allowed to record governed decisions.':'允许记录受治理决策的身份。','Structural claim':'结构规则','Claim title':'规则标题','Claim ID':'规则标识','Forbidden modules':'禁止的模块','Claim scope':'规则范围','Authority override':'自定义授权主体','Blank uses the project default.':'留空则使用项目默认值。','Evidence obligations':'证据要求','Signed CI evidence':'已签名的 CI 证据','Advanced · optional':'高级 · 可选','Pin an Ed25519 public key and require a DSSE-wrapped SLSA verification summary. Never paste a private key.':'指定 Ed25519 公钥，并要求以 DSSE 封装的 SLSA 验证摘要。请勿粘贴私钥。','Signed obligation label':'签名证据要求名称','Trusted key ID':'受信任密钥标识','Required verified level':'所需验证级别','Ed25519 public key · base64':'Ed25519 公钥 · base64','Verifier ID':'验证者标识','Resource URI prefix':'资源 URI 前缀','The target commit is appended and must match the signed VSA resource URI.':'将自动追加目标提交，且必须匹配签名 VSA 的资源 URI。','Choose a repository, then an open pull request':'先选择仓库，再选择未关闭的拉取请求','Read-only: Consensus cannot change or merge the PR.':'只读：系统无法修改或合并拉取请求。','Edit settings':'编辑设置','Check workspace':'检查工作区','Analyze PR':'分析拉取请求',
    'What should change?':'需要改变什么？','Start with the outcome and the constraints. Then compare interpretations before committing to one.':'先明确结果与约束，再比较不同理解，最后做出选择。','This workflow compares Python import replacements. Each request needs at least two alternatives.':'此流程用于比较 Python 导入替换方案。每条需求至少需要两个候选方案。','What do you want to change?':'你想改变什么？','What must stay true?':'什么必须保持不变？','Repository baseline':'仓库基线','Base revision':'基线版本','The current project revision is prefilled. Use another commit only if the request targets it.':'已填入项目当前版本，仅在需求针对其他提交时修改。','Check each alternative and keep unanswered questions visible. Recording these proposals does not resolve or select any of them.':'检查每个候选方案，并保留未回答的问题。记录提案不等于解决或选定方案。','Draft stays here while this page is open.':'页面保持打开时，草稿会保留。','Back to request':'返回需求','Draft with AI':'让 AI 起草','Write alternatives':'编写候选方案','Original request and constraints':'原始需求与约束','Review the latest version':'查看最新版本','Apply my edits to latest':'将我的修改应用到最新版本','Approach name':'方案名称','Why this approach?':'为什么采用此方案？','Proposed import change':'拟议的导入变更','Python file':'Python 文件','Repository-relative Python file. This edits the proposal, not the file.':'填写相对仓库的 Python 文件路径。此处编辑提案，不修改文件。','Current import':'当前导入','Replace with':'替换为','Open questions (optional)':'待澄清问题（可选）','One question per line. Keep unanswered questions; explain any removal below.':'每行一个问题。保留未回答的问题；如移除，请在下方说明。','Why are you making this change?':'为什么做此修改？','Recorded with your identity and the before/after versions.':'将记录你的身份与修改前后版本。','Compare proposed changes':'比较提议的变更','Draft stays here while this page is open. Nothing is selected or executed.':'页面打开期间保留草稿，不会选择或执行任何方案。','Review latest revision':'查看最新修订','Save proposal changes':'保存提案修改','Record a clarification':'记录澄清','An answer can resolve part of the request. Keep every interpretation that is still possible; mark only the questions this answer settles.':'回答可能只澄清部分需求。保留仍然可能的理解，仅标记此回答已解决的问题。','What did you ask?':'提出了什么问题？','What did you learn?':'得到什么信息？','Record clarification':'保存澄清','Human selection':'人工选择','Select structural proposal':'选择结构方案','This authorizes one interpretation for an isolated proposal. Other alternatives remain in the record as not selected. No files change until you run realization.':'此操作为独立提案选择一种理解。其他方案仍保留为未选定记录，执行实现前不会修改文件。','Selection rationale':'选择理由','Select candidate':'选择此方案',
    'Read snapshot file':'查看快照文件','Find in file':'在文件中查找','Previous':'上一个','Next':'下一个','Wrap lines':'自动换行','Retry file':'重新加载文件','Reload workspace':'重新加载工作区','Snapshot details':'快照详情','Close file':'关闭文件','Review a change':'评审变更','Choose the code to analyze. Nothing is merged.':'选择待分析的代码，不会合并任何内容。','GitHub pull request':'GitHub 拉取请求','Choose an open PR, inspect its changes and evidence.':'选择未关闭的拉取请求，查看变更与证据。','Local revisions':'本地版本','Compare a branch or commit in':'比较分支或提交，仓库：','Analysis prepares a review. An authorized person records the final decision.':'分析会创建评审，最终决定由获授权者记录。','Comparison details':'比较详情','Analyze a change against the project baseline. Both revisions resolve to commits; project tests run against the target. Nothing is merged.':'相对项目基线分析变更。两个版本均解析为提交，项目测试针对目标版本执行，不会合并代码。','A branch, tag or commit available in this repository.':'此仓库中可用的分支、标签或提交。','Change intent':'变更目的','Baseline and proposer':'基线与提议者','Prefilled from the governed project state; change it to compare another baseline.':'已按当前项目状态填入；如需比较其他基线，可修改。','Proposer':'提议者','The proposing person or agent. This label does not grant approval authority.':'提议变更的人或代理。此标签不赋予批准权限。','Use a GitHub pull request instead':'改用 GitHub 拉取请求','Review created':'评审已创建','The review is saved. Open it to continue; you do not need to analyze this change again.':'评审已保存。打开后继续，无需再次分析同一变更。','Start another comparison':'开始另一次比较','Discard draft':'丢弃草稿','Analyze change':'分析变更',
    'Resolve blocker':'处理阻碍项','Run target tests':'运行目标版本测试','The command runs without a shell against this review’s immutable target commit. A passing result replaces the missing test evidence.':'命令直接针对本评审不可变的目标提交执行，不经过 shell。通过后补充测试证据。','The exact command is recorded in the review audit trail.':'完整命令将记录在评审审计记录中。','Run tests':'运行测试','Human decision':'人工决策','Record decision':'记录决定','Decision identity:':'决策身份：','Governing policy':'适用策略','Asserted authority':'声明的授权主体','Bounded scope':'限定范围','Expires at':'到期时间','The waiver lapses automatically at this time and the finding reopens.':'豁免将在此时自动失效，相关问题重新打开。','Confirm decision':'确认决定','Attach an evidence record':'附加证据记录','Record a check you have already performed. Attaching evidence does not run tests or approve the review.':'记录已经完成的检查。附加证据不会执行测试，也不会批准评审。','Evidence recorder:':'证据记录者：','Evidence summary':'证据摘要','Describe the observation that supports this requirement. Do not claim a check passed unless it did.':'描述支持此要求的观察结果。检查未通过时，请勿声称通过。','Evidence source':'证据来源','Cite a retrievable run, report, or trace so another reviewer can verify the observation.':'引用可检索的运行、报告或记录，以便其他评审者核实。','Import signed verification':'导入签名验证','DSSE envelope file':'DSSE 封装文件','The file is read locally, then submitted as JSON for signature and policy verification.':'文件将在本地读取，再以 JSON 提交以验证签名和策略。','DSSE envelope JSON':'DSSE 封装 JSON','Verify and attach':'验证并附加',
    'Change attestation trust':'更改证明信任','Trust administrator:':'信任管理员：','Current key':'当前密钥','Key to replace or revoke':'待替换或撤销的密钥','Revocation mode':'撤销模式','Prospective · block future imports':'向后生效 · 阻止后续导入','Retroactive · invalidate prior evidence':'追溯生效 · 使此前证据失效','New key and possession proof':'新密钥与持有证明','New key ID':'新密钥标识','Evidence authority':'证据授权主体','Valid from':'生效时间','Valid until · optional':'失效时间 · 可选','Build signing template':'生成签名模板','Creates the exact DSSE payload for the external key to sign. It does not access a private key.':'生成供外部密钥签名的准确 DSSE 载荷，不访问私钥。','Build a template to see the required policy, verified level, target, and signing bytes.':'生成模板以查看所需策略、验证级别、目标和待签名字节。','DSSE PAE signing input · base64':'DSSE PAE 签名输入 · base64','Decode this value, sign the bytes with the new Ed25519 private key, then place the base64 signature in':'解码此值，用新的 Ed25519 私钥签名字节，再将 base64 签名放入','Copy signing input':'复制签名输入','Download signing package':'下载签名包','Signed proof file':'已签名的证明文件','A dedicated possession VSA signed by the new key and bound to the current governed head.':'由新密钥签名并绑定当前受治理版本的专用持有证明 VSA。','Signed proof JSON':'已签名的证明 JSON','Apply trust change':'应用信任变更',
    'Access control':'访问控制','Operator identities':'操作员身份','Global roles control console access. Project authority grants still decide who may attest, waive, commit, or manage trust.':'全局角色控制工作区访问，项目授权决定谁能出具证明、豁免、批准或管理信任。','Identity audit':'身份审计','Append only':'只追加记录','Add identity':'添加身份','Role':'角色','Viewer':'观察者','Administrator':'管理员','Account security':'账户安全','Change password':'修改密码','Confirm the current password. A successful change rotates this session and revokes every other session for your identity.':'请确认当前密码。修改成功后将更新本会话，并撤销该身份的其他会话。','Current password':'当前密码','Sign out other sessions':'退出其他会话','Keep this browser signed in.':'保持当前浏览器登录。','Administrator reset':'管理员重置','Issue temporary password':'设置临时密码','Reset':'重置','Confirm temporary password':'确认临时密码','Reset and revoke sessions':'重置并撤销会话','Keyboard':'键盘','Shortcuts':'快捷键','Open the command palette':'打开快捷操作','Next or previous review':'下一个或上一个评审','Decision, Changes, Evidence, Audit':'决策、变更、证据、审计','Search the audit graph':'搜索审计关系图','Ask the review assistant':'询问评审助手','Close menus, dialogs, and the inspector on narrow screens':'关闭菜单、对话框及窄屏详情面板','Show this list':'显示此列表',
    'Ready to approve':'可以批准','Update requested':'已请求更新','Approval rolled back':'批准已回退','Inspect missing evidence':'查看缺失证据','Checks passed':'检查已通过','Approval unavailable':'暂时无法批准','Recorded outcome':'已记录的结果',
    'Structure scope':'结构检查范围','Python files in this change':'个变更中的 Python 文件','linked rules':'条关联规则','Assessment details':'评估详情',
    'Explore the code changes':'查看代码变更','Request-to-decision links':'从需求到决策的关联','Inspect recorded correspondence':'查看已记录的对应关系','Policy checks':'策略检查',
    'Record approval':'记录批准','Resolve blocking checks before recording approval':'记录批准前，请先处理阻碍项','Open on GitHub':'在 GitHub 中打开','Open changed files':'查看变更文件','Ask AI about this review':'向 AI 询问此评审','More review actions':'更多评审操作','More actions':'更多操作','Copy review link':'复制评审链接','Refresh review summary':'刷新评审摘要','Refresh summary':'刷新摘要','Copy summary':'复制摘要','Export JSON':'导出 JSON','Source revisions':'源码版本','base':'基线','target':'目标',
    'Read-only access':'只读访问','You can inspect this review and its evidence, but only an operator can change the recorded decision.':'可以查看评审和证据，但只有操作员能更改决策记录。','Request update':'请求更新','Roll back approval':'回退批准','Recorded decision':'已记录的决定','Raw unified patch':'原始统一补丁','Open full diff':'查看完整变更','Governing claims':'适用规则','Review trace':'评审链路','Links recorded in this review':'本评审中记录的关联','No recorded events yet.':'暂无事件记录。',
    'Configured checks pass. Record your decision once you have read the change.':'配置的检查均已通过。阅读变更后，可以记录你的决定。','{count} blocking checks must be resolved first.':'需要先处理 {count} 项阻碍检查。','Tests have not run; {count} evidence records are missing.':'测试尚未运行；缺少 {count} 条证据。','{count} evidence records are missing.':'缺少 {count} 条证据。','{count} files changed':'{count} 个文件发生变更','{count} files · paths and change volume':'{count} 个文件 · 路径与变更量','{count} blocking checks':'{count} 项阻碍检查',
    'New operator · Identity boundary':'新操作员 · 身份边界','Identity boundary':'身份边界','Your name and audit identity will be recorded with the actions you take.':'你的姓名和审计身份将随操作一同记录。','Project permissions are assigned separately. Creating an account does not grant approval authority.':'项目权限单独分配，创建账户不赋予批准权限。','New here? Choose Sign up to create an account for this installation.':'首次使用？点击注册，为此工作区创建账户。','Use the account created for this installation. Need access? Ask the administrator who runs this workspace.':'请使用此工作区的账户登录。如需访问权限，请联系管理员。',
    'Draft a Python request':'起草 Python 需求','Create first request':'创建第一条需求','View existing reviews':'查看已有评审','Open reviews':'打开评审列表',
    'Project':'项目','Projects':'项目','Project state':'项目共识','Requests':'需求','Reviews':'评审','Rules':'规则',
    'Commitments':'约定','Relations':'关系图','New review':'新建评审','Jump to…':'快速跳转…',
    'Open review':'进入评审','Open project':'打开项目','Inspect rules':'查看规则','Describe commitment':'描述约定',
    'Awaiting agreement':'待确认','Agreed state':'已达成的共识','Proposed':'提案','Agreed':'已确认','Draft':'草稿',
    'Interface':'接口','Behavior':'行为','Compatibility':'兼容性','Dependency':'依赖','Authority':'权限',
    'Meaning across the implementation':'约定与实现的对应关系','What we propose to agree':'待确认的共同约定','What is currently agreed':'当前共同约定',
    'Question to resolve':'待讨论的问题','Context':'相关实现','Consistent reading':'解读一致','Not interpreted':'尚未解读',
    'Author-raised question':'作者提出的疑问','Authored source reading':'作者的源码解读','Source reading · not verification':'源码解读 · 不等于验证',
    'Read rationale':'查看理由','Shared meaning':'共同约定','Source correspondence':'实现对照','Behavioral evidence':'行为验证',
    'Not interpreted yet':'尚未解读','Reading evidence…':'正在读取证据…','Inspection unavailable':'暂时无法查看',
    'Needs verification':'待验证','Verification outdated':'验证已过期','Conflicting evidence':'证据存在冲突','Exception recorded':'已记录例外',
    'Evidence attached':'已附证据','Not assessed':'尚未评估','Rationale & original request':'理由与原始需求',
    'Previously agreed':'此前约定','Author’s reasoning':'作者的判断依据','Original request':'原始需求','Recorded by {actor}':'记录者：{actor}',
    'Changes & source':'变更与源码','Human agreement is still required.':'仍需人工确认。','Authorized state · evidence remains inspectable.':'已授权的共识 · 可继续查看证据。',
    'Revise interpretation':'修订约定','Only an authorized decision changes the shared state.':'只有获得授权的决定，才会更新共同约定。',
    'Source':'源码','Evidence':'证据','Refresh source and evidence':'刷新源码与证据','Close inspection':'关闭详情','Inspection':'查看详情',
    'Inspect the selected commitment':'查看当前约定','Source-to-meaning correspondence':'约定与源码的对应关系',
    'Interpretation, correspondence and verification':'约定、实现对照与验证','Project meaning workspace':'项目共识工作区',
    'Select a commitment':'选择约定','Describe a commitment':'描述约定','Find in this patch…':'在此变更中查找…','Find in this patch':'在此变更中查找',
    'Captured excerpt':'已记录的源码片段','Open full review diff':'查看完整变更','Selected file patch':'所选文件的变更',
    'Repository root':'仓库根目录','No patch':'无变更片段','Verification plan':'验证计划','Not a test result':'并非测试结果',
    'Attached evidence':'已关联的证据','Open verification':'进入验证','Reading the review snapshot…':'正在读取评审快照…',
    'Couldn’t load inspection':'无法加载详情','Try again':'重试','Partial patch · search covers displayed lines only.':'仅显示部分变更 · 搜索范围限于已显示的代码。',
    'No patch is available for this file in this review.':'此评审没有该文件的变更片段。','Binary file · text cannot be displayed.':'二进制文件 · 无法显示为文本。',
    'No evidence is linked to this commitment. Code changes alone do not verify the behavior.':'尚无证据关联到此约定。代码发生变化，不代表行为已经得到验证。',
    'No review is linked to this commitment. Evidence cannot be inferred from its approved status.':'此约定未关联评审，不能仅凭已批准状态推断验证结果。',
    'This file is linked, but no source reading has been recorded.':'文件已关联，但尚未记录它如何实现这条约定。',
    'No rationale linked to the available record.':'当前记录未提供判断依据。','The original request is not linked in the available records.':'当前记录未关联原始需求。',
    'Unknown':'未知','Recorded snapshot':'已记录的快照','Meaning of this change':'这次变更意味着什么','Project commitments':'项目约定',
    'What should this change mean?':'这次变更应该实现什么？','Request & interpretation':'需求与解读','Agreed at baseline':'基线中的约定',
    'No prior commitment recorded':'尚未记录此前约定','Accepted in this review':'本次评审已接受','Proposed interpretation':'提议的约定','Must remain true':'必须保持不变',
    'Inspect verification':'查看验证','Edit proposal':'编辑提案','Propose revision':'提出修订','To verify':'验证方式',
    'Interpret the request':'理解需求','State the behavior or boundary being agreed.':'明确需要共同确认的行为或边界。',
    'Connect the implementation':'关联实现','Link the files that carry that commitment.':'关联实现这条约定的文件。',
    'Define the evidence':'明确证据','Make clear what must be checked before acceptance.':'明确接受变更前需要验证什么。',
    'No agreed commitments yet':'尚未达成共同约定','Start with one concrete behavior or boundary. Once its proposal is approved, it belongs here.':'从一条具体行为或边界开始。提案获批后，会显示在这里。',
    'Describe the first commitment':'描述第一条约定','Proposed changes':'待确认的变更','Not yet part of the agreed state':'尚未纳入共同约定',
    'No commitment proposals awaiting approval.':'暂无待批准的约定提案。','Changes to interpret':'待解读的变更',
    'Unmapped changes':'未关联的变更','No commitment is linked yet.':'尚未关联到具体约定。',
    'Linked to: {title}':'关联约定：{title}',
    'Open reviews: {count} · Agreed commitments: {agreed}':'进行中评审 {count} · 已确认约定 {agreed}',
    'Show all records':'显示全部记录','Waive':'申请豁免',
    '{count} requirement':'{count} 项要求','{count} requirements':'{count} 项要求',
    '{count} finding':'{count} 个问题','{count} findings':'{count} 个问题',
    'Cite a retrievable run, report, or trace. The source must start with {prefix}.':'请引用可追溯的运行记录、报告或日志。来源必须以 {prefix} 开头。',
    'These reviews have code changes, but no proposed commitment yet.':'这些评审包含代码变更，但尚未描述相应约定。',
    'Inspect what this change means':'查看这次变更的含义','Start a change':'发起变更','Files & verification':'文件与验证','New commitment':'新约定','Revise commitment':'修订约定',
    'Review the interpretation & evidence':'评审解读与证据','Revise the proposed commitment':'修订约定提案','Describe a project commitment':'描述项目约定',
    'Commitment title':'约定标题','Kind':'类型','Our proposed interpretation':'我们提议的约定','Why this interpretation?':'为什么这样理解？',
    'Files carrying this commitment':'承载此约定的文件','Source readings':'源码解读','Optional · interpretations, not test evidence':'可选 · 解读并非测试证据',
    'Connect a short interpretation to 1–12 lines in the target snapshot. The server captures the actual source; these notes do not satisfy verification.':'为目标版本中的 1–12 行源码记录简短解读。系统会保存真实代码片段；这些笔记不作为验证证据。',
    'Add source reading':'添加源码解读','How will we verify it?':'如何验证？','Recorded as an evidence requirement for this target revision. Saving a proposal does not verify it.':'将作为当前目标版本的证据要求。保存提案不代表验证通过。',
    'The agreed project state changes only after authorized approval.':'只有获得授权批准，项目共识才会更新。','Close draft':'关闭草稿','Save proposal':'保存提案','Reload & keep draft':'重新加载并保留草稿',
    'Source interpretation':'源码解读','Label':'标题','Relationship':'对应关系','Remove this source reading':'移除此条源码解读','File':'文件','First line':'起始行','Last line':'结束行','What does this code mean?':'这段代码表达了什么？',
    'A short name for the agreement':'为约定起一个简短名称','What did the person ask for?':'原始需求是什么？','What exactly should remain true or become true?':'具体需要保持或实现什么？',
    'Record the choice and the reasoning behind it.':'记录这一选择及其依据。','Which observation or check would support this exact statement?':'什么观察或检查能够支持这条具体约定？','e.g. Generation service':'例如：生成服务',
    'Close proposal':'关闭提案','Saving proposal…':'正在保存提案…','Commitment proposed — verification and approval remain separate':'提案已保存，仍需分别完成验证和批准',
    'Select at least one file that carries this commitment.':'请至少选择一个实现此约定的文件。','A proposal can include up to 12 source readings.':'每个提案最多添加 12 条源码解读。',
    'Loading reviews and requests…':'正在加载评审与需求…','Project context is unavailable. Retry below.':'无法加载项目上下文，请在下方重试。',
    'No open reviews. Start with a pull request or compare local revisions.':'暂无进行中的评审。可以导入拉取请求，或比较本地版本。',
    '{count} open reviews · {attention} need attention. Inspect evidence before approval.':'{count} 个进行中的评审 · {attention} 个需要关注。批准前请查看证据。',
    '{count} linked files':'关联 {count} 个文件','{count} files':'{count} 个文件','{count} question raised':'{count} 个待讨论问题','{count} authored readings':'{count} 条源码解读',
    '{count} linked evidence records':'{count} 条关联证据','{count} agreed · version {version}':'已确认 {count} 条 · 版本 {version}',
    'Commitment {index} / {total}':'约定 {index} / {total}','Target {ref} · read-only patch':'目标版本 {ref} · 只读变更',
    '{count} review-level approval blockers':'评审中有 {count} 项批准前置条件未满足','{count} matching lines':'找到 {count} 行',
    'Account':'账户','Account access':'账户访问','Sign in':'登录','Sign up':'注册','Sign out':'退出登录','Username':'用户名','Password':'密码',
    'Audit identity':'审计身份','Confirm password':'确认密码','Sign in to your workspace':'登录工作区','Create your account':'创建账户',
    'Review proposed changes, trace the evidence, and record your decision.':'查看变更提案、追溯证据，并记录你的决定。','Use the account created for this installation.':'请使用此工作区的账户登录。',
    'Create first administrator':'创建首位管理员','Create operator account':'创建操作员账户','Operator':'操作员','Temporary password':'临时密码','New password':'新密码','Confirm new password':'确认新密码','Set new password':'设置新密码',
    'Use the exact identity named in project authority grants.':'请使用项目授权记录中的准确身份。','This identity is recorded on governed actions.':'此身份将记录在需要授权的操作中。',
    'Registration grants console access, not project authority.':'注册后可访问工作区，但不会自动获得项目授权。','About accounts and permissions':'关于账户与权限',
    'Project permissions govern who can approve, waive, or provide evidence. An account alone does not grant that authority.':'项目权限决定谁能批准、豁免或提供证据。拥有账户不等于获得这些权限。',
    'Passwords are hashed with Argon2id. Sessions stay server-side and expire automatically.':'密码使用 Argon2id 哈希保存，会话保存在服务端并自动过期。',
    'Opening your workspace':'正在打开工作区','Connecting to this service and checking your session…':'正在连接服务并检查登录状态…','Reload page':'重新加载','Open local app':'打开本地应用','If the app doesn’t open':'如果应用无法打开',
    'Skip to review workspace':'跳转到评审工作区','Service status':'服务状态','Switch project':'切换项目','Active project':'当前项目','No project':'暂无项目','Project views':'项目视图',
    'Open command palette':'打开快捷操作','Show review inspector':'显示评审详情','Show inspector':'显示详情','Inspector':'详情','Import status':'导入状态','Status':'状态','Account actions':'账户操作',
    'GitHub repositories':'GitHub 仓库','Keyboard shortcuts':'键盘快捷键','Presentation view':'演示视图','Exit presentation view':'退出演示视图','Users':'用户',
    'Switch to dark theme':'切换为深色外观','Switch to light theme':'切换为浅色外观','Switch to dark':'切换深色','Switch to light':'切换浅色','Open account menu':'打开账户菜单',
    'Language':'语言','Switch language':'切换语言','Pull request review':'拉取请求评审','Decide what is safe to merge.':'判断哪些变更可以安全合入。',
    'Open a pull request to see the blocking checks, supporting evidence, changed files, and the next action in one place.':'打开拉取请求，在同一处查看阻碍项、支持证据、文件变更和下一步操作。',
    'Analyze a GitHub pull request':'分析 GitHub 拉取请求','Use a local repository':'使用本地仓库',
    'GitHub access is read-only. This workspace records review decisions; it never merges code on your behalf.':'GitHub 访问为只读。工作区记录评审决定，不会代你合并代码。',
    'Compare two revisions':'比较两个版本','Switch review':'切换评审','Filter reviews':'筛选评审','Clear':'清除','Clear review filter':'清除评审筛选','Pull request reviews':'拉取请求评审',
    'Decision':'决策','Changes':'变更','Audit':'审计','Files':'文件','Ask AI':'询问 AI','Overview':'概览','Details':'详情','Summary':'摘要','Requirements':'要求','Records':'记录',
    'Review next change':'评审下一项变更','Group files':'按目录分组','Show files':'展开文件','Fit to view':'适配视图','Search project':'搜索项目','Search':'搜索','Clear search':'清除搜索','Project canvas':'项目画布',
    'Focus':'聚焦','Whole project':'整个项目','Directories':'目录','All files':'全部文件','No matching files':'没有匹配的文件','Open':'进行中','Approved':'已批准','Rejected':'已拒绝','Rolled back':'已回退','Pending':'待处理',
    'No governed claims':'尚未配置受治理的规则','Claims are declared when a repository is registered. Existing checks and decisions are available in its reviews.':'规则在注册仓库时声明。已有检查与决定可在评审中查看。',
    'Inspect existing reviews':'查看已有评审','Claim':'规则','Versioned evidence':'版本绑定的证据','Authorized decision':'获得授权的决定','Record structure · no claims configured yet':'记录结构 · 尚未配置规则',
    'Describe':'描述','Compare':'比较','Select & review':'选择并评审','State the import change and what must stay true.':'描述导入变更，以及必须保持不变的行为。',
    'Inspect alternative replacements and open questions.':'比较替换方案与待澄清问题。','Record a choice, then inspect its implementation.':'记录选择，再检查具体实现。',
    'Start with a code review':'从代码评审开始','Clarify the change before implementation':'实现前先澄清需求',
    'No Python files were found in this project snapshot. Requests currently handles Python import replacements. Use Reviews to inspect this project’s existing changes and evidence.':'此项目快照中未发现 Python 文件。需求模块目前支持 Python 导入替换；可以前往评审，查看已有变更与证据。',
    'No requests are recorded yet. Describe a Python import change and compare alternatives before selecting an approach.':'尚未记录需求。描述 Python 导入变更，比较候选方案后再做选择。',
    'New request':'新建需求','View reviews':'查看评审','No requests yet':'暂无需求','Describe a request':'描述需求',
    'Close':'关闭','Cancel':'取消','Save':'保存','Continue':'继续','Back':'返回','Retry':'重试','Refresh':'刷新','Reload':'重新加载','Loading…':'正在加载…','Copy':'复制','Copied':'已复制',
    'Before':'变更前','After':'变更后','Reason':'理由','Author':'作者','Action':'操作','View':'查看','Target':'目标','Baseline':'基线','Current':'当前','Not run':'未执行','Pass':'通过','Fail':'失败','Missing':'缺失','Stale':'已过期',
    'Read-only':'只读','Review':'评审','Selected':'已选择','Select':'选择','Approve':'批准','Reject':'拒绝','Rollback':'回退','Approved change':'已批准的变更',
    'Decision options':'决策选项','Inspect missing evidence':'查看缺失证据','Copy review brief':'复制评审摘要','Not ready to approve':'尚不满足批准条件','Ready for decision':'可以做出决定',
    'Attach evidence':'附加证据','Verification':'验证','Source records':'原始记录','Supporting evidence':'支持证据','Changed files':'变更文件','Checks':'检查','Findings':'发现的问题',
    'This review':'当前评审','Review context':'评审上下文','Target revision':'目标版本','Source readings are interpretations, not evidence.':'源码解读不等于验证证据。',
    'just now':'刚刚','Untitled change':'未命名变更','No project selected':'未选择项目','Choose a project':'选择项目','Empty':'暂无内容',
  };
  const storageKey='agentic-consensus-language';
  let language=root.document?.documentElement?.dataset?.defaultLanguage==='en'?'en':'zh-CN';try{const saved=root.localStorage?.getItem(storageKey);if(saved==='en'||saved==='zh-CN')language=saved;}catch{}
  const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const encode=value=>encodeURIComponent(value).replace(/'/g,'%27');
  const decode=value=>{try{return decodeURIComponent(value);}catch{return value;}};
  const quantities={'file':'个文件','linked file':'个关联文件','changed file':'个变更文件','blocking check':'项阻碍检查','missing evidence record':'条缺失证据','open critical finding':'个未解决的严重问题','record':'条记录','event':'个事件','claim':'条规则','requirement':'项要求','directory':'个目录','finding':'个问题'};
  function translated(key){
    if(Object.hasOwn(messages,key))return messages[key];
    let match=key.match(/^(\d+) missing evidence records?$/);if(match)return `缺少 ${match[1]} 条证据`;
    match=key.match(/^(\d+) (year|month|week|day|hour|minute)s? ago$/);if(match)return `${match[1]} ${({year:'年',month:'个月',week:'周',day:'天',hour:'小时',minute:'分钟'})[match[2]]}前`;
    match=key.match(/^(\d+) (.+?)s?$/);if(match){const unit=quantities[match[2]]||quantities[match[2].replace(/s$/,'')];if(unit)return `${match[1]} ${unit}`;}
    return key;
  }
  function t(key,params={}){const source=String(key??'');let value=language==='zh-CN'?translated(source):source;
    if(language==='en'&&Number(params.count)===1)value=({'{count} files':'{count} file','{count} linked files':'{count} linked file','{count} authored readings':'{count} authored reading','{count} linked evidence records':'{count} linked evidence record','{count} matching lines':'{count} matching line','{count} configured rules':'{count} configured rule','{count} files changed':'{count} file changed','{count} blocking checks':'{count} blocking check','{count} items need attention':'{count} item needs attention'})[source]||value;
    if(language==='en'&&source==='{requirements} requirements · {findings} findings') {
      if(Number(params.requirements)===1)value=value.replace(' requirements',' requirement');
      if(Number(params.findings)===1)value=value.replace(' findings',' finding');
    }
    return value.replace(/\{(\w+)\}/g,(match,name)=>Object.hasOwn(params,name)?String(params[name]):match);
  }
  function mark(key,params={}){return `<span data-i18n="${encode(key)}" data-i18n-params="${escape(JSON.stringify(params))}">${escape(t(key,params))}</span>`;}
  function canvasLabel(data){
    const label=data.label||'';if(language==='en')return label;
    if(data.type==='state'){const match=label.match(/^Current state\nVersion (\d+)$/);return match?t('Current state\nVersion {version}',{version:match[1]}):label;}
    if(data.type==='review'){const split=label.indexOf('\n');return split<0?label:t(({open:'Open',committed:'Approved',rejected:'Rejected',rolled_back:'Rolled back',rebase_required:'Update requested'})[data.status]||label.slice(0,split))+label.slice(split);}
    if(data.type==='intent'&&label.startsWith('Intent\n'))return t('Intent')+label.slice(6);
    if(data.type==='directory'&&Array.isArray(data.paths))return (data.directory==='Repository root'?t('Repository root'):data.directory)+'\n'+t(`${data.paths.length} changed files`);
    return label;
  }
  const attributes=['placeholder','aria-label','title','data-tooltip'];
  const selector=['[data-i18n]',...attributes.map(a=>`[data-i18n-${a}]`),'[data-language-switch]'].join(',');
  const rendered=new WeakMap();
  function paint(node){
    if(node.closest('[data-no-i18n],pre,code,script,style'))return;
    // Form hints are UI; the input/textarea content itself is always user data.
    if(node.hasAttribute('data-i18n')&&!node.matches('input,textarea')){
      const key=decode(node.dataset.i18n),previous=rendered.get(node);let params={};try{params=JSON.parse(node.dataset.i18nParams||'{}');}catch{}
      const value=t(key,params);
      // A renderer can replace a placeholder with project content. Do not restore
      // its former UI label over that new content.
      if(previous&&previous.key===key&&node.textContent!==previous.value&&node.textContent!==key){node.removeAttribute('data-i18n');rendered.delete(node);}
      else{if(node.textContent!==value)node.textContent=value;rendered.set(node,{key,value});}
    }
    for(const attr of attributes){const key=node.getAttribute('data-i18n-'+attr);if(key!==null){const value=t(decode(key));if(node.getAttribute(attr)!==value)node.setAttribute(attr,value);}}
    if(node.hasAttribute('data-language-switch')){const label=language==='zh-CN'?'EN':'ZH',hint=language==='zh-CN'?'Switch to English':'Switch to Chinese';if(node.textContent!==label)node.textContent=label;if(node.getAttribute('aria-label')!==hint)node.setAttribute('aria-label',hint);if(node.getAttribute('title')!==hint)node.setAttribute('title',hint);}
  }
  function apply(scope=root.document){if(!scope)return;if(scope.matches?.(selector))paint(scope);scope.querySelectorAll?.(selector).forEach(paint);}
  function setText(node,key,params={}){if(!node)return;node.dataset.i18n=encode(key);node.dataset.i18nParams=JSON.stringify(params);rendered.delete(node);paint(node);}
  function setAttribute(node,attr,key){if(!node)return;node.setAttribute('data-i18n-'+attr,encode(key));paint(node);}
  function setLanguage(value){language=value==='en'?'en':'zh-CN';try{root.localStorage?.setItem(storageKey,language);}catch{}if(root.document){root.document.documentElement.lang=language;apply();root.document.dispatchEvent(new CustomEvent('languagechange',{detail:{language}}));}return language;}
  const api={get language(){return language;},messages,t,mark,apply,setText,setAttribute,setLanguage,canvasLabel};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.I18n=api;
  if(root.document){
    root.document.documentElement.lang=language;
    const init=()=>{
      root.document.querySelectorAll('dialog .dialog-head').forEach(head=>{
        const close=head.querySelector('[data-close-dialog]');
        if(!close||head.querySelector('[data-language-switch]'))return;
        let heading=head.querySelector(':scope > div');
        if(!heading){
          const title=head.querySelector(':scope > h2');
          if(!title)return;
          heading=root.document.createElement('div');head.insertBefore(heading,title);heading.append(title);
        }
        heading.classList.add('dialog-heading');
        const controls=root.document.createElement('div');controls.className='dialog-tools';
        const button=root.document.createElement('button');button.type='button';button.className='language-button';button.dataset.languageSwitch='';
        controls.append(button,close);head.append(controls);
        // Supporting context should not compete with title controls for line width.
        heading.querySelectorAll(':scope > p:not(.eyebrow)').forEach(description=>{
          description.dataset.dialogDescription='';head.append(description);
        });
      });
      apply();
      root.document.addEventListener('click',event=>{if(event.target.closest('[data-language-switch]'))setLanguage(language==='zh-CN'?'en':'zh-CN');});
      const observer=new MutationObserver(records=>{const scopes=new Set();for(const record of records){if(record.type==='attributes'||record.type==='characterData')scopes.add(record.target.nodeType===3?record.target.parentElement:record.target);else{scopes.add(record.target);for(const node of record.addedNodes)if(node.nodeType===1)scopes.add(node);}}for(const scope of scopes)apply(scope);});
      observer.observe(root.document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['data-i18n','data-i18n-params',...attributes.map(a=>'data-i18n-'+a)]});
    };
    if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',init);else init();
  }
})(typeof globalThis!=='undefined'?globalThis:this);
