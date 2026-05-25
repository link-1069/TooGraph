# Buddy Runtime Permission Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Buddy permission mode from Buddy Home policy context into a global persisted runtime setting, then stop injecting `policy.json` into Buddy LLM context and official Buddy templates.

**Architecture:** Store the global Buddy permission mode in app settings under `buddy_runtime.permission_mode`, expose a small settings API for the floating Buddy widget, and keep copying the effective mode into graph metadata at run construction time. LLM nodes see Buddy Home identity/profile/memory context only; backend permission approval and Action hard guards remain the enforcement authority.

**Tech Stack:** FastAPI/Pydantic backend settings routes, JSON settings storage, Vue 3 Composition API, Element Plus controls, Node test runner, Python unittest/pytest-compatible backend tests, TooGraph official JSON graph templates.

---

## Files And Responsibilities

- Modify `backend/app/api/routes_settings.py`: normalize Buddy permission mode, expose it in `/api/settings`, add dedicated `/api/settings/buddy-runtime` read/write endpoints, and migrate from legacy `buddy_home/policy.json` only when no app setting exists.
- Modify `backend/app/buddy/home.py`: stop treating `policy.json` as Buddy Home context for new context packs and default `AGENTS.md`; keep compatibility helpers/endpoints intact.
- Modify `backend/app/buddy/store.py`: stop listing legacy `policy.json` as a current Buddy Home file surface.
- Modify `frontend/src/types/settings.ts`: add `BuddyPermissionMode` and `buddy_runtime` payload types.
- Modify `frontend/src/api/settings.ts`: add `fetchBuddyRuntimeSettings()` and `updateBuddyRuntimeSettings()` helpers, and allow full settings updates to carry `buddy_runtime`.
- Create `frontend/src/buddy/useBuddyPermissionMode.ts`: centralize global mode hydration, normalization, save, and status state for the Buddy widget.
- Modify `frontend/src/buddy/BuddyWidget.vue`: replace local-only `buddyMode` with the persisted mode composable.
- Modify `frontend/src/buddy/buddyTemplateBindingModel.ts`: remove `policy.json` from default Buddy Home local-folder package.
- Modify official templates:
  - `graph_template/official/buddy_autonomous_loop/template.json`
  - `graph_template/official/buddy_autonomous_review/template.json`
  - `graph_template/official/buddy_context_compaction/template.json`
- Modify tests:
  - `backend/tests/test_settings_model_providers.py`
  - `backend/tests/test_buddy_routes.py`
  - `backend/tests/test_buddy_store.py`
  - `backend/tests/test_template_layouts.py`
  - `frontend/src/api/settings.test.ts`
  - `frontend/src/buddy/buddyTemplateBindingModel.test.ts`
  - `frontend/src/buddy/buddyChatGraph.test.ts`
  - `frontend/src/buddy/BuddyWidget.structure.test.ts`
  - `frontend/src/pages/BuddyPage.structure.test.ts`
- Modify docs:
  - `README.md`
  - `docs/README.md`

Do not automatically modify `graph_template/user/user_template_f6e878e73a/template.json`. It currently contains `policy.json`, but it is a user template. The implementation should leave it as user data and rely on the updated default builder plus official templates for new runs. If a later migration is wanted, make it explicit and reversible.

---

### Task 1: Backend Runtime Setting And Compatibility Migration

**Files:**
- Modify: `backend/app/api/routes_settings.py`
- Test: `backend/tests/test_settings_model_providers.py`

- [ ] **Step 1: Write failing backend settings tests**

Append these tests to `backend/tests/test_settings_model_providers.py` inside `SettingsModelProviderTests`:

