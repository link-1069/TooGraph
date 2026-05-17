# Run Tree Dynamic Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement the first production slice of the run tree design: dynamic capability protocol cleanup, child run records for graph-level subagents, run tree API support, and removal of the Buddy follow concept from the new path.

**Architecture:** Add run relation fields to persisted run records and route every graph-calling-graph execution through child run state creation. Preserve the current synchronous parent-node semantics first: the parent node creates a child run, executes it in-process with normal run persistence, then packages the public child outputs back into the parent state. UI tree rendering can consume the same run relation records through a shared `/api/runs/{run_id}/tree` endpoint.

**Tech Stack:** Python FastAPI backend, Node System LangGraph runtime, JSON run store, Vue frontend, pytest/unittest backend tests, frontend TypeScript build/tests.

---

## File Structure

- Modify `backend/app/core/runtime/state.py`: add run relation fields to `RunState` and `create_initial_run_state`.
- Create `backend/app/core/runtime/run_tree.py`: helpers for child run creation, run summaries, and batch group metadata.
- Modify `backend/app/core/schemas/run.py`: expose run relation fields and child summaries in API schemas.
- Modify `backend/app/core/storage/run_store.py`: add helpers to list children and build a run tree from JSON records.
- Modify `backend/app/api/routes_runs.py`: add `GET /api/runs/{run_id}/tree` and include direct children in `RunDetail`.
- Modify `backend/app/core/langgraph/runtime.py`: execute Subgraph node, dynamic subgraph capability, and batch subgraph worker as child runs.
- Modify `backend/app/core/compiler/validator.py`: reject legacy dynamic `kind: "skill"` capability state defaults.
- Modify `backend/app/core/runtime/node_handlers.py`: include `childRunId`/`child_run_id` in dynamic subgraph result packages and activity details.
- Modify `action/official/toograph_capability_selector/*`: stop hardcoding page operation and return `action/subgraph/tool/none` from catalog-like input.
- Modify `action/official/toograph_context_fanout/after_llm.py`: produce discoverable template/action/tool candidates instead of one fixed page-operation candidate.
- Modify `graph_template/official/buddy_capability_loop/template.json` and embedded copy in `graph_template/official/buddy_autonomous_loop/template.json`: route subgraphs through the generic dynamic executor, not visible page operation.
- Modify `frontend/src/buddy/BuddyWidget.vue`: remove follow toggle/storage and keep template execution on the background path.
- Modify `frontend/src/buddy/buddyOutputTrace.ts`: expose child run ids from activity details as trace evidence links.
- Modify `frontend/src/pages/RunDetailPage.vue` and `frontend/src/pages/runDetailModel.ts`: render persisted child run trees with collapsed batch groups.
- Update tests under `backend/tests`, `frontend/src`, and `frontend/e2e` for the new protocol and run tree behavior.

## Task 1: Run Relation Schema And Store

**Files:**
- Modify: `backend/app/core/runtime/state.py`
- Create: `backend/app/core/runtime/run_tree.py`
- Modify: `backend/app/core/schemas/run.py`
- Modify: `backend/app/core/storage/run_store.py`
- Test: `backend/tests/test_run_tree_store.py`

- [x] **Step 1: Write failing tests for root/child run metadata and tree loading**

Create `backend/tests/test_run_tree_store.py` with tests that:

- build a root run and child run using the new helper;
- assert child fields `parent_run_id`, `root_run_id`, `parent_node_id`, `invocation_kind`, `invocation_key`, `run_depth`, and `run_path`;
- save the runs in a temporary run directory;
- assert `build_run_tree("run_root")` returns the root with nested children.

- [x] **Step 2: Run the focused failing test**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_run_tree_store.py -q
```

Expected: fail because `run_tree.py` and store helpers do not exist yet.

- [x] **Step 3: Implement run relation fields and store helpers**

Add relation fields with empty defaults to `create_initial_run_state`. Implement `create_child_run_state(parent_state, graph_id, graph_name, parent_node_id, invocation_kind, invocation_key, batch_group_id="", batch_item_index=None, batch_item_label="")`. Add `list_child_runs(parent_run_id)` and `build_run_tree(run_id)` to `run_store.py`.

- [x] **Step 4: Verify Task 1**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_run_tree_store.py -q
```

Expected: pass.

## Task 2: Child Run API

