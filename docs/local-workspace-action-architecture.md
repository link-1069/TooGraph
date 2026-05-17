# 本地工作区 Action 架构判断

本文记录 TooGraph 本地文件编辑与可执行程序运行能力的 Action 边界判断。它参考 `demo/agent-framework-lab/` 中对成熟 Agent 文件编辑和命令执行链路的调研结论，并对照当前官方 Action 实现，作为后续改造 `local_workspace_executor`、`toograph_script_tester` 和相关底层 runtime primitive 的架构参考。

调研日期：2026-05-22

## 1. 结论

当前不建议把 `local_workspace_executor` 立即拆成多个用户可选 Action。更合适的方向是：

```text
对图和用户保持少量清晰 Action
  local_workspace_executor: 本地工作区单次低层操作入口
  toograph_script_tester: 临时测试工作区和测试命令运行入口

在 Action 内部拆清 operation 协议
  read / list / search / edit / write / execute

在后端或 Action 包内共享底层 primitives
  path policy / file snapshot / text edit / full write / command execution / activity events
```

理由是 TooGraph 的 Action 不是隐藏工具面板，而是 LLM 节点一次绑定的一项显式能力。若把 read、list、search、edit、write、execute 全部拆成用户级 Action，一个普通流程会被迫拆成过多节点，Buddy 能力选择也会变得碎片化。拆分应该优先发生在协议和实现层，而不是先发生在产品层。

## 2. 当前相似能力

### `local_workspace_executor`

当前最接近通用本地文件和脚本能力。它已经支持：

- `read`：读取一个 UTF-8 文本文件。
- `list`：列出路径下可读文本文件。
- `search`：在路径下搜索文本。
- `write`：在白名单根目录中创建或覆盖一个文本文件。
- `execute`：执行白名单根目录中的脚本文件。

它也有有价值的基础边界：

- Action manifest 声明 `file_read`、`file_write`、`subprocess` 权限。
- `before_llm.py` 可以根据 runtime context 预读候选路径。
- `after_llm.py` 对路径做仓库内约束、拒绝 `.git`、`.env`、`backend/data/settings`。
- 写入、读取、搜索和命令运行都会返回 activity events。

主要不足：

- `edit` 目前等同于 `write`，普通局部编辑要求模型输出完整文件内容。
- `write` 缺少 read-before-write 快照、mtime/hash stale 检查、唯一匹配和结构化 patch。
- `before_llm.py` 的预读只进入提示词，不是 runtime-owned `readFileState`。
- `execute` 只按脚本路径执行，缺少命令解析、只读命令识别、后台任务和大输出 artifact。
- 权限暂停粒度仍是 Action 级，read-only 操作和 write/execute 操作共享同一风险标签。

### `toograph_script_tester`

它不是通用本地执行器，但更接近“受控运行程序”的好模式：

- 在临时目录写入 LLM 生成的最小测试文件。
- 运行命令参数数组，而不是任意 shell 字符串。
- 使用命令 allowlist。
- 限制文件路径只能留在临时测试目录内。
- 返回命令、退出码、stdout、stderr、耗时和 activity events。

它应继续保留为独立 Action，因为它的用户意图是“生成测试并验证脚本行为”，不是“操作 TooGraph 工作区中的明确路径”。但它的路径校验、命令执行、输出裁剪和错误格式应与 `local_workspace_executor` 共享底层实现。

## 3. 拆分原则

不要按底层函数机械拆用户级 Action。用户级 Action 应按产品语义和权限边界拆分。

适合保留在同一个 Action 内的情况：

- 都是一次明确的本地工作区低层操作。
- LLM 只需要选择一个 operation 并填结构化参数。
- 权限和审计可以在 operation 层细分。
- 输出可以统一成 `success`、`result`、`activity_events`，并由下游 state 接收。

适合拆成多个用户级 Action 的情况：

- 权限边界明显不同，例如只读能力与执行本地进程需要完全不同的审批体验。
- 输出契约明显不同，例如文件编辑需要 patch/diff/revision，命令执行需要 stdout/stderr/exit code/task id。
- 能力选择器经常因为职责过宽而选错。
- 用户需要在 UI 中单独启用或禁用某类能力，例如允许读写但禁止执行。
- 某个能力已经变成多步工作流，而不再是一次低层操作。

因此短期不拆 `local_workspace_executor`，中期可以在证据充分时拆成两个用户级 Action：

```text
local_file_operator
  read / list / search / edit / write

local_script_runner
  execute / background task / output artifact
```

不建议拆成 `read_file_action`、`edit_file_action`、`write_file_action`、`execute_action` 这种过细产品层 Action。底层 primitives 可以这么拆，用户可见能力不应这么碎。

## 4. 推荐目标结构

`local_workspace_executor` 保持一个 Action，但内部 operation 协议升级为：