```python
    def test_settings_payload_includes_buddy_runtime_permission_mode(self) -> None:
        catalog = {
            "default_text_model_ref": "local/current-text",
            "default_video_model_ref": "local/current-video",
            "providers": [],
            "provider_templates": [],
        }

        with patch("app.api.routes_settings.build_model_catalog", return_value=catalog):
            with patch("app.api.routes_settings.get_default_agent_thinking_level", return_value="medium"):
                with patch("app.api.routes_settings.get_default_agent_temperature", return_value=0.2):
                    with patch("app.api.routes_settings.get_tool_registry", return_value={}):
                        with patch("app.api.routes_settings.load_app_settings", return_value={"buddy_runtime": {"permission_mode": "full_access"}}):
                            payload = routes_settings._build_settings_payload(force_refresh_models=False)

        self.assertEqual(payload["buddy_runtime"], {"permission_mode": "full_access"})

    def test_update_settings_preserves_existing_buddy_runtime_when_omitted(self) -> None:
        saved_payload = {}

        def capture_save(payload: dict) -> dict:
            saved_payload.clear()
            saved_payload.update(payload)
            return payload

        existing_settings = {"buddy_runtime": {"permission_mode": "full_access"}}
        with patch("app.api.routes_settings.load_app_settings", return_value=existing_settings):
            with patch("app.api.routes_settings.save_app_settings", side_effect=capture_save):
                with patch("app.api.routes_settings._build_settings_payload", return_value={"ok": True}):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/settings",
                            json={
                                "model": {
                                    "text_model_ref": "local/text",
                                    "video_model_ref": "local/video",
                                },
                                "agent_runtime_defaults": {
                                    "model": "local/text",
                                    "thinking_enabled": True,
                                    "thinking_level": "medium",
                                    "temperature": 0.2,
                                },
                            },
                        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved_payload["buddy_runtime"], {"permission_mode": "full_access"})

    def test_buddy_runtime_endpoint_persists_normalized_permission_mode(self) -> None:
        saved_payload = {}

        def capture_save(payload: dict) -> dict:
            saved_payload.clear()
            saved_payload.update(payload)
            return payload

        with patch("app.api.routes_settings.load_app_settings", return_value={}):
            with patch("app.api.routes_settings.save_app_settings", side_effect=capture_save):
                with TestClient(app) as client:
                    response = client.post("/api/settings/buddy-runtime", json={"permission_mode": "unrestricted"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"permission_mode": "full_access"})
        self.assertEqual(saved_payload["buddy_runtime"], {"permission_mode": "full_access"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest backend/tests/test_settings_model_providers.py -q
```

Expected: FAIL because `buddy_runtime` payload and `/api/settings/buddy-runtime` do not exist yet.

- [ ] **Step 3: Implement backend normalization and endpoints**

In `backend/app/api/routes_settings.py`, add imports near existing imports:

```python
from app.buddy.home import POLICY_PATH, get_default_buddy_home_dir
from app.core.storage.json_file_utils import read_json_file
```

Add constants and helpers after the Pydantic payload classes:

```python
BUDDY_PERMISSION_MODE_ASK_FIRST = "ask_first"
BUDDY_PERMISSION_MODE_FULL_ACCESS = "full_access"
BUDDY_PERMISSION_MODE_DEFAULT = BUDDY_PERMISSION_MODE_ASK_FIRST


class BuddyRuntimeSettingsPayload(BaseModel):
    permission_mode: str = Field(default=BUDDY_PERMISSION_MODE_DEFAULT, alias="permission_mode")

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    @property
    def normalized_permission_mode(self) -> str:
        return normalize_buddy_permission_mode(self.permission_mode)


def normalize_buddy_permission_mode(value: object) -> str:
    mode = str(value or "").strip()
    if mode in {BUDDY_PERMISSION_MODE_FULL_ACCESS, "unrestricted"}:
        return BUDDY_PERMISSION_MODE_FULL_ACCESS
    return BUDDY_PERMISSION_MODE_ASK_FIRST


def _normalize_buddy_runtime_settings(value: object) -> dict[str, str]:
    payload = value if isinstance(value, dict) else {}
    return {
        "permission_mode": normalize_buddy_permission_mode(payload.get("permission_mode")),
    }


def _read_legacy_buddy_policy_permission_mode() -> str:
    policy_path = get_default_buddy_home_dir() / POLICY_PATH
    policy = read_json_file(policy_path, default={})
    if not isinstance(policy, dict):
        return BUDDY_PERMISSION_MODE_DEFAULT
    return normalize_buddy_permission_mode(policy.get("graph_permission_mode"))


def get_saved_buddy_runtime_settings(settings: dict | None = None) -> dict[str, str]:
    source = settings if isinstance(settings, dict) else load_app_settings()
    raw_runtime = source.get("buddy_runtime")
    if isinstance(raw_runtime, dict) and "permission_mode" in raw_runtime:
        return _normalize_buddy_runtime_settings(raw_runtime)
    if "buddy_permission_mode" in source:
        return {"permission_mode": normalize_buddy_permission_mode(source.get("buddy_permission_mode"))}
    return {"permission_mode": _read_legacy_buddy_policy_permission_mode()}


def save_buddy_runtime_settings(payload: BuddyRuntimeSettingsPayload) -> dict[str, str]:
    existing_settings = load_app_settings()
    next_settings = dict(existing_settings)
    next_settings.pop("buddy_permission_mode", None)
    next_settings["buddy_runtime"] = {"permission_mode": payload.normalized_permission_mode}
    save_app_settings(next_settings)
    return get_saved_buddy_runtime_settings(next_settings)
```

