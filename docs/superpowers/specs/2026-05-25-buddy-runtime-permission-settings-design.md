# Buddy Runtime Permission Settings Design

## Context

Buddy Home currently contains `policy.json`. The file mixes three concerns:

- Runtime permission mode: `graph_permission_mode`.
- Behavioral boundary text: `behavior_boundaries`.
- Communication preference text: `communication_preferences`.

The current Buddy context pack and official Buddy templates include `policy.json` in the local-folder context. That means LLM nodes can see permission and boundary text. This is the wrong authority model: LLMs should decide what capability is useful, but code should decide whether a capability may run automatically, must pause for approval, or is hard-blocked.

The existing runtime already has the core enforcement path. Buddy graph construction writes `graph_permission_mode` into graph metadata, and backend permission approval checks Action manifest permissions before invoking risky Actions. The `local_workspace_executor` also has deterministic hard checks for paths, stale file snapshots, edit uniqueness, and execute allowlists.

## Decision

Move Buddy permission mode out of Buddy Home and into a global persistent runtime setting.

The setting controls the default Buddy run mode:

- `ask_first`: risky operations pause for human approval.
- `full_access`: risky operations may proceed without the approval pause, while Action-level hard guards still apply.

Buddy Home should no longer be the source of permission mode. Buddy Home should also stop exposing `policy.json` to LLM context. Long-lived Buddy context remains focused on identity, user profile, and curated memory.

## Recommendation

Use a runtime settings source, not `buddy_home/policy.json`.

Compared with keeping `policy.json` as a runtime-only file, putting the mode in runtime settings gives the cleanest boundary:

- Buddy Home remains human-readable memory/profile context.
- Runtime settings remain machine-owned app configuration.
- LLM context does not contain permission policy text.
- The existing graph metadata enforcement path can continue to consume a plain mode value.

## Architecture

### Runtime Setting

Add a global persisted setting for Buddy permission mode, for example `buddy_permission_mode`.

The setting should live in the existing settings storage path or an equivalent runtime configuration store. It should not live in Buddy Home, because Buddy Home is loaded as durable context for Buddy graphs.

The setting's normalized values are:

- `ask_first`
- `full_access`

Legacy values should normalize as:

- `approval`, `advisory`, unknown -> `ask_first`
- `unrestricted` -> `full_access`

### Buddy Widget

The Buddy floating widget should read the global setting when it initializes.

When the user changes the mode in the widget, the widget should persist the new value globally. The next app load and the next Buddy session should use the same mode.

When starting a Buddy run, graph construction should copy the current global mode into graph metadata:

- `metadata.graph_permission_mode`
- compatibility flags only if still needed by existing runtime code

This metadata is runtime input, not LLM context.

### LLM Context

Buddy Home context should no longer include `policy.json`.

The default Buddy Home local-folder selection should include:

- `AGENTS.md`
- `SOUL.md`
- `USER.md`
- `MEMORY.md`

It should not include permission settings or runtime policy text.

If communication preferences are still useful as long-term user preference, they should move into `USER.md` or `MEMORY.md` as ordinary preference context, not a JSON policy object.

### Enforcement

The runtime remains the authority for permission pauses.

The LLM selects a capability such as `local_workspace_executor`, `toograph_page_operator`, or a subgraph. It does not need to know whether a later step will pause for approval.

The backend checks:

- current graph metadata permission mode
- Action manifest permissions
- existing pending approval state

The Action still performs deterministic operation validation after approval mode is resolved. `full_access` skips the approval pause; it must not disable Action hard guards.

## Existing Gaps

Local file operations already have a functional enforcement path:

- `local_workspace_executor` supports `read`, `list`, `search`, `edit`, `write`, and `execute`.
- `edit` uses `old_string`, `new_string`, uniqueness checks, hash and mtime stale checks, and patch activity events.
- `write` and `execute` have path allowlists and denied roots.

The main gap is risk granularity. Permission approval is currently Action-level. Because `local_workspace_executor` declares `file_write` and `subprocess`, read-only operations can still inherit the Action's risky permission profile. Future work should move approval display and pause logic toward operation-level risk.

Page and graph UI operations are a separate chain:

- `toograph_page_operator` emits `virtual_ui_operation` requests.
- The frontend executes visible operation playback and resumes the run with an operation result.
- Operation journal records the chain.

`virtual_ui_operation` is not currently part of the same risky permission approval set. If graph editing should obey the global `ask_first/full_access` mode, it needs an explicit runtime gate or a permission classification update for graph edit operations.

## Migration

The migration should be conservative:

1. Read the existing `buddy_home/policy.json.graph_permission_mode` once if no new runtime setting exists.
2. Persist the normalized value into the new runtime setting.
3. Stop injecting `policy.json` into Buddy graph inputs.
4. Keep reading old `policy.json` only for compatibility in the Buddy page until the UI is revised.
5. Eventually remove `policy.json` from the normative Buddy Home shape.

The migration must not delete user data automatically.

## UI Changes

The Buddy widget mode control becomes the primary global control for Buddy permission mode.

The Buddy page should no longer present `policy.json` as Buddy Home policy. If a settings surface is needed, it should link to or reuse the global runtime setting.

The UI copy should make the behavior concrete:

- Ask first: risky Actions pause before execution.
- Full access: risky Actions run without the approval pause, but hard safety checks still apply.

## Testing

Minimum verification for implementation:

- Unit test that Buddy graph construction uses the persisted global mode.
- Unit test that Buddy Home context selection excludes `policy.json`.
- Backend test that permission approval still pauses for `file_write`/`subprocess` in `ask_first`.
- Backend test that `full_access` skips the pause but Action hard validation still rejects forbidden paths.
- UI test that changing the widget mode persists and survives reload or reinitialization.
- Regression test that existing legacy values normalize to supported modes.

## Non-Goals

This design does not replace Action-level hard validation.

This design does not make LLM prompt text a security boundary.

This design does not require deleting `policy.json` immediately.

This design does not yet implement operation-level approval granularity for `local_workspace_executor` or graph edit playback.

## Confirmed Decision

The global setting should be persistent across app sessions. The user confirmed this should not be a temporary per-widget session value.
