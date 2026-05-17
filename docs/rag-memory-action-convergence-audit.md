# RAG 与记忆系统 Action 收敛调研

本文记录 TooGraph 当前官方 Action 的职责审计、RAG 与记忆系统的共用能力边界，以及为了实现“共享底层能力、用图模板区分业务语义”的推荐路线。本文不是阶段性流水账，而是后续做 RAG/Memory 能力收敛时的正式架构参考。

调研日期：2026-05-22

## 1. 结论

RAG 和记忆系统可以共享检索、排序、去重、上下文预算、来源追踪、审计和评测这些底层能力，但不能共享同一个业务语义。

推荐方向：

```text
共用底层能力：
query planning / hybrid retrieval / rerank / context budget / source trace / context package

分开业务 Action：
knowledge_retrieval / buddy_session_recall / buddy_home_reader / buddy_home_writer

用图模板表达流程：
RAG 问答 / 记忆召回 / 记忆写回 / 统一上下文 fanout / 评测
```

当前官方 Action 中没有需要立即删除的明显重复 Action，但有几类需要收敛：

1. `toograph_capability_selector` 目前只是固定返回页面操作子图，名字像通用能力选择器，实际是占位能力，后续应该升级或改名。
2. `toograph_context_fanout` 职责过宽，把 Buddy Home 记忆、知识库检索、页面上下文和能力候选混在一个 Action 中。它适合作为当前过渡实现，但目标形态应该是图模板编排多个更窄 Action。
3. `toograph_graph_template_validator` 和 `toograph_graph_template_writer` 内部重复了模板解析和校验逻辑，应抽到后端共享 helper，但两个 Action 的外部职责仍应保留。
4. `toograph_action_package_reader` 和 `toograph_graph_template_reader` 都是“包读取器”，但读取对象、校验规则和输出结构不同，暂时不建议合并为一个 Action。
5. `buddy_session_recall` 被多个业务模板当作“风格或历史偏好召回”，这是合理的只读历史能力，但应在图模板中明确它不是长期记忆权威。
6. `buddy_visible_subgraph_result_adapter` 体量大、内部兼容路径多，后续可沉淀成通用 result package adapter 或 runtime primitive，但不是 RAG/Memory 第一优先级。

## 2. 当前官方 Action 盘点

当前 `action/official/` 下共有 14 个 Action：

| Action | 当前职责 | 权限 | 是否内部 | 初步判断 |
| --- | --- | --- | --- | --- |
| `buddy_home_writer` | 受控写入 Buddy Home，生成 command/revision | `buddy_home_write` | 是 | 保留，记忆写回唯一出口 |
| `buddy_session_recall` | 只读 Buddy 会话历史，支持 browse/discover/scroll | `buddy_session_read` | 是 | 保留，历史召回专用 |
| `buddy_visible_subgraph_result_adapter` | 把可见页面操作子图结果适配回 Buddy capability result package | 无 | 是 | 保留但后续可泛化 |
| `local_workspace_executor` | 白名单本地文件读写、搜索、执行 | `file_read,file_write,subprocess` | 否 | 保留，低层本地操作能力 |
| `toograph_action_builder` | 生成 Action 包文件内容 | `file_read` | 否 | 保留，用于 Action 创建流程 |
| `toograph_action_package_reader` | 读取已有 Action 包 | `action_read` | 否 | 保留，可共享包读取 helper |
| `toograph_capability_selector` | 当前固定返回 `toograph_page_operation_workflow` | 无 | 否 | 需升级或改名 |
| `toograph_context_fanout` | 并行装配 memory/knowledge/page/capability context | `buddy_home_read,knowledge_read,file_read` | 是 | 过渡保留，目标拆成图模板 |
| `toograph_graph_template_reader` | 读取官方或用户图模板 | `file_read` | 否 | 保留，可共享包读取 helper |
| `toograph_graph_template_validator` | 校验图模板 JSON | 无 | 否 | 保留，内部逻辑需共享 |
| `toograph_graph_template_writer` | 校验并写入用户图模板，记录 revision | `file_write` | 否 | 保留，内部逻辑需共享 |
| `toograph_page_operator` | 页面虚拟操作、模板运行、图编辑意图 | `virtual_ui_operation` | 否 | 保留，高复杂核心能力 |
| `toograph_script_tester` | 编写并运行脚本测试 | `file_write,subprocess` | 否 | 保留，可共享执行沙箱 |
| `web_search` | 联网搜索、下载网页正文、本地 artifact 输出 | `network,secret_read,browser_automation` | 否 | 保留，可复用 source document artifact 规范 |