Modify `SettingsUpdatePayload`:

```python
class SettingsUpdatePayload(BaseModel):
    model: SettingsModelPayload
    agent_runtime_defaults: AgentRuntimeDefaultsPayload = Field(alias="agent_runtime_defaults")
    model_providers: dict[str, SettingsModelProviderPayload] | None = Field(default=None, alias="model_providers")
    buddy_runtime: BuddyRuntimeSettingsPayload | None = Field(default=None, alias="buddy_runtime")

    model_config = ConfigDict(populate_by_name=True)
```

Modify `_build_settings_payload()` to include:

```python
        "buddy_runtime": get_saved_buddy_runtime_settings(),
```

Modify `update_settings_endpoint()` after `next_settings.update(...)`:

```python
    existing_buddy_runtime = get_saved_buddy_runtime_settings(existing_settings)
    next_settings["buddy_runtime"] = (
        {"permission_mode": payload.buddy_runtime.normalized_permission_mode}
        if payload.buddy_runtime is not None
        else existing_buddy_runtime
    )
    next_settings.pop("buddy_permission_mode", None)
```

Add dedicated endpoints after `update_settings_endpoint()`:

```python
@router.get("/buddy-runtime")
def get_buddy_runtime_settings_endpoint() -> dict[str, str]:
    return get_saved_buddy_runtime_settings()


@router.post("/buddy-runtime")
def update_buddy_runtime_settings_endpoint(payload: BuddyRuntimeSettingsPayload) -> dict[str, str]:
    return save_buddy_runtime_settings(payload)
```

- [ ] **Step 4: Run backend settings tests**

Run:

```bash
pytest backend/tests/test_settings_model_providers.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/app/api/routes_settings.py backend/tests/test_settings_model_providers.py
git commit -m "添加伙伴运行权限全局设置"
```

---

### Task 2: Frontend Settings API Types

**Files:**
- Modify: `frontend/src/types/settings.ts`
- Modify: `frontend/src/api/settings.ts`
- Test: `frontend/src/api/settings.test.ts`

- [ ] **Step 1: Write failing frontend API tests**

In `frontend/src/api/settings.test.ts`, update the import:

```ts
import {
  discoverModelProviderModels,
  fetchBuddyRuntimeSettings,
  fetchOpenAICodexAuthStatus,
  importOpenAICodexCliAuth,
  logoutOpenAICodexAuth,
  pollOpenAICodexAuth,
  pollOpenAICodexBrowserAuth,
  startOpenAICodexBrowserAuth,
  startOpenAICodexAuth,
  updateBuddyRuntimeSettings,
  updateSettings,
} from "./settings.ts";
```

Add these tests after the existing `updateSettings posts through the frontend api proxy` test:

