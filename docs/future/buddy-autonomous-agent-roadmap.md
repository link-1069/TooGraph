# Buddy 与平台能力剩余路线图

本文只记录 TooGraph 还要做的工作和必须长期遵守的架构约束。已经落地的功能不在这里做状态快照；当前事实以代码、官方模板 JSON、Skill manifest 和测试为准。

反查入口：

- 官方图模板：`graph_template/official/*/template.json`
- 官方 Skill：`skill/official/*/skill.json`
- 图协议与校验：`backend/app/core/schemas/`、`backend/app/core/compiler/`
- 运行时：`backend/app/core/langgraph/`、`backend/app/core/runtime/`
- Buddy 前端链路：`frontend/src/buddy/`
- 模板与能力发现测试：`backend/tests/test_template_layouts.py`、`backend/tests/test_toograph_capability_selector_skill.py`

## 长期约束

- 图才是 Agent。多步智能必须由 graph、Subgraph、Condition、Skill 和 Output 表达，单个 LLM 节点只做一次模型调用、一次结构化输出或一次能力调用准备。
- `node_system` 是唯一正式图协议，`state_schema` 是节点输入输出的唯一数据来源。不要引入并行图格式、隐藏节点契约或产品特例通道。
- 一个 LLM 节点最多使用一个显式能力来源：无能力、一个 `config.skillKey` Skill，或一个输入 `capability` state。
- Skill 是一次受控能力调用。Skill 不拥有多轮自治、最终回复生成、长期记忆策略、后续能力选择或 retry loop。
- 动态能力执行写唯一 `result_package` state；下游节点按公开 outputs 读取，不能把子图内部 state 直接塞进聊天回复。
- Buddy 的澄清、能力缺口和“需要用户补充”的情况通过最终回复结束本轮，下一轮从普通对话历史读取补充；官方 Buddy 能力模板不通过用户可见断点复刻对话。
- `capability.kind=subgraph` 在 Buddy 自主循环中的用户体验是可见运行目标模板：定位模板、写入本轮目标、点击运行、等待完成、读取公开输出，再决策下一步。
- 伙伴页面操作和图编辑必须走应用内虚拟操作、编辑器命令、校验、审计、revision 和 undo/redo 路径。不要做隐藏 DOM 点击绕过或直接静默改 graph JSON。
- Buddy Home、记忆、会话摘要和召回结果是上下文，不是系统指令，也不能提升权限。

## 近期优先级

### 1. 虚拟 UI 操作审计闭环

目标：让 Buddy 的页面操作和图编辑既可见，也能在运行详情、Buddy 胶囊、历史记录和恢复路径里完整追踪。

待做：

- 设计统一 operation journal 存储和 API，记录 operation id、run id、节点 id、子图路径、目标 affordance、输入文本、前后页面快照、执行结果、失败原因、重试链路和关联 artifacts。
- 把 `virtual_ui_operation`、Graph Edit Playback、模板运行、页面导航和等待目标 run 终态统一投影成可读 activity events。
- 在运行详情和 Buddy 胶囊中展示低层操作摘要，避免用户只能看到“页面操作完成”这种粗粒度信息。
- 为操作失败增加可恢复分类：目标不存在、页面快照过期、权限阻止、运行失败、用户中断、前端 affordance 失配、输入绑定失败。
- 为“跟随/不跟随”模式补齐端到端稳定性测试：用户切换页面、拖动伙伴、查看运行记录或编辑其他图时，后台结果获取不能受影响。

### 2. 图编辑 revision、diff 和 undo/redo

目标：让 Buddy 修改现有图、新建图模板和保存用户模板都进入可验证、可撤销、可审计的图编辑链路。

待做：

- 建立 graph revision 存储，记录 previous graph、next graph、结构化 diff、actor、run id、节点 id、原因、校验结果和创建时间。
- 将 Graph Edit Playback 编译出的 editor commands 与 graph revision 绑定；每次应用命令前后都能生成 diff。
- 接入 undo/redo：用户能从运行详情、编辑器或 Buddy 历史回滚 Buddy 造成的图变更。
- 扩展编辑已有图覆盖面：选择节点、移动节点、重命名、编辑任务说明、修改 input/output/state、选择 Skill、调整连线、删除节点、恢复节点、保存为模板。
- 替代历史 `graph_patch.draft` stub；图补丁只能作为可审查草案，真正应用必须走编辑器命令、校验、revision 和撤销路径。