**Files:**
- Modify: `backend/app/core/schemas/run.py`
- Modify: `backend/app/api/routes_runs.py`
- Test: `backend/tests/test_routes_runs.py`

- [x] **Step 1: Write failing API tests**

Add tests that seed a root and child run JSON record, then assert:

- `GET /api/runs/{root}/tree` returns a tree with one child;
- `GET /api/runs/{root}` includes direct child summaries;
- `/api/runs` still lists root and child records unless filtered later.

- [x] **Step 2: Run the focused failing tests**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_routes_runs.py -q
```

Expected: fail for the missing `/tree` route or missing children field.

- [x] **Step 3: Implement API schema and route**

Add `RunChildSummary` and `RunTreeNode` models. Include `children` in `RunDetail`. Add `GET /api/runs/{run_id}/tree` using `build_run_tree`.

- [x] **Step 4: Verify Task 2**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_routes_runs.py -q
```

Expected: pass.

## Task 3: Dynamic Subgraph Child Runs

**Files:**
- Modify: `backend/app/core/langgraph/runtime.py`
- Modify: `backend/app/core/runtime/node_handlers.py`
- Test: `backend/tests/test_subgraph_node_system.py`
- Test: `backend/tests/test_node_handlers_runtime.py`

- [x] **Step 1: Write failing runtime tests**

Update dynamic subgraph and ordinary Subgraph node tests to assert:

- a child run id is generated;
- the child run has `parent_run_id` equal to parent run id;
- the parent result package includes `childRunId` and `child_run_id`;
- parent `subgraph_status_map` remains populated for compatibility.

- [x] **Step 2: Run focused failing tests**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_subgraph_node_system.py backend/tests/test_node_handlers_runtime.py -q
```

Expected: fail on missing child run metadata/result package fields.

- [x] **Step 3: Implement child run execution for subgraphs**

In `runtime.py`, replace subgraph initial state creation with `create_child_run_state`, set `runtime_backend="langgraph"`, store the child `graph_snapshot`, initialize child `node_status_map`, save it, and call `execute_node_system_graph_langgraph(..., persist_progress=True, save_final_run=True)`. Keep copying child `node_status_map` into the parent `subgraph_status_map` until the UI fully moves to run tree.

- [x] **Step 4: Add child run ids to dynamic packages and events**

Pass `child_run_id` through execution result dictionaries. Add `childRunId`, `child_run_id`, and `triggered_run_id` to dynamic subgraph `result_package`. Add the same ids to `capability_outputs` and `subgraph_invocation` activity details.

- [x] **Step 5: Verify Task 3**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_subgraph_node_system.py backend/tests/test_node_handlers_runtime.py -q
```

Expected: pass.

## Task 4: Capability Protocol Cleanup

**Files:**
- Modify: `backend/app/core/compiler/validator.py`
- Modify: `action/official/toograph_capability_selector/action.json`
- Modify: `action/official/toograph_capability_selector/after_llm.py`
- Modify: `action/official/toograph_context_fanout/after_llm.py`
- Test: `backend/tests/test_toograph_capability_selector_action.py`
- Test: `backend/tests/test_toograph_context_fanout_action.py`
- Test: `backend/tests/test_node_system_validator_actions.py`

- [x] **Step 1: Write failing protocol tests**

Add or update tests so:

- selector returns `none` when no candidate matches;
- selector returns `advanced_web_research_loop` for AI news/research queries when present in candidates;
- selector returns `toograph_page_operation_workflow` only for page operation queries;
- dynamic `kind: "skill"` is rejected or ignored with a validation error;
- context fanout emits multiple discoverable candidates and no legacy `skill` kind.

- [x] **Step 2: Run focused failing tests**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_toograph_capability_selector_action.py backend/tests/test_toograph_context_fanout_action.py backend/tests/test_node_system_validator_actions.py -q
```

Expected: fail because selector/fanout are fixed to page operation.

- [x] **Step 3: Implement selector and fanout changes**

Change selector manifest to accept `requirement`, `capability_candidates`, and optional `origin`. Implement deterministic selection in `after_llm.py` using provided candidates first, then a small built-in fallback catalog. Return `{"kind":"none"}` when no candidate is suitable. Update context fanout to read `graph_template/settings.json`, template JSON metadata, `action/settings.json`, and `tool/settings.json` where available.

- [x] **Step 4: Verify Task 4**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_toograph_capability_selector_action.py backend/tests/test_toograph_context_fanout_action.py backend/tests/test_node_system_validator_actions.py -q
```