## 3. 官方模板中的 Action 使用情况

官方模板对 Action 的使用呈现几个特征：

| Action | 直接被官方模板声明次数 | 说明 |
| --- | ---: | --- |
| `buddy_session_recall` | 8 | 大量业务模板用它读取历史偏好、过往上下文或风格样本 |
| `web_search` | 1 | AI 新闻摘要模板显式使用联网补充 |
| `toograph_context_fanout` | 1 | Buddy 上下文 fanout 内部模板使用 |
| `buddy_home_writer` | 1 | Buddy 后台复盘写回使用 |

这说明当前业务模板普遍把 `buddy_session_recall` 作为轻量记忆上下文来源。这个方向可以保留，但需要更清晰地区分：

- `buddy_session_recall` 是历史会话召回。
- `MEMORY.md` 是长期记忆权威。
- `knowledge_context` 是外部知识证据。
- `context_brief` 只是本轮上下文摘要，不是系统指令，也不是权限来源。

## 4. RAG 与记忆系统的共通层

RAG 和记忆系统都可以抽象成“从来源中找上下文，然后包装给 LLM 使用”。

共通操作包括：

| 共通能力 | RAG 用法 | 记忆用法 |
| --- | --- | --- |
| query planning | 把用户问题改写成知识库检索 query | 把用户目标改写成历史会话或偏好查询 |
| source retrieval | 搜知识库 chunk | 搜 Buddy Home 或 buddy.db 会话 |
| metadata filter | 过滤知识库、来源、section、时间、权限 | 过滤当前会话 lineage、角色、时间、来源 |
| rerank/dedupe | 排序知识 chunk，去重文档 | 排序历史会话，去重 lineage |
| context budget | 控制检索证据长度 | 控制 MEMORY.md 和历史消息长度 |
| source trace | citation id、chunk id、URL、页码 | message_id、session_id、run_id、revision_id |
| audit report | 检索分数、命中条数、遗漏项 | 召回模式、命中窗口、写回 revision |
| eval | context precision、citation accuracy | 记忆稳定性、去重、错误沉淀率 |

这部分可以逐步沉淀为共享 helper 或标准 output contract。

## 5. RAG 与记忆系统必须分开的语义层

RAG 和记忆最容易混淆的地方是“都给 LLM 提供上下文”。但它们的权威性完全不同。

| 维度 | RAG | 记忆 |
| --- | --- | --- |
| 来源 | 外部文档、网页、政策、产品资料 | Buddy Home、用户偏好、历史会话 |
| 主要问题 | “资料怎么说？” | “用户过去怎么说？偏好是什么？” |
| 权威级别 | 外部事实证据 | 个性化上下文 |
| 输出引用 | citation、chunk、URL、页码 | session、message、run、revision |
| 写入触发 | 导入、同步、rebuild | 后台复盘、稳定性判断、受控写回 |
| 失败风险 | 引用错、过期资料、检索遗漏 | 错记偏好、沉淀临时信息、权限误升 |
| 安全边界 | 文档权限和来源过滤 | 记忆不能覆盖系统规则或权限 |

规则：

- RAG 可以支撑事实型回答。
- 记忆只能作为个性化上下文。
- 记忆不能变成系统规则。
- 记忆不能替代用户当前指令。
- 记忆不能提升图操作、文件写入、网络访问或脚本执行权限。
- 长期记忆写入只能通过受控写回和 revision。

## 6. 推荐统一输出契约：context_package

为了共享底层能力而不混淆语义，建议新增一个统一上下文包结构。