```ts
test("buddy runtime settings api uses dedicated settings endpoints", async () => {
  const requests: Array<{ url: string; payload: unknown }> = [];

  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const payload = init?.body ? JSON.parse(String(init.body)) : null;
    requests.push({ url, payload });
    return new Response(JSON.stringify({ permission_mode: "full_access" }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
      },
    });
  }) as typeof fetch;

  assert.deepEqual(await fetchBuddyRuntimeSettings(), { permission_mode: "full_access" });
  assert.deepEqual(await updateBuddyRuntimeSettings({ permission_mode: "ask_first" }), { permission_mode: "full_access" });

  assert.deepEqual(requests, [
    { url: "/api/settings/buddy-runtime", payload: null },
    { url: "/api/settings/buddy-runtime", payload: { permission_mode: "ask_first" } },
  ]);
});
```

Also extend the existing `updateSettings` test payload and expected payload with:

```ts
buddy_runtime: {
  permission_mode: "full_access",
},
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm test -- frontend/src/api/settings.test.ts
```

Expected: FAIL because the new API helpers and types do not exist.

- [ ] **Step 3: Implement settings types and API helpers**

In `frontend/src/types/settings.ts`, add:

```ts
export type BuddyPermissionMode = "ask_first" | "full_access";

export type BuddyRuntimeSettings = {
  permission_mode: BuddyPermissionMode;
};
```

Add `buddy_runtime` to `SettingsPayload`:

```ts
  buddy_runtime?: BuddyRuntimeSettings;
```

In `frontend/src/api/settings.ts`, update imports:

```ts
import type {
  AgentThinkingLevel,
  BuddyRuntimeSettings,
  ModelProviderTransport,
  OpenAICodexAuthStatus,
  SettingsPayload,
} from "@/types/settings";
```

Add to `SettingsUpdatePayload`:

```ts
  buddy_runtime?: BuddyRuntimeSettings;
```

Add the dedicated helpers:

```ts
export async function fetchBuddyRuntimeSettings(): Promise<BuddyRuntimeSettings> {
  return apiGet<BuddyRuntimeSettings>("/api/settings/buddy-runtime");
}

export async function updateBuddyRuntimeSettings(payload: BuddyRuntimeSettings): Promise<BuddyRuntimeSettings> {
  return apiPost<BuddyRuntimeSettings>("/api/settings/buddy-runtime", payload);
}
```

- [ ] **Step 4: Run frontend API test**

Run:

```bash
npm test -- frontend/src/api/settings.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add frontend/src/types/settings.ts frontend/src/api/settings.ts frontend/src/api/settings.test.ts
git commit -m "添加伙伴运行权限前端设置接口"
```

---

### Task 3: Persist Buddy Widget Permission Mode Globally

**Files:**
- Create: `frontend/src/buddy/useBuddyPermissionMode.ts`
- Modify: `frontend/src/buddy/BuddyWidget.vue`
- Test: `frontend/src/buddy/BuddyWidget.structure.test.ts`

- [ ] **Step 1: Write failing widget structure tests**

In `frontend/src/buddy/BuddyWidget.structure.test.ts`, add a source read near existing source constants:

```ts
const permissionModeSource = readFileSync(resolve(currentDirectory, "useBuddyPermissionMode.ts"), "utf8");
```

Add this test near the existing Buddy mode tests:

```ts
test("BuddyWidget persists permission mode through settings API composable", () => {
  assert.match(componentSource, /import \{ useBuddyPermissionMode \} from "\.\/useBuddyPermissionMode\.ts";/);
  assert.match(componentSource, /useBuddyPermissionMode\(\)/);
  assert.match(componentSource, /hydrateBuddyPermissionMode\(\)/);
  assert.match(permissionModeSource, /fetchBuddyRuntimeSettings/);
  assert.match(permissionModeSource, /updateBuddyRuntimeSettings/);
  assert.doesNotMatch(componentSource, /const buddyMode = ref<BuddyMode>\(DEFAULT_BUDDY_MODE\)/);
});
```

- [ ] **Step 2: Run structure test to verify it fails**

Run:

```bash
npm test -- frontend/src/buddy/BuddyWidget.structure.test.ts
```

Expected: FAIL because the composable does not exist and BuddyWidget still owns local-only mode state.

- [ ] **Step 3: Create persisted mode composable**

Create `frontend/src/buddy/useBuddyPermissionMode.ts`:

```ts
import { computed, ref, watch } from "vue";

import { fetchBuddyRuntimeSettings, updateBuddyRuntimeSettings } from "../api/settings.ts";
import type { BuddyPermissionMode } from "../types/settings.ts";
import { DEFAULT_BUDDY_MODE, resolveBuddyMode, type BuddyMode } from "./buddyChatGraph.ts";

export function useBuddyPermissionMode() {
  const buddyMode = ref<BuddyMode>(DEFAULT_BUDDY_MODE);
  const isBuddyModeLoading = ref(false);
  const isBuddyModeSaving = ref(false);
  const buddyModeError = ref("");
  const hasHydratedBuddyMode = ref(false);

  const buddyModeDisabled = computed(() => isBuddyModeLoading.value || isBuddyModeSaving.value);

  async function hydrateBuddyPermissionMode() {
    isBuddyModeLoading.value = true;
    buddyModeError.value = "";
    try {
      const settings = await fetchBuddyRuntimeSettings();
      buddyMode.value = resolveBuddyMode(settings.permission_mode);
      hasHydratedBuddyMode.value = true;
    } catch (error) {
      buddyModeError.value = error instanceof Error ? error.message : "Failed to load Buddy permission mode.";
      hasHydratedBuddyMode.value = true;
    } finally {
      isBuddyModeLoading.value = false;
    }
  }

  async function persistBuddyPermissionMode(mode: BuddyMode) {
    isBuddyModeSaving.value = true;
    buddyModeError.value = "";
    try {
      const settings = await updateBuddyRuntimeSettings({ permission_mode: mode as BuddyPermissionMode });
      buddyMode.value = resolveBuddyMode(settings.permission_mode);
    } catch (error) {
      buddyModeError.value = error instanceof Error ? error.message : "Failed to save Buddy permission mode.";
    } finally {
      isBuddyModeSaving.value = false;
    }
  }

  watch(buddyMode, (nextMode) => {
    const safeMode = resolveBuddyMode(nextMode);
    if (safeMode !== nextMode) {
      buddyMode.value = safeMode;
      return;
    }
    if (!hasHydratedBuddyMode.value || isBuddyModeLoading.value) {
      return;
    }
    void persistBuddyPermissionMode(safeMode);
  });

  return {
    buddyMode,
    buddyModeDisabled,
    buddyModeError,
    hydrateBuddyPermissionMode,
  };
}
```

- [ ] **Step 4: Wire BuddyWidget to the composable**

In `frontend/src/buddy/BuddyWidget.vue`, remove `DEFAULT_BUDDY_MODE` from the `buddyChatGraph.ts` import list.

Add import:

```ts
import { useBuddyPermissionMode } from "./useBuddyPermissionMode.ts";
```

Replace:

```ts
const buddyMode = ref<BuddyMode>(DEFAULT_BUDDY_MODE);
```

with:

```ts
const {
  buddyMode,
  buddyModeDisabled,
  buddyModeError,
  hydrateBuddyPermissionMode,
} = useBuddyPermissionMode();
```

Update the mode `<ElSelect>`:

```vue
<ElSelect
  v-model="buddyMode"
  class="buddy-widget__mode-select toograph-select"
  popper-class="toograph-select-popper buddy-widget__select-popper"
  size="small"
  :aria-label="t('buddy.modeLabel')"
  :title="buddyModeError || buddyModeLabel"
  :disabled="buddyModeDisabled"
>
```

Remove the existing `watch(buddyMode, ...)` block from `BuddyWidget.vue`.

Inside `onMounted`, next to model hydration, add:

```ts
  void hydrateBuddyPermissionMode();
```

- [ ] **Step 5: Run widget structure test**

Run:

```bash
npm test -- frontend/src/buddy/BuddyWidget.structure.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add frontend/src/buddy/useBuddyPermissionMode.ts frontend/src/buddy/BuddyWidget.vue frontend/src/buddy/BuddyWidget.structure.test.ts
git commit -m "持久化伙伴悬浮窗权限模式"
```

---

