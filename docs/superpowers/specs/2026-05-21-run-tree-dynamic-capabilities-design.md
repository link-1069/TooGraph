# TooGraph Run Tree 与动态能力执行设计

## 目标

TooGraph 需要把 Buddy、图模板、Subgraph node、动态能力选择和运行记录统一到同一套语义中：

```text
一个图是一个 Agent。
一次图执行是一个 Run。
一个图调用另一个图，就是父 Run 创建一个 child Run。
```

这份设计固定以下产品和工程边界：

- 动态 `capability` state 的合法 `kind` 为 `action`、`subgraph`、`tool`、`none`。
- `skill` 不再作为动态能力 kind；未来 Skill 是 Agent 操作书型能力，不属于这个 capability 执行协议。
- Buddy 不再通过页面操作工作流去“打开模板并点击运行”来执行通用能力。
- 所有图级子 Agent 都有独立运行记录。
- Buddy 胶囊折叠态只显示当前运行内容，展开态显示完整运行历史和树形结构。
- Batch subgraph worker 也创建 child run，但在 UI 中按 batch group 折叠。

## 当前问题

当前实现已经有动态能力和子图执行的底层能力，但存在几类设计噪音：

- `toograph_capability_selector` 固定返回 `toograph_page_operation_workflow`，导致普通需求也绕到页面操作流程。
- `toograph_context_fanout` 的 capability 分支固定提供页面操作候选，而不是真实 action/subgraph/tool catalog。
- `buddy_capability_loop` 对页面操作和可见模板运行有特殊分支，通用 subgraph 没有直接走统一动态执行。
- `buddy_visible_subgraph_result_adapter` 只为旧的页面操作模板运行路径服务。
- Buddy 窗口存在“跟随”按钮和 follow preference，但新产品语义要求所有运行都后台化。
- Subgraph 当前多为嵌入式执行：子图复用父 run id，内部状态写入父 run 的 `subgraph_status_map`，不会天然生成独立 run 记录。

这些问题会让 Buddy 看起来像在“操控页面”而不是“选择能力并运行图级 Agent”，也会让用户难以从运行记录中审计每个子 Agent 的完整过程。

## 核心决定

### 1. 动态能力协议

`capability` state 是单个互斥对象，不能是列表。

合法形状：

```json
{
  "kind": "action",
  "key": "web_search",
  "name": "联网搜索"
}
```

```json
{
  "kind": "subgraph",
  "key": "advanced_web_research_loop",
  "name": "高级联网研究"
}
```

```json
{
  "kind": "tool",
  "key": "video_segmenter",
  "name": "视频分段"
}
```

没有合适能力时返回：

```json
{
  "kind": "none",
  "reason": "没有找到适合该请求的能力。"
}
```

`none` 表示“选择已完成但没有可执行能力”。它不进入动态执行节点，后续应该路由到普通回复、澄清或能力缺口说明。

### 2. Action、Tool、Subgraph 的执行边界

- `action`：一次受控能力调用，可包含 LLM 参数规划、`before_llm.py`、`after_llm.py` 和 state 写回。它不拥有多步自治。
- `tool`：确定性处理能力，不调用 LLM。它适合视频分段、OCR、文档切块、格式转换等。
- `subgraph`：图级 Agent。运行时必须创建独立 child run。
- `none`：不可执行，只做路由和回复。

`skill` 不属于这里。旧代码和文档中的 `skillKey`、`kind: "skill"`、`skillBindings` 等属于历史命名，后续迁移应显式清理，不做隐藏兼容扩展。

### 3. Run Tree 语义

所有图调用图的场景都创建 child run：

- 普通 Subgraph node。
- 动态 `capability.kind=subgraph`。
- Batch node 中的 subgraph worker item。
- 后续任何模板运行另一个模板的能力。

父 run 与 child run 关系写入 run record，而不是只塞进父 run 的 `subgraph_status_map`。

推荐 run 关系字段：

```json
{
  "parent_run_id": "run_parent",
  "root_run_id": "run_root",
  "parent_node_id": "run_selected_subgraph",
  "invocation_kind": "dynamic_subgraph_capability",
  "invocation_key": "advanced_web_research_loop",
  "run_depth": 1,
  "run_path": ["run_parent", "run_child"]
}
```

`invocation_kind` 初始取值：

- `subgraph_node`
- `dynamic_subgraph_capability`
- `batch_subgraph_worker`
- `template_run`

父 run 的节点执行记录和 activity event 应记录：