```json
{
  "kind": "context_package",
  "source_kind": "knowledge|memory|session|page|capability|web",
  "authority": "evidence|preference|history|context_only|candidate",
  "query": "检索或召回使用的 query",
  "items": [
    {
      "id": "kb:docs:1",
      "title": "来源标题",
      "summary": "摘要",
      "content": "预算内上下文",
      "score": 0.82,
      "source": "URL、文件、message_id 或 revision_id",
      "metadata": {},
      "trace": {}
    }
  ],
  "citations": [],
  "budget": {
    "used_chars": 1200,
    "source_chars": 4500,
    "omitted_count": 2
  },
  "warnings": []
}
```

`authority` 是关键字段：

- `evidence`：可作为事实证据，例如 RAG 文档、网页来源。
- `preference`：用户长期偏好，例如 `MEMORY.md`。
- `history`：历史会话事实，例如 buddy.db message。
- `context_only`：只可参考，不能作为权限或新指令。
- `candidate`：候选内容，仍需审查。

这样下游 LLM 节点可以共用渲染逻辑，但仍知道不同来源的权威级别。

## 7. 冗余与收敛审计

### 7.1 `toograph_capability_selector`

当前状态：

- `after_llm.py` 只有固定返回：

```json
{
  "kind": "subgraph",
  "key": "toograph_page_operation_workflow"
}
```

问题：

- 名字叫 capability selector，但没有检索真实 Action、Subgraph 或 Tool catalog。
- 容易让人以为它已经是通用能力选择器。
- 与 `toograph_context_fanout` 中 capability 分支的固定页面操作候选存在概念重复。

建议：

1. 短期保留，避免 Buddy 能力循环断链。
2. 文档中标注它是固定页面操作选择器。
3. 中期升级为真正的 capability retrieval Action，输入 goal/context，输出候选列表和选择结果。
4. 如果短期不升级，改名为 `toograph_page_operation_selector` 更准确。

优先级：P1。

### 7.2 `toograph_context_fanout`

当前状态：

- 同时读取 Buddy Home MEMORY.md、知识库、页面上下文和固定能力候选。
- 输出 `memory_context`、`knowledge_context`、`page_context_summary`、`capability_candidates`、`context_brief`。

问题：

- 职责过宽。
- RAG 和记忆的语义边界靠内部字段维持，没有统一 context package。
- knowledge branch 直接调用 runtime helper，不是独立 `knowledge_retrieval` Action。
- capability branch 固定页面操作候选，不是真实能力发现。

建议：

短期保留它作为 Buddy 主循环的稳定入口。中期拆成图模板：

```text
LLM: 生成 fanout_request
Action: buddy_home_reader 或 memory_context_pack
Action: buddy_session_recall 可选
Action: knowledge_retrieval
Action: page_context_pack
Action: capability_retrieval
LLM/Action: context_package_merge
Output: context_brief + fanout_report
```

拆分后，`toograph_context_fanout` 可以降级为兼容 Action 或被 `buddy_context_fanout` 图模板替代。

优先级：P1。

### 7.3 `toograph_graph_template_validator` 与 `toograph_graph_template_writer`

当前状态：

- validator 负责校验模板 JSON。
- writer 会再次解析和校验模板，然后写入用户模板并记录 revision。

问题：

- 两者重复实现 `_coerce_template_payload` 和模板校验逻辑。
- 如果协议变更，两个 Action 可能出现校验口径不一致。

建议：

- 保留两个 Action，因为一个只读校验，一个有写入副作用。
- 把模板解析、schema 校验、graph 校验、LangGraph runtime 兼容性校验抽到后端共享模块。
- writer 调用共享校验 helper，并在写入前仍强制校验。

优先级：P2。

### 7.4 `toograph_action_package_reader` 与 `toograph_graph_template_reader`

当前状态：

- 都是读取包内容。
- 一个读取 Action 包内多个文件。
- 一个读取 template.json 并解析 JSON。

问题：

- 路径安全、scope、大小预算、读取报告可以共用 helper。
- 但输出结构和业务对象不同。

建议：

- 不合并 Action。
- 抽共享 helper：safe scope resolution、path budget、UTF-8 read、omitted file report。
- 保留 `action_package` 和 `template_package` 两种输出契约。

优先级：P3。