Expected: pass.

## Task 5: Buddy Template Route Cleanup

**Files:**
- Modify: `graph_template/official/buddy_capability_loop/template.json`
- Modify: `graph_template/official/buddy_autonomous_loop/template.json`
- Test: `backend/tests/test_template_layouts.py`

- [x] **Step 1: Write failing template assertions**

Update tests to assert Buddy routes selected `subgraph` to `execute_capability`, no longer to `run_visible_template_operation`, and selector instructions do not mention fixed page operation.

- [x] **Step 2: Run focused failing tests**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_template_layouts.py -q
```

Expected: fail until template JSON is updated.

- [x] **Step 3: Update templates**

Remove the page-operation special condition from the capability loop path. Route `capability_found_condition.true` to `execute_capability`. Keep page operation as a normal selectable subgraph; it will run through dynamic subgraph child run execution.

- [x] **Step 4: Verify Task 5**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_template_layouts.py -q
```

Expected: pass.

## Task 6: Buddy Follow UI Removal And Tree Hook

**Files:**
- Modify: `frontend/src/buddy/BuddyWidget.vue`
- Modify: `frontend/src/buddy/buddyOutputTrace.ts`
- Modify: `frontend/src/pages/RunDetailPage.vue`
- Modify: `frontend/src/pages/runDetailModel.ts`
- Modify: `frontend/src/types/run.ts`
- Modify: `frontend/src/api/runs.ts`
- Test: `frontend/src/buddy/BuddyWidget.structure.test.ts`
- Test: `frontend/src/buddy/buddyOutputTrace.test.ts`
- Test: `frontend/src/pages/RunDetailPage.structure.test.ts`
- Test: `frontend/src/pages/runDetailModel.test.ts`
- Test: `frontend/e2e/buddy-follow-mode.spec.ts`

- [x] **Step 1: Write failing frontend tests**

Update structure tests to assert the follow storage key, follow toggle class, and follow-control UI are absent. Add trace/tree tests for child run evidence and collapsed batch groups.

- [x] **Step 2: Run focused failing frontend tests**

Run:

```bash
node --test frontend/src/buddy/BuddyWidget.structure.test.ts frontend/src/buddy/buddyOutputTrace.test.ts frontend/src/pages/RunDetailPage.structure.test.ts frontend/src/pages/runDetailModel.test.ts
```

Expected: fail until UI and trace parsing are updated.

- [x] **Step 3: Remove follow UI and add child run trace support**

Delete follow preference state, storage access, toggle markup, and follow-specific branch logic. Preserve background execution behavior as the only path. Parse child run ids from activity details into trace evidence links and render `/api/runs/{run_id}/tree` on run details with batch groups collapsed.

- [x] **Step 4: Verify Task 6**

Run:

```bash
node --test frontend/src/buddy/BuddyWidget.structure.test.ts frontend/src/buddy/buddyOutputTrace.test.ts frontend/src/pages/RunDetailPage.structure.test.ts frontend/src/pages/runDetailModel.test.ts
```

Expected: pass.

## Task 7: Final Verification, Start, Commit, Push

**Files:**
- All modified files.

- [x] **Step 1: Run backend focused suite**

Run:

```bash
PYTHONPATH=backend pytest backend/tests/test_run_tree_store.py backend/tests/test_routes_runs.py backend/tests/test_subgraph_node_system.py backend/tests/test_node_handlers_runtime.py backend/tests/test_batch_node_system.py backend/tests/test_toograph_capability_selector_action.py backend/tests/test_toograph_context_fanout_action.py backend/tests/test_node_system_validator_actions.py backend/tests/test_template_layouts.py -q
```

Expected: pass.

- [x] **Step 2: Run frontend build/test target**

Run:

```bash
cd frontend && npm run build
```

Expected: pass.

- [x] **Step 3: Restart TooGraph**

Run:

```bash
npm start
```

Expected: starts on `http://127.0.0.1:3477`.

- [x] **Step 4: Commit and push**

Run:

```bash
git status --short
git add <changed files>
git commit -m "实现运行树与动态能力执行"
git push origin feat/run-tree-dynamic-capabilities
```

Expected: branch pushed with Chinese commit message.