- `child_run_id`
- `child_run_status`
- `child_run_graph_id`
- `child_run_graph_name`
- `invocation_kind`
- `invocation_key`
- 输出摘要或失败摘要

### 4. Subgraph 执行模型

第一阶段采用同步等待的 child run 模型：

```text
父 run 节点开始
-> 创建并保存 child run
-> child run 使用标准运行机制执行并实时持久化
-> 父节点等待 child run 结束
-> 父节点读取 child run 的公开 output
-> 父 run 继续执行
```

这不是前端“跟随”，也不是页面播放。父 run 和 child run 都是后台 run，分别有自己的 run detail 和事件流。

如果 child run 成功完成，父节点把 child run 的公开 output 打包回父 run 的 state。

如果 child run 失败，父节点写入失败状态、错误摘要和 child run 链接。父图是否继续由图内条件节点决定。

如果 child run 进入 `awaiting_human`，父 run 也进入等待状态，并记录：

```json
{
  "pending_child_run_id": "run_child",
  "pending_child_parent_node_id": "run_selected_subgraph",
  "pending_child_invocation_kind": "dynamic_subgraph_capability"
}
```

用户在 child run 的标准 review surface 完成处理后，父 run 可以继续读取 child run 的最终 output 并恢复后续节点。

### 5. Result Package 合同

动态 capability 执行节点继续只写一个 `result_package` state。

`subgraph` result package 需要带 child run 引用：

```json
{
  "kind": "result_package",
  "sourceType": "subgraph",
  "sourceKey": "advanced_web_research_loop",
  "sourceName": "高级联网研究",
  "status": "succeeded",
  "childRunId": "run_child",
  "outputs": {
    "final_reply": {
      "name": "Final Reply",
      "description": "子图公开输出。",
      "type": "text",
      "value": "..."
    }
  }
}
```

为了兼容现有前端 trace 和 operation report，迁移期可以同时提供 `triggered_run_id`，但新协议字段应以 `childRunId` 或 snake_case `child_run_id` 为准。

### 6. Buddy 胶囊

Buddy 胶囊只表达 run tree，不表达“跟随页面”。

折叠态：

- 只显示当前 active leaf run 或当前父节点正在做什么。
- 示例：`正在选择能力`、`正在运行高级联网研究`、`正在整理最终回复`。
- 不显示完整历史。
- 不显示跟随按钮。

展开态：

- 显示完整运行历史和树形结构。
- 父 Buddy run 是根。
- 能力选择、action/tool activity、subgraph child run 都是树中的节点。
- child run 可点击进入标准 RunDetail。
- 失败、等待人工、运行中状态要在树中可见。

示例：

```text
Buddy run
  能力选择: advanced_web_research_loop
  child run: 高级联网研究
    输入整理
    联网搜索
    结果归纳
  最终回复
```

### 7. Batch 分组折叠

Batch subgraph worker 也创建 child run，但 UI 默认折叠为 batch group。

示例：

```text
root run
  batch node: 批量处理 50 个文件
    batch group: 50 items, 32 completed, 2 failed, 16 running
      child run item 1
      child run item 2
      child run item 3
```

Batch child run 元数据：

```json
{
  "invocation_kind": "batch_subgraph_worker",
  "batch_group_id": "batch_process_files",
  "batch_item_index": 0,
  "batch_item_label": "file-a.pdf"
}
```

UI 默认只显示 group 汇总；展开 group 后才显示每个 item 的 child run。RunDetail 和 Buddy 展开态都应支持按状态查看 batch item：运行中、失败、完成。

## 能力选择设计

`toograph_capability_selector` 应从真实 catalog 中选择能力：

- discoverable graph templates -> `kind: "subgraph"`
- enabled Actions -> `kind: "action"`
- enabled Tools -> `kind: "tool"`

选择器输出必须是单个 capability，不得输出列表。它可以输出 selection reason、拒绝原因和候选摘要，但下游执行只接受一个互斥 capability。

`toograph_page_operation_workflow` 仍然可以作为一个 discoverable subgraph，但只应在用户明确要求页面操作、图编辑、打开 UI 页面或应用内操作时被选中。

普通需求示例：

- “帮我整理最新 AI 新闻” -> `advanced_web_research_loop` 或更具体的新闻整理 subgraph。
- “打开知识库页面” -> `toograph_page_operation_workflow`。
- “把这个视频分段” -> `video_segmenter` tool。
- “没有合适能力” -> `none`。

## 旧路径清理

需要删除或降级以下旧路径：