### 7.5 `local_workspace_executor` 与 `toograph_script_tester`

当前状态：

- 两者都涉及文件写入和 subprocess。
- `local_workspace_executor` 面向明确路径的本地读写/搜索/执行。
- `toograph_script_tester` 面向脚本测试流程，会生成测试文件并运行命令。

问题：

- 底层执行和白名单策略有复用空间。
- 但用户意图不同，不应合并 Action。

建议：

- 保留两个 Action。
- 共享命令白名单、路径归一化、执行报告、安全错误格式。
- 高风险执行仍必须通过权限路径和图模板审核。

优先级：P3。

### 7.6 `web_search` 与未来 RAG ingestion

当前状态：

- `web_search` 会搜索网页、下载正文、输出本地 source document artifact。
- RAG 系统未来也需要网页或文档导入。

问题：

- 搜索和下载得到的 source document artifact 可以成为知识库导入输入。
- 但 `web_search` 不应该直接写知识库索引，否则会把“临时联网搜索”和“持久知识库导入”混在一起。

建议：

- 保留 `web_search` 为临时外部证据检索。
- 新增 `knowledge_ingest` 或 `knowledge_import` Action 负责显式持久化导入。
- 共享 source document artifact 格式。

优先级：P2。

### 7.7 `buddy_home_writer`

当前状态：

- 支持 `memory_document.update`、`session_summary.update`、`profile.update`、`policy.update`、`report.create`、`capability_usage_stats.update`。

问题：

- 它是写入器，不是记忆策略本身。
- 目前 command 种类较多，但都属于 Buddy Home 受控写回。

建议：

- 保留。
- 后续若写入规则变复杂，不要拆成多个写入 Action，优先让图模板负责策略判断，writer 只负责校验和写入。
- `policy.update` 继续限制在非权限字段。

优先级：保留。

## 8. 推荐新增或改造的 Action

### 8.1 新增 `knowledge_retrieval`

目的：把 RAG 检索从 `toograph_context_fanout` 中抽出来，成为正式可复用 Action。

输入：

```json
{
  "query": "检索 query",
  "knowledge_base": "知识库 ID",
  "limit": 5,
  "metadata_filter": {
    "source_path_prefix": "",
    "source_kind": "",
    "section": ""
  },
  "retrieval_mode": "hybrid"
}
```

输出：

```json
{
  "success": true,
  "knowledge_context": {},
  "context_package": {},
  "results": [],
  "citations": [],
  "retrieval_report": {},
  "warnings": []
}
```

要求：

- 调用现有 `retrieve_knowledge_base_context()` 或 `search_knowledge()`。
- 保留 citation id、chunk id、source、metadata、score。
- 输出 `authority=evidence` 的 `context_package`。
- 不负责最终总结。
- 不写知识库。

### 8.2 新增或明确 `buddy_home_reader`

目的：让读取 Buddy Home 也变成显式能力，而不是只藏在 `toograph_context_fanout` 内。

输入：

```json
{
  "files": ["SOUL.md", "USER.md", "MEMORY.md", "policy.json"],
  "budget_chars": 3000
}
```

输出：

```json
{
  "success": true,
  "buddy_home_context": {},
  "memory_context": {},
  "context_package": {},
  "warnings": []
}
```

要求：

- `MEMORY.md` 输出 `authority=preference`。
- `SOUL.md`、`USER.md`、`policy.json` 输出 `authority=context_only` 或明确字段。
- 不写文件。
- 不做会话 FTS。

### 8.3 新增 `context_package_merge`

目的：统一合并 RAG、Memory、Session、Page、Capability 的上下文包。

输入：

```json
{
  "packages": [],
  "total_budget_chars": 6000,
  "merge_policy": "authority_aware"
}
```

输出：

```json
{
  "context_brief": {},
  "merged_context_package": {},
  "assembly_report": {}
}
```

要求：

- 不改变 source authority。
- 不把 memory 当 evidence。
- 不把 context_only 当权限。
- 保留 omitted list。

### 8.4 升级 `toograph_capability_selector`

目标形态：

```text
输入 user_goal + context_brief + allowed_origins
读取 Action catalog + graph template catalog + policy
输出候选能力列表、选中能力、found、reason、required_permissions
```

