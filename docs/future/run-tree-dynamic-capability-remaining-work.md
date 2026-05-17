# 运行树与动态能力剩余工作

本文记录 2026-05-22 审查后仍未完成、但已经确定需要继续推进的工作。它不是当前状态快照；代码、官方模板 JSON、Action manifest 和测试仍然是实现事实来源。这里保留的是后续开发需要遵守的目标、任务边界和验收标准。

相关入口：

- 动态能力协议校验：`backend/app/core/compiler/validator.py`
- LangGraph 运行时与子图执行：`backend/app/core/langgraph/runtime.py`
- 运行树存储与 API：`backend/app/core/runtime/run_tree.py`、`backend/app/core/storage/run_store.py`、`backend/app/api/routes_runs.py`
- Buddy 胶囊与运行 trace：`frontend/src/buddy/`
- 运行详情页运行树展示：`frontend/src/pages/RunDetailPage.vue`、`frontend/src/pages/runDetailModel.ts`
- 官方能力选择 Action：`action/official/toograph_capability_selector/`
- 官方 Buddy 能力循环模板：`graph_template/official/buddy_capability_loop/template.json`、`graph_template/official/buddy_autonomous_loop/template.json`

## 已确定的架构约束

- 动态 `capability` state 是单个互斥对象，合法 `kind` 为 `action`、`subgraph`、`tool`、`none`。`none` 表示没有找到可用能力。
- `skill` 是历史叫法，不应继续出现在动态能力 state 中；未来如果重新引入 Skill，也不能混入当前动态能力协议。
- 所有能力运行都应是后台运行。Buddy 不再提供“跟随按钮”作为运行模式分支；用户通过胶囊、运行记录和跳转入口观察进度。
- 任何 graph-calling-graph 路径都应创建独立 child run，包括 Subgraph node、动态 `capability.kind=subgraph`、batch subgraph worker，以及后续统一后的 subagent 路径。
- Buddy 胶囊折叠时只展示当前运行内容；展开后应能看到完整运行历史和树形结构。batch 子运行需要按 batch group 折叠。
- 动态能力执行只写一个 `result_package` state；Subgraph 结果包必须携带可追踪的 child run 标识，供 Buddy 胶囊和运行详情跳转。

## P0：子图暂停恢复必须续写原 child run

问题：

- 当前 Subgraph node 和动态 Subgraph capability 的首次执行会创建独立 child run。
- 但暂停后恢复路径仍根据 pending metadata 重建临时子图状态，并把 `run_id` 设回父 run；这会导致恢复过程没有天然续写原 child run。
- 主要风险点在 `_resume_subgraph_node_runtime` 和 `_resume_dynamic_subgraph_capability`。

目标：

- pending subgraph breakpoint 必须保存 `child_run_id`。
- resume 时加载原 child run，使用原 checkpoint/thread 元数据继续执行。
- 恢复过程应更新同一个 child run 的状态、节点执行记录、errors/warnings、artifacts 和终态。
- 父 run 只记录父级进度、结果包、activity event 和运行树关系，不冒充子图运行记录。
- 动态 Subgraph 恢复后的 `result_package` 继续包含 `child_run_id` / `triggered_run_id`。

验收标准：

- 一个会暂停的普通 Subgraph node 初次运行后，运行树中出现一个 status 为 `awaiting_human` 的 child run。
- 恢复该暂停后，同一个 child run id 变为 completed 或 failed；不会新增伪 child run，也不会把子图执行写到父 run id 上。
- 一个会暂停的动态 `capability.kind=subgraph` 具备同样行为。
- 父 run 的 `/api/runs/{run_id}/tree` 能稳定展示暂停前后同一 child run。
- 新增或更新后端测试覆盖普通 Subgraph node resume、动态 Subgraph capability resume、再次暂停、失败恢复和 result package 中的 child run 标识。

建议实现方向：