### Task 4: Stop Injecting `policy.json` Into Buddy Context And Official Templates

**Files:**
- Modify: `frontend/src/buddy/buddyTemplateBindingModel.ts`
- Modify: `frontend/src/buddy/buddyChatGraph.ts` only if tests reveal local constants need adjustment
- Modify: `graph_template/official/buddy_autonomous_loop/template.json`
- Modify: `graph_template/official/buddy_autonomous_review/template.json`
- Modify: `graph_template/official/buddy_context_compaction/template.json`
- Test: `frontend/src/buddy/buddyTemplateBindingModel.test.ts`
- Test: `frontend/src/buddy/buddyChatGraph.test.ts`
- Test: `backend/tests/test_template_layouts.py`

- [ ] **Step 1: Write failing frontend context tests**

In `frontend/src/buddy/buddyTemplateBindingModel.test.ts`, change the expected selected files:

```ts
selected: ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md"],
```

In `frontend/src/buddy/buddyChatGraph.test.ts`, change both expected selected file arrays to:

```ts
selected: ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md"],
```

- [ ] **Step 2: Write failing official template test**

In `backend/tests/test_template_layouts.py`, change the expected Buddy context selected files in `test_buddy_autonomous_loop_uses_output_boundary_capsules`:

```python
["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md"],
```

Add assertions that all official Buddy support templates exclude `policy.json`:

```python
    def test_buddy_support_templates_do_not_inject_policy_json(self) -> None:
        for template_id in ["buddy_autonomous_loop", "buddy_autonomous_review", "buddy_context_compaction"]:
            with self.subTest(template_id=template_id):
                template = _load_official_template(template_id)
                self.assertNotIn("policy.json", json.dumps(template, ensure_ascii=False))
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
npm test -- frontend/src/buddy/buddyTemplateBindingModel.test.ts frontend/src/buddy/buddyChatGraph.test.ts
pytest backend/tests/test_template_layouts.py -q
```

Expected: FAIL because runtime builders and official templates still include `policy.json`.

- [ ] **Step 4: Remove `policy.json` from default frontend Buddy Home package**

In `frontend/src/buddy/buddyTemplateBindingModel.ts`, change:

```ts
selected: ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md", "policy.json"],
```

to:

```ts
selected: ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md"],
```

- [ ] **Step 5: Remove `policy.json` from official templates**

Edit each official template JSON and remove only `policy.json` entries from Buddy Home local-folder selections:

```bash
node --input-type=module <<'JS'
import { readFileSync, writeFileSync } from "node:fs";

const paths = [
  "graph_template/official/buddy_autonomous_loop/template.json",
  "graph_template/official/buddy_autonomous_review/template.json",
  "graph_template/official/buddy_context_compaction/template.json",
];

function removePolicyJson(value) {
  if (Array.isArray(value)) {
    for (const item of value) {
      removePolicyJson(item);
    }
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  for (const [key, item] of Object.entries(value)) {
    if (key === "selected" && Array.isArray(item)) {
      value[key] = item.filter((entry) => entry !== "policy.json");
    } else {
      removePolicyJson(item);
    }
  }
}

for (const path of paths) {
  const data = JSON.parse(readFileSync(path, "utf8"));
  removePolicyJson(data);
  writeFileSync(path, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}
JS
```

Do not run this script against `graph_template/user/`.

- [ ] **Step 6: Run context and template tests**

Run:

```bash
npm test -- frontend/src/buddy/buddyTemplateBindingModel.test.ts frontend/src/buddy/buddyChatGraph.test.ts
pytest backend/tests/test_template_layouts.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add frontend/src/buddy/buddyTemplateBindingModel.ts frontend/src/buddy/buddyTemplateBindingModel.test.ts frontend/src/buddy/buddyChatGraph.test.ts backend/tests/test_template_layouts.py graph_template/official/buddy_autonomous_loop/template.json graph_template/official/buddy_autonomous_review/template.json graph_template/official/buddy_context_compaction/template.json
git commit -m "移除伙伴模板中的策略上下文注入"
```

---

### Task 5: Stop Treating Buddy Home Policy As Current Product Surface