短期可以只支持：

- 固定页面操作子图。
- 已注册 Action catalog。
- 官方模板 catalog。

中期再支持：

- 用户模板。
- 能力评分。
- 缺能力时生成 capability_gap。

## 9. 推荐图模板

### 9.1 `rag_question_answering`

用于文档问答。

```text
input_question
input_knowledge_base
-> plan_retrieval_query
-> knowledge_retrieval
-> review_evidence
-> has_enough_evidence
   true -> draft_grounded_answer
   false -> ask_for_more_sources_or_report_gap
-> output_answer
-> output_citations
```

关键约束：

- 回答必须使用 citation。
- 资料不足时说明不足。
- 不读 Buddy memory，除非模板显式需要个性化语气。

### 9.2 `memory_context_recall`

用于召回用户历史和偏好。

```text
input_user_goal
input_current_session_id
-> build_memory_query
-> buddy_home_reader
-> optional buddy_session_recall
-> filter_memory_context
-> output_memory_context_package
```

关键约束：

- 会话召回是 history。
- MEMORY.md 是 preference。
- 不能输出权限升级。

### 9.3 `memory_review_and_writeback`

用于后台复盘沉淀长期记忆。

```text
input_source_run_id
input_run_snapshot
input_recent_conversation
-> buddy_session_recall
-> extract_memory_candidates
-> filter_memory_candidates
-> merge_memory_document
-> review_write_risk
-> buddy_home_writer
-> output_revision_report
```

关键约束：

- 只写稳定、长期有用、非敏感、不可从当前图重读的信息。
- 写回必须产生 revision。
- 高风险 policy 或权限字段不能自动写。

### 9.4 `unified_context_fanout`

用于 Buddy 主循环启动上下文。

```text
input_user_message
input_conversation_history
input_page_context
input_buddy_context
-> build_fanout_queries
-> buddy_home_reader
-> knowledge_retrieval
-> page_context_pack
-> capability_selector
-> context_package_merge
-> output_context_brief
-> output_assembly_report
```

关键约束：

- 这是图模板，不是单个自治 Action。
- 每个分支的权限和 source authority 可见。
- `context_brief` 只能作为 context_only。

## 10. 具体落地任务

### P0：先建立契约，不动大结构

1. 在文档中定义 `context_package` 契约。
2. 明确 `authority` 枚举：`evidence`、`preference`、`history`、`context_only`、`candidate`。
3. 更新 Action 作者指南，说明 RAG 和 Memory 输出如何包装。
4. 在测试中增加 context package contract 示例。

建议文件：

- `action/ACTION_AUTHORING_GUIDE.md`
- `docs/rag-memory-action-convergence-audit.md`
- `backend/tests/test_action_manifest_contract.py`

### P1：新增 `knowledge_retrieval` Action

1. 创建 `action/official/knowledge_retrieval/action.json`。
2. 创建 `after_llm.py`，调用现有知识库 runtime。
3. 支持 `query`、`knowledge_base`、`limit`、`metadata_filter`。
4. 输出 `knowledge_context`、`context_package`、`citations`、`retrieval_report`。
5. 增加单元测试。
6. 在 `action/settings.json` 启用。

建议测试：

- manifest 可加载。
- 空知识库时返回失败或空结果。
- 能返回 citation、chunk_id、score。
- metadata filter 可生效。
- 输出 `authority=evidence`。

### P1：明确 Buddy Home 读取能力

两种做法：

1. 新增 `buddy_home_reader` Action。
2. 或者先在 `toograph_context_fanout` 中输出更标准的 `context_package`。

推荐先做第 2 种，降低改动面；等 `knowledge_retrieval` 稳定后再新增 reader。

### P1：升级能力选择

1. 把 `toograph_capability_selector` 的文档描述改成当前真实行为，避免误导。
2. 在 roadmap 中标注目标是 catalog-based capability retrieval。
3. 后续实现时，让 selector 读取 Action catalog 和 template catalog。
4. 不要让 LLM 自由编造能力。

### P2：把 `toograph_context_fanout` 拆成图模板