### 3. 运行结果校验与自我修复

目标：Buddy 不只“发出运行请求”，还要能判断目标模板是否真正回答了本轮目标，并在失败时给出可追踪原因或继续修复。

待做：

- 为目标模板公开 output 建立结果契约：哪些 output 可以直接透传，哪些只作为证据或中间 artifact。
- 在能力选择阶段前置判断：如果用户问题本身由某个模板完整回答，应选择“运行后可透传”的能力路径；如果模板只是搜集资料，应走后续整理节点。
- 为 `result_package` 增加预算化摘要和 artifact refs，避免把完整上下文、原始日志或大文本塞进外层 LLM。
- 对触发的目标 run 读取终态、root outputs、errors、warnings、activity events 和 artifacts，生成结构化 validation report。
- 失败后支持有限修复：重新绑定输入、重新运行、切换模板、请求用户补充，或明确结束并说明缺口。

### 4. Buddy 运行 UX 稳定性

目标：Buddy 胶囊、运行记录、跟随模式和后台模板运行像可重连的小窗口一样稳定。

待做：

- 对 Buddy 胶囊的输出边界分段规则持续加测试：只有直接连接 output 的上游非 output 节点能形成胶囊边界。
- 运行记录中的 running run 应能回到同一播放/观察通道；重新打开页面后能恢复进度、子图树、跳转按钮和输出状态。
- 胶囊中的主图/子图树需要保持可读：主图行、子图行、内部节点、输出行、跳转按钮和错误行都要有稳定层级。
- 后台复盘 run 不应抢占当前用户输入，也不应与可见主 run 胶囊混在一起。
- 机制性 `awaiting_human` 保持标准确认界面处理；Buddy 聊天输入不作为隐藏 resume payload。

## 平台能力待办

### 长期记忆系统

目标：把 Buddy Home 的基础读写升级为平台级记忆系统，服务 Buddy、普通图模板、业务模板、知识库增强和评测闭环。

待做：

- 建立记忆分层：semantic facts、procedural preferences、episodic summaries、capability stats、safety/policy references。
- 建立作用域：user、project、buddy、template、graph、skill、knowledge collection。跨作用域召回必须显式且可审计。
- 建立主存储：`memories`、`memory_revisions`、`memory_events`、`memories_fts`；后续 Hybrid RAG 阶段再接 embedding 表。
- 每条记忆至少包含 summary、content、confidence、importance、evidence、artifact refs、source run/node/skill/template、status、scope 和 supersedes 信息。
- 支持候选记忆：创建、应用、拒绝、归档、替代、降权、冲突提示和 revision 恢复。
- 实现预算化召回：scope/layer/type/status 过滤、top_k、max_chars、相关性排序、冲突提示和引用来源。
- 新增或等价实现 `memory_recall` 与 `memory_candidate_writer` 能力。前者只读召回并输出 `memory_context`，后者只生成候选和证据，不能直接改长期记忆。
- 前端和运行详情展示召回命中、候选、应用/拒绝、冲突、revision 和来源 run。
- Buddy Home 文件继续作为用户可编辑投影；底层 Store、command 和 revision 是审计与恢复来源。

### 上下文预算和大结果处理

目标：减少外层 LLM 被结果包、日志、文件和历史塞爆的风险。

待做：

- 为每个 LLM 节点建立上下文装配报告：读取了哪些 state、文件、result outputs、记忆、知识库 chunk，各占多少字符/token。
- 为 `result_package` 定义默认渲染策略：公开 output 可摘要展示，原始值保存在 artifacts 或可按需展开的 state 中。
- 大 artifact 只传路径、摘要、mime、大小、来源和关键引用；不把 base64、完整日志、大媒体或大量网页正文写进长期上下文。
- 历史对话、Buddy Home、运行记录和子图结果都要按预算裁剪，并保留 omitted list。
- 建立只读 fanout 的并行上下文装配：记忆召回、知识库检索、页面上下文压缩、能力候选读取可以并行，合并节点负责预算和冲突处理。

### Skill 与模板自我演进

目标：Buddy 能从运行轨迹、失败、用户纠正和成功经验中提出小步、可逆、可审查的改进。

待做：