**Files:**
- Modify: `backend/app/buddy/home.py`
- Modify: `backend/tests/test_buddy_routes.py`
- Modify: `backend/tests/test_buddy_store.py` only if it asserts default `policy.json` creation
- Modify: `frontend/src/pages/BuddyPage.vue`
- Modify: `frontend/src/pages/BuddyPage.structure.test.ts`

- [ ] **Step 1: Write failing Buddy Home default tests**

In `backend/tests/test_buddy_routes.py`, change the default file assertion from:

```python
for path in ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md", "policy.json", "buddy.db"]:
```

to:

```python
for path in ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md", "buddy.db"]:
```

Add:

```python
self.assertNotIn("policy.json", files)
```

If `backend/tests/test_buddy_store.py` asserts default `policy.json`, update that assertion to check only `AGENTS.md`, `SOUL.md`, `USER.md`, `MEMORY.md`, and `buddy.db`.

- [ ] **Step 2: Write failing Buddy page structure test**

In `frontend/src/pages/BuddyPage.structure.test.ts`, replace policy-tab expectations with:

```ts
test("BuddyPage no longer exposes policy json as a Buddy Home editor surface", () => {
  assert.doesNotMatch(source, /name="policy"/);
  assert.doesNotMatch(source, /fetchBuddyPolicy/);
  assert.doesNotMatch(source, /updateBuddyPolicy/);
  assert.doesNotMatch(source, /policyDraft/);
  assert.doesNotMatch(source, /graph_permission_mode/);
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest backend/tests/test_buddy_routes.py backend/tests/test_buddy_store.py -q
npm test -- frontend/src/pages/BuddyPage.structure.test.ts
```

Expected: FAIL because Buddy Home still creates/list policy and BuddyPage still exposes the policy tab.

- [ ] **Step 4: Stop creating `policy.json` for new Buddy Homes**

In `backend/app/buddy/home.py`, update `DEFAULT_AGENTS_MD` startup text:

```markdown
- Read `SOUL.md`, `USER.md`, and `MEMORY.md` when a buddy graph needs durable context.
```

Remove this line from `ensure_buddy_home()`:

```python
    _write_json_if_missing(resolved_home / POLICY_PATH, DEFAULT_POLICY)
```

Keep `POLICY_PATH`, `DEFAULT_POLICY`, and policy read/write helpers for compatibility with existing files and old API callers.

- [ ] **Step 5: Hide legacy policy from Buddy Home file listing**

In `backend/app/buddy/store.py`, update `load_home_files()` or its file-entry list so it no longer includes `POLICY_PATH` in the default returned file set. Leave `load_policy()` and `save_policy()` unchanged.

The returned files should include:

```python
[
    _home_file_entry(BUDDY_HOME_DIR / AGENTS_PATH, AGENTS_PATH),
    _home_file_entry(BUDDY_HOME_DIR / SOUL_PATH, SOUL_PATH),
    _home_file_entry(BUDDY_HOME_DIR / USER_PATH, USER_PATH),
    _home_file_entry(BUDDY_HOME_DIR / MEMORY_PATH, MEMORY_PATH),
    _home_file_entry(BUDDY_HOME_DIR / BUDDY_DB_PATH, BUDDY_DB_PATH),
]
```

Use the actual local structure of `load_home_files()`; do not invent new response fields.

- [ ] **Step 6: Remove BuddyPage policy tab**

In `frontend/src/pages/BuddyPage.vue`, remove:

- The `<ElTabPane name="policy">...</ElTabPane>` block.
- Imports of `fetchBuddyPolicy`, `updateBuddyPolicy`, and `BuddyPolicy`.
- `isSavingPolicy`, `policyDraft`, `policyBoundaryText`, `policyPreferenceText`.
- `defaultPolicyDraft`, `normalizePolicyMode`, `normalizeBuddyPolicy`.
- `savePolicy()`.
- `fetchBuddyPolicy()` from the parallel data load in `loadBuddyData()`.
- Assignment of the fetched policy result.

Do not remove the Memory, Profile, Summary, Bindings, Home Files, Sessions, or Revisions tabs.