1. 保留原 Action 作为兼容路径。
2. 新增或改造 `buddy_context_fanout` 子图模板。
3. 模板内显式调用 `knowledge_retrieval`、Buddy Home 读取、页面上下文压缩、能力选择。
4. 输出统一 `context_brief` 和 `assembly_report`。
5. Buddy 主循环改用新模板。

### P2：新增标准 RAG 问答模板

1. 新建 `graph_template/official/rag_question_answering/template.json`。
2. 支持输入问题和知识库。
3. 调用 `knowledge_retrieval`。
4. 增加证据审查节点。
5. 输出答案、citations、uncertainties。
6. 增加 eval cases。

### P2：补 RAG Eval

1. 扩展 evaluator 中已有 `knowledge_retrieval` / `knowledge_context` 检查。
2. 增加 citation accuracy 检查。
3. 增加 context recall / precision 的简单规则版。
4. 对 `rag_question_answering` 加官方 eval case。

### P3：抽共享 helper

1. 模板校验 helper：供 validator 和 writer 复用。
2. 包读取 helper：供 action reader 和 template reader 复用。
3. 命令执行 helper：供 local executor 和 script tester 复用。
4. source document artifact helper：供 web_search 和 knowledge_import 复用。

### P3：知识库导入与真实 embedding

1. 新增 `knowledge_import` 或 `knowledge_ingest` Action。
2. 支持 local source document artifact 导入。
3. 支持真实 embedding provider。
4. 支持 rebuild report。
5. 支持删除一致性和版本记录。

## 11. 不建议做的事

不要把 `buddy_session_recall` 和 `knowledge_retrieval` 合并成一个 Action。
理由：一个返回历史上下文，一个返回外部证据，权限和权威不同。

不要让 `buddy_home_writer` 承担记忆判断策略。
理由：写入器只负责受控写入和 revision，是否应该写入应由图模板判断。

不要让 `web_search` 直接写知识库。
理由：联网搜索是临时证据，知识库导入是持久副作用，必须显式分开。

不要让 capability selector 由 LLM 编造能力。
理由：能力必须来自 Action catalog、Tool catalog 或 graph template catalog。

不要为了减少 Action 数量而合并 reader/writer。
理由：读和写的权限、审计和风险等级不同。

## 12. 推荐实施顺序

建议按这个顺序推进：

1. 文档和契约：定义 `context_package`。
2. 新增 `knowledge_retrieval` Action。
3. 让 `toograph_context_fanout` 输出标准 context package。
4. 新增 `rag_question_answering` 模板。
5. 升级 `toograph_capability_selector` 或改名。
6. 把 fanout 从 Action 逐步迁移为图模板。
7. 抽共享 helper，减少重复实现。
8. 做 RAG Eval 和 Memory Eval。
9. 做真实 embedding 和知识库导入。

这个顺序的优点是：先获得可复用 RAG 能力，再逐步整理内部 Action，不会破坏现有 Buddy 主循环。

## 13. 验收标准

完成后应满足：

- RAG 问答可以通过 `knowledge_retrieval` 独立运行。
- 记忆召回仍通过 `buddy_session_recall` 和 Buddy Home 读取，不混入知识库。
- 下游 LLM 能看到每个 context item 的 `authority`。
- `context_brief` 不会把 memory 当作事实证据。
- `toograph_capability_selector` 不再是误导性固定选择器，或已经改名。
- 模板 writer 和 validator 使用同一校验口径。
- RAG eval 能检查 citation 和检索命中。
- Memory review 能检查稳定性、敏感性、重复沉淀和 revision。

## 14. 当前最小可执行切片

如果只做一个最小闭环，建议这样切：

1. 增加 `knowledge_retrieval` Action。
2. 输出 `context_package.authority=evidence`。
3. 新增一个最小 `rag_question_answering` 模板。
4. 保持 `toograph_context_fanout` 不动，只在报告中标注后续拆分。
5. 给 `toograph_capability_selector` 增加文档说明或重命名计划。

这样可以最快把 RAG 从“fanout 内部能力”升级为“可被任意图模板复用的显式能力”，同时不干扰已有记忆系统和 Buddy 主循环。