- Buddy follow button、follow storage key、follow preference UI。
- 用 `toograph_page_operation_workflow` 运行通用模板的特殊路由。
- `run_visible_template_operation` 作为通用 subgraph 运行路径。
- `buddy_visible_subgraph_result_adapter` 对通用能力链路的依赖。
- 文档和模板中“selector 固定返回页面操作”的描述。
- 动态 capability 中的 `kind: "skill"` 残留。

页面操作能力本身保留，但它只处理真实页面操作。

## API 与存储方向

Run record 需要支持父子关系字段。字段可以先存在 run JSON 顶层，后续再抽象成 `run_relation` 对象。

Runs API 需要支持：

- 查询 root runs。
- 查询某个 run 的 child runs。
- 查询完整 run tree。
- RunDetail 返回当前 run 的直接 children 摘要。

推荐新增：

```text
GET /api/runs/{run_id}/tree
```

该接口返回 root、children、batch groups 和每个节点的状态摘要，供 Buddy 胶囊和 RunDetail 树视图复用。

现有 `/api/runs/{run_id}/events` 保持按单个 run 订阅。父 run 事件中记录 child run 创建和状态变化；进入 child RunDetail 后订阅 child run 自己的事件流。

## 开发阶段

### Phase 1: 协议和 selector 收口

- 明确 `capability.kind` 为 `action | subgraph | tool | none`。
- 清理 selector 和相关测试里的 `skill` 能力输出。
- `toograph_capability_selector` 改成 catalog-based selection。
- `toograph_context_fanout` 不再固定页面操作候选。

### Phase 2: Child run runtime

- 为普通 Subgraph node 创建 child run。
- 为动态 subgraph capability 创建 child run。
- 父节点等待 child run，并从 child run 公开 output 写回父 state。
- result_package 带 `childRunId`。
- child run 失败、等待人工、恢复路径有明确状态。

### Phase 3: Batch group

- Batch subgraph worker item 创建 child run。
- 父 run 记录 batch group 汇总。
- UI 默认折叠 batch group。

### Phase 4: Buddy 和 RunDetail UI

- 移除 Buddy follow UI。
- Buddy 胶囊折叠态只显示当前 active leaf。
- 展开态显示 run tree。
- RunDetail 显示 direct children 和 batch group。

### Phase 5: 旧路径删除和文档更新

- 删除通用能力链路对 visible template operation adapter 的依赖。
- 更新 README、roadmap、AGENT_ZH/CLAUDE 中与旧 Skill/capability/page-operation 固定选择冲突的描述。
- 删除或重写旧 follow mode E2E。

## 测试要求

后端：

- capability state 接受 `action/subgraph/tool/none`，拒绝 `skill`。
- `none` 不进入动态执行节点。
- 动态 action/tool 继续写唯一 result_package。
- 动态 subgraph 创建 child run 并写 child run id。
- 普通 Subgraph node 创建 child run。
- Batch subgraph worker 创建 child run，并生成 batch group 汇总。
- child run failed/awaiting_human/completed 三种状态都能反映到父 run。

前端：

- Buddy 折叠态只显示当前运行内容。
- Buddy 展开态显示 run tree。
- child run 链接可进入 RunDetail。
- Batch group 默认折叠，展开后显示 item child runs。
- 移除 follow preference 后不会影响已有后台运行 evidence 展示。

端到端：

- “整理最新 AI 新闻”选择研究/news subgraph，创建 child run，不走页面操作。
- “打开知识库页面”才选择页面操作 subgraph。
- 动态 subgraph 运行中可从 Buddy 胶囊展开进入 child RunDetail 看实时过程。
- Batch subgraph worker 多 item 运行时不会刷屏，默认显示 group 汇总。

## 非目标

- 不把 Action 或 Tool 都包装成 Run。它们保留 activity event 和 result_package，除非未来升级为图级能力。
- 不恢复 follow/playback 模式。
- 不把 `skill` 重新加入动态 capability 协议。
- 不引入隐藏 DOM 点击作为通用模板运行机制。
- 不在第一阶段引入分布式任务队列；child run 可以先由当前后台 worker 同步执行并持久化实时进度。

## 完成标准

- Buddy 普通能力请求不会再默认进入页面操作工作流。
- 任意图级子 Agent 都有独立 run 记录。
- 父 run 和 child run 之间有可查询、可展示、可审计的关系。
- Buddy 胶囊折叠态清爽，展开态能看完整树。
- Batch 子运行不刷屏，按 group 汇总展示。
- 旧 `kind: "skill"` 动态能力和 follow UI 不再出现在新协议路径中。