- 在 `_build_pending_subgraph_breakpoint` 和 `_build_pending_dynamic_subgraph_breakpoint` 输出中持久化 `child_run_id`。
- resume 路径优先通过 run store 读取 child run；缺失时才进入受控兼容错误，而不是静默重建父 run id 状态。
- 将 child run 的 checkpoint metadata、graph snapshot、state values 和 execution records 作为恢复事实来源。
- 恢复完成后保存 child run，再回写父 run 的 pending metadata、subgraph status map 和 result package。

## P1：Buddy 胶囊展开态接入真实运行树

问题：

- 当前 Buddy 胶囊展开态主要展示 output-boundary trace tree，并通过 evidence 链接跳转 child run。
- 这能看到局部执行线索，但不是完整的持久化 run tree，也没有在 Buddy 内做 batch group 折叠。

目标：

- 胶囊折叠态保持轻量，只显示当前 output-boundary 段的运行内容和状态。
- 胶囊展开态读取或接收父 run 的完整运行树，展示 parent run、child run、动态 subgraph、batch worker 和关键输出。
- batch worker 子运行按 `batch_group_id` 折叠，默认显示 group label、数量、完成/失败/运行中统计，展开后显示每个 item child run。
- 每个 child run 行都能跳转到运行详情页；失败、暂停、运行中状态必须清晰。
- Buddy 胶囊中的 trace event 与持久 run tree 不应互相矛盾；trace 可以作为实时增量，run tree 是恢复后的事实来源。

验收标准：

- 后台 Subgraph 运行时，Buddy 胶囊展开可以看到该 child run，而不是只有一条 evidence 标签。
- batch subgraph worker 多个 child run 默认折叠为一个 batch group。
- 页面刷新或重新打开 Buddy 后，胶囊展开仍能从后端恢复同一运行树。
- 运行中、awaiting_human、failed、completed 四类状态在胶囊树中都有稳定样式。
- 前端结构测试覆盖 Buddy 胶囊读取运行树、batch group 折叠、child run 跳转和恢复显示。

建议实现方向：

- 复用 `fetchRunTree` 和 `buildRunTreeDisplayItems`，或抽出 Buddy 与 RunDetail 共用的运行树 display model。
- Buddy 实时事件继续用于即时反馈；当 run id 可用时异步拉取 `/api/runs/{run_id}/tree` 作为展开态主数据。
- 避免把运行树塞进聊天正文；它属于消息 metadata 或可重新拉取的 UI 数据。

## P1：清理动态能力协议文档漂移

问题：

- 部分文档仍写着旧协议，例如 `capability.kind=skill/subgraph/none` 或 selector 固定返回 `toograph_page_operation_workflow`。
- 这些描述会误导后续开发，把已经废弃的页面操作 workflow 分支重新引回来。

需要修正：

- `AGENTS.md`：将动态能力 state 的 `kind` 统一为 `action/subgraph/tool/none`；说明 `skill` 是历史术语，不在当前动态能力协议中。
- `README.md`：更新官方 Action、能力选择器和 Buddy 运行路径说明，删除“selector 固定选择页面操作 workflow”的旧描述。
- `docs/future/buddy-autonomous-agent-roadmap.md`：修正“capability.kind=subgraph 的用户体验是可见运行目标模板”和“selector 固定页面操作入口”等旧段落。
- `action/official/toograph_capability_selector/ACTION.md`：改为描述基于 requirement 与 candidates 返回单个互斥 capability。
- 相关测试或 eval 描述中如果仍把 selector 绑定到页面操作 workflow，也要同步更新。

验收标准：

- 仓库中不再出现“selector 固定返回 `toograph_page_operation_workflow`”作为当前规则的描述。
- 当前架构文档和官方 Action 文档对动态能力 `kind` 的描述一致。
- 文档明确区分 Action、Tool、Subgraph、历史 Skill 叫法和未来可能的新 Skill 概念。

## P1：处理遗留 `buddy_visible_subgraph_result_adapter`

问题：

- `buddy_visible_subgraph_result_adapter` 仍存在，并且 manifest 和文档仍描述旧的页面操作 workflow 适配路径。
- 如果它已经不在官方 Buddy 模板中使用，继续保留会制造能力选择噪音。