- 后台复盘输出 improvement candidates，而不是直接做高风险变更。
- Skill 改进链路：读取旧 Skill 包、生成补丁、测试、审查、用户批准、写入 `skill/user/` 或生成新 revision。
- 图模板改进链路：生成 graph diff 草案、预览、校验、可选试运行、用户批准、保存为用户模板。
- 能力缺口链路：建议进入 `toograph_skill_creation_workflow` 或图模板创建流程，不假装已经拥有能力。
- 所有文件写入、脚本执行、图修改、权限扩大、网络访问和自动化创建都必须有清晰权限和可恢复 revision。

### Hybrid RAG 知识库

目标：把当前基础检索升级成可扩展的 Hybrid RAG，让业务模板能稳定获得带 citation 的外部资料上下文。

待做：

- 增加 embedding 存储、content hash、provider/model 记录和知识库级 rebuild API。
- 实现关键词 + 向量 + metadata filter 的混合召回，并支持 rerank。
- 输出 `knowledge_context`，包含 citation id、chunk id、标题、section、score、source path/url 和摘要。
- 区分 `knowledge_context` 与 `memory_context`：Knowledge 是外部资料，Memory 是历史经验和偏好。
- 在业务模板中显式声明需要的知识库、召回字段和引用输出。
- 为检索质量建立评测：命中率、引用准确性、遗漏关键条件、过度引用、chunk 质量和上下文预算。

### Agent Eval 评测体系

目标：让官方模板、业务模板、Buddy 主循环和关键 Skill 可以持续回归验证。

待做：

- 建立 eval suite、case、run 和 case result 数据结构。
- 每个 Eval Case 发起独立 graph run，保留 run id、状态、错误、输出、artifacts 和节点失败信息。
- 支持 schema 检查、artifact 检查、引用检查、规则检查、LLM judge 和人工评审记录。
- 前端或 API 展示 suite 结果、case diff、失败原因和可复跑入口。
- 覆盖 Buddy 主循环、能力循环、页面操作、Skill 创建、联网搜索和至少一个业务模板。

## 业务模板待办

业务模板用于证明 TooGraph 能承载真实工作流，而不是只展示单次问答。模板必须有多源输入、结构化中间 state、显式 Skill/Subgraph、artifact 输出、审计和 Eval。

首批建议：

- Policy Navigator：政策/通知白话解读，输出资格清单、关键条款、风险提示和引用。
- AI News Digest to WeChat Article：多源新闻整理、证据筛选、公众号文章生成、引用和事实核查。
- Multi-platform Content Repurposer：一文多发、风格迁移、去 AI 味、平台差异化稿件和反馈记忆候选。

下一组建议：

- Job Application & Interview Coach：JD/简历匹配、项目故事、差距分析、面试题和行动计划。
- Game Creative Factory：通用游戏广告创意生产。`game_genre` 是输入字段，SLG 只是一种示例值；同一模板应支持 RPG、策略、休闲、模拟、卡牌、塔防、解谜、射击等类型。
- Product Competitor Research：竞品资料抓取、需求洞察、差异分析和证据地图。
- E-commerce Review Mining：评论聚类、卖点提炼、痛点优先级和素材 briefs。

每个业务模板都要补齐：

- 输入 schema、Graph State、节点流程、Skill 列表和权限说明。
- mock data 模式，保证无外部账号时也能演示。
- 主要 artifacts：Markdown、JSON、表格、引用地图、评审报告或文件包。
- Eval cases：完整性、引用准确性、风险边界、结构化输出、预算控制和返修循环。
- 长期记忆集成：只输出候选记忆和证据，不直接绕过 Store、command、revision 或审批。

## 部署和项目可用性

待做：

- 梳理桌面端、Docker 或单机部署路径，降低非开发环境启动成本。
- 为关键 UI 流程补充端到端测试：编辑器、运行记录、Buddy 虚拟操作、权限确认、多语言和模板运行。
- 完善知识库更新、删除、重建索引、检索质量评估和引用展示。
- 将内部 `agent` kind 的用户心智逐步迁移为 LLM 节点语义；不能引入第二套协议。

## 不再维护的方向

- 不恢复 `docs/current_project_status.md` 这类当前实现快照。
- 不恢复 `docs/future/toograph_p0_p1_development_goals.md` 或平行的模板库长期规划。
- 不创建单体 `self_evolve` Skill 或 Buddy 专用隐藏 runtime。
- 不把 SLG 做成固定模板身份；游戏模板应以通用 `game_genre` 输入表达类型。
- 不把用户聊天输入当作隐藏断点 resume payload。
- 不让 Buddy 绕过 TooGraph 编辑器命令、校验、审计、revision 和 undo/redo 直接改图。