- [ ] **Step 7: Run Buddy Home and Buddy page tests**

Run:

```bash
pytest backend/tests/test_buddy_routes.py backend/tests/test_buddy_store.py -q
npm test -- frontend/src/pages/BuddyPage.structure.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add backend/app/buddy/home.py backend/app/buddy/store.py backend/tests/test_buddy_routes.py backend/tests/test_buddy_store.py frontend/src/pages/BuddyPage.vue frontend/src/pages/BuddyPage.structure.test.ts
git commit -m "移除伙伴之家策略编辑入口"
```

---

### Task 6: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Update docs text**

In `README.md`, update the Action/runtime bullets so they state:

```markdown
- Buddy 的“需确认 / 完全访问”是全局运行时设置，保存在应用 settings 中。每次 Buddy run 会把当前模式写入 graph metadata，由后端权限暂停逻辑和 Action manifest permissions 决定是否需要人工确认；该模式不来自 Buddy Home，也不注入 LLM 上下文。
```

In `docs/README.md`, replace normative Buddy Home shape text with:

```markdown
- `buddy_home/` 规范形态是 `AGENTS.md`、`SOUL.md`、`USER.md`、`MEMORY.md`、`buddy.db`。旧的 `policy.json` 只作为兼容遗留文件存在，不再作为权限配置来源，也不再注入 Buddy LLM context。
```

Also update the remaining roadmap note so it mentions global runtime settings rather than `policy.json` for permission mode.

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest backend/tests/test_settings_model_providers.py backend/tests/test_buddy_routes.py backend/tests/test_buddy_store.py backend/tests/test_template_layouts.py backend/tests/test_permission_approval.py backend/tests/test_langgraph_permission_approval.py -q
npm test -- frontend/src/api/settings.test.ts frontend/src/buddy/BuddyWidget.structure.test.ts frontend/src/buddy/buddyTemplateBindingModel.test.ts frontend/src/buddy/buddyChatGraph.test.ts frontend/src/pages/BuddyPage.structure.test.ts
```

Expected: PASS.

- [ ] **Step 3: Search for stale policy context references**

Run:

```bash
rg -n "policy\\.json|graph_permission_mode|buddy_can_execute_actions|buddy_requires_approval" README.md docs backend/app frontend/src graph_template/official backend/tests frontend/src --glob '!frontend/dist'
```

Expected:

- `policy.json` may remain only in compatibility backend policy helpers/tests, old-policy migration logic, and docs that explicitly call it legacy.
- `graph_permission_mode` may remain in backend permission runtime, Buddy graph metadata construction, tests, and settings migration.
- No official template JSON should contain `policy.json`.

- [ ] **Step 4: Start TooGraph after code changes**

Run:

```bash
npm start
```

Expected:

- TooGraph starts on `http://127.0.0.1:3477`.
- If port `3477` is occupied by a non-TooGraph process, startup stops and reports the PID/command instead of falling back.

- [ ] **Step 5: Manual UI smoke check**

Open `http://127.0.0.1:3477` and verify:

- Buddy widget mode starts from the persisted setting.
- Switching between `需确认` and `完全访问` persists after reload.
- A Buddy run still records the selected mode in graph metadata.
- Buddy Home context in run details no longer includes `policy.json`.
- Buddy page no longer exposes a Policy JSON editor.

- [ ] **Step 6: Commit docs and any verification-only fixes**

Run:

```bash
git add README.md docs/README.md
git commit -m "更新伙伴权限设置文档"
```

If verification required code/test fixes, include those touched files in the same commit only if they directly repair this implementation.

---

## Self-Review Notes

- Spec coverage: the plan covers global persisted settings, Buddy widget persistence, runtime graph metadata, LLM context cleanup, official template cleanup, Buddy Home policy removal from current UI, compatibility migration, tests, docs, and startup verification.
- Template sync: official Buddy templates need changes. One user template references `policy.json`; it is intentionally not modified automatically because it is user data.
- Deferred gap: operation-level risk granularity for `local_workspace_executor` and explicit permission classification for graph edit playback remain future work, matching the design non-goals.