可选处理方向：

- 删除该 Action 包及只服务于它的测试/eval 描述。
- 或保留但显式标记为 legacy/internal/deprecated，并确保能力选择器不会把它当作当前可选能力。

验收标准：

- 官方 Buddy 模板不依赖旧 adapter。
- 能力候选、README 和 roadmap 不把旧 adapter 当作当前路径。
- 如果保留，Action 文档必须说明仅用于读取旧运行记录或兼容旧数据，不能作为新运行链路。

## P2：运行树 API 与 batch group 摘要统一

问题：

- RunDetail 前端已经能对 child run 做 batch group 折叠。
- 如果 Buddy 也需要同样展示，不能让两个 UI 各自维护不一致的分组逻辑。

目标：

- 建立共享的运行树 display model，或由后端 `/api/runs/{run_id}/tree` 返回 batch group summary。
- batch group summary 至少包含 group id、label、child count、status counts、started/ended 时间、errors/warnings 摘要。

验收标准：

- RunDetail 和 Buddy 对同一 run tree 的 batch group 展示一致。
- 新增测试覆盖 batch group summary 的排序、状态统计和空/失败 item。

## P2：启动端口释放策略的边界确认

现状：

- `npm start` / `scripts/start.mjs` 已遵守单端口模型，不会因为 `3477` 被占用就自动换端口。
- 当前脚本只会释放能安全识别为 TooGraph 的进程；如果 `3477` 被未知进程占用，会报告 PID/command 并停止。

待确认：

- 是否需要扩展“安全识别”规则，例如识别 bare `uvicorn app.main:app --port 3477` 但 cwd 信息缺失的情况。
- 如果扩展，必须避免误杀其他项目或用户手动启动的非 TooGraph 服务。

验收标准：

- 已知 TooGraph backend/frontend/root 进程占用 `3477` 时，`npm start` 能释放并重启。
- 未知进程占用 `3477` 时，不启动第二端口，并给出明确 PID/command。
- 任何新增识别规则都有单元测试覆盖，不依赖模糊命令字符串误杀。

## P2：收敛旧计划和路线图

问题：

- 旧实现计划中部分任务被标为完成，但更深的验收项仍有缺口，例如 child run resume 和 Buddy 展开真实运行树。
- 这类计划如果继续存在，会让后续审查误以为所有目标已经完成。

目标：

- 已完成的一次性计划保留为历史时，应明确指向本文的剩余工作。
- 长期路线图只保留仍然有效的约束和未来工作，不维护逐日状态。

验收标准：

- 旧计划不会和本文冲突。
- `docs/future/` 中关于动态能力、运行树和 Buddy 胶囊的目标描述一致。

## 建议开发顺序

1. 先实现 child run resume：这是运行树可信度的底层前提。
2. 再把 Buddy 胶囊展开态接入真实 run tree，并复用 batch group 折叠逻辑。
3. 同步清理协议文档、README、Action 文档和旧 adapter。
4. 最后决定是否扩展端口释放识别规则，并收敛旧计划引用。

## 建议验证集

- 后端：`PYTHONPATH=backend pytest backend/tests/test_run_tree_store.py backend/tests/test_routes_runs.py backend/tests/test_subgraph_node_system.py backend/tests/test_node_handlers_runtime.py backend/tests/test_batch_node_system.py backend/tests/test_toograph_capability_selector_action.py backend/tests/test_node_system_validator_actions.py -q`
- 前端：`node --test frontend/src/api/runs.test.ts frontend/src/pages/runDetailModel.test.ts frontend/src/pages/RunDetailPage.structure.test.ts frontend/src/buddy/BuddyWidget.structure.test.ts frontend/src/buddy/buddyOutputTrace.test.ts frontend/src/buddy/buddyOutputTraceTree.test.ts frontend/src/buddy/buddyMessageMetadata.test.ts`
- UI：涉及 Buddy 展开态或运行详情时，用 `npm start` 在 `http://127.0.0.1:3477` 做一次浏览器截图或手动观察。