```text
operation:
  read
  list
  search
  edit
  write
  execute
```

推荐底层模块或 helper：

| 模块 | 职责 |
| --- | --- |
| `workspace_paths` | 归一化仓库相对路径、拒绝危险根、校验读写执行根 |
| `workspace_read` | 文本读取、大小限制、二进制拒绝、生成文件快照 |
| `workspace_edit` | `old_string -> new_string`、唯一匹配、replace_all、stale 检查、patch |
| `workspace_write` | 新建文件和完整覆盖；覆盖已有文件前要求完整快照 |
| `workspace_execute` | 脚本/命令执行、timeout、输出裁剪、后续后台任务接口 |
| `workspace_events` | 统一 activity events、错误类型、diff 摘要和 artifact 引用 |

这个结构能保留 TooGraph 的图优先产品体验，同时把文件和命令副作用收敛到更可测试的受控原语。

## 5. 文件编辑目标协议

普通编辑应新增 `edit`，不要继续通过完整 `write` 表达。

建议 LLM 输出：

```json
{
  "operation": "edit",
  "path": "action/user/example/after_llm.py",
  "old_string": "timeout=30",
  "new_string": "timeout=60",
  "replace_all": false
}
```

运行时应校验：

- `path` 留在仓库内，并符合写入根策略。
- 文件是可读 UTF-8 文本，不是二进制或超大文件。
- 目标文件在本轮或前置节点中有完整读取快照。
- 当前文件 mtime/hash 与快照一致；不一致则拒绝 stale write。
- `old_string` 能匹配且默认唯一。
- `replace_all=false` 时多处匹配必须失败并要求更多上下文。
- 写入后返回结构化 patch/diff、字符和行数摘要、activity event。

完整 `write` 应保留，但定位为：

- 新建文件。
- 生成完整小文件。
- 明确需要整体覆盖的文件。

覆盖已有文件时仍应要求完整快照和 stale 检查。

## 6. 命令执行目标协议

`execute` 短期可以继续保持“执行一个明确路径指向的脚本”，但应逐步吸收 `toograph_script_tester` 的更稳做法：

- 命令使用参数数组或由路径和运行时类型生成参数数组，不让模型输出任意 shell 字符串。
- 执行根与写入根分开配置。
- 记录 cwd、命令、退出码、stdout/stderr 字符数、耗时和错误类型。
- 大输出写入 artifact，只把预览和路径放进 `result`。
- 后续如支持长任务，新增 task id、output artifact、stop/read output operation，而不是阻塞 LLM 节点。
- 对 read-only 命令、写文件命令、安装依赖、测试命令分别做不同风险分类。

不建议把 shell 作为默认逃生口。若确实需要更通用命令能力，应先有命令解析、重定向检查、路径策略、审批预览和输出 artifact。

## 7. 权限和审计目标

当前 Action 级权限声明仍应保留，但低层审批应按 operation 展示更具体的风险：

| Operation | 默认风险 |
| --- | --- |
| `read` / `list` / `search` | 只读，通常不触发写入或执行确认 |
| `edit` / `write` | 文件写入，需要展示路径和 diff/摘要 |
| `execute` | 子进程执行，需要展示路径、命令、cwd 和权限原因 |

activity events 应从“Action 调用成功/失败”下钻到具体副作用：

- `file_read`
- `file_list`
- `file_search`
- `file_edit`
- `file_write`
- `command`

文件写入事件应包含 path、operation、added/removed、patch 摘要、stale check 结果。命令事件应包含 command、cwd、exit_code、duration、stdout/stderr 摘要和 artifact refs。

## 8. 推荐改造顺序

1. 保留 `local_workspace_executor` 的 Action key，不破坏现有模板。
2. 在 `local_workspace_executor` 中新增 `edit` operation 和对应 schema 字段。
3. 抽出路径策略、文本读取、命令执行、activity event helper，先让 `local_workspace_executor` 使用。
4. 给 `toograph_script_tester` 复用命令执行和错误格式 helper。
5. 引入文件快照和 stale write 防护；覆盖已有文件必须经过完整快照。
6. 让 `edit` 返回 patch/diff，更新运行详情和 Buddy 胶囊展示。
7. 将权限暂停从 Action 级逐步扩展到 operation 级风险展示。
8. 如果使用证据显示职责过宽，再拆 `local_file_operator` 与 `local_script_runner`。

## 9. 非目标

- 不把单个 Action 做成隐藏多轮 Agent。
- 不让 Action 自己决定后续图流程。
- 不让模型输出任意 shell 字符串作为默认执行协议。
- 不让模型用完整文件覆盖表达普通局部编辑。
- 不把 diff 当作主要修改协议；diff 是审计结果，编辑意图应是结构化参数。
- 不把本地 runtime 状态、日志、构建产物或机器配置写入仓库。
