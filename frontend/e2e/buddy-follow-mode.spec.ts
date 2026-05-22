import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const ACTIVE_SESSION_STORAGE_KEY = "toograph:buddy-active-session";

test("background template evidence survives route changes and buddy dragging", async ({ page, request }) => {
  const sessionId = await seedBuddyTraceSession(request, "E2E background target stability");
  await openBuddySession(page, sessionId);
  await expandTrace(page);

  await expect(page.getByText("artifacts: 2")).toBeVisible();
  await expect(page.getByText("retries: 5")).toBeVisible();

  await page.goto("/runs");
  await openBuddyPanelIfClosed(page);
  await expandTrace(page);
  await expect(page.getByText("artifacts: 2")).toBeVisible();

  await dragBuddy(page, 70, -55);
  await expect(page.getByText("retries: 5")).toBeVisible();

  await page.goto("/editor/new");
  await openBuddyPanelIfClosed(page);
  await expandTrace(page);
  await expect(page.getByText("run: run_e2e_target completed")).toBeVisible();
});

async function seedBuddyTraceSession(request: APIRequestContext, title: string) {
  const sessionResponse = await request.post("/api/buddy/sessions", {
    data: { title },
  });
  expect(sessionResponse.ok()).toBeTruthy();
  const session = await sessionResponse.json();
  const sessionId = String(session.session_id ?? "").trim();
  expect(sessionId).not.toEqual("");

  const now = Date.now();
  const messageResponse = await request.post(`/api/buddy/sessions/${encodeURIComponent(sessionId)}/messages`, {
    data: {
      message_id: `msg_${sessionId}_trace`,
      role: "assistant",
      content: "",
      client_order: 1,
      include_in_context: false,
      run_id: "run_e2e_parent",
      metadata: {
        kind: "output_trace",
        outputTrace: {
          segmentId: "boundary:public_response",
          boundaryNodeId: "public_response",
          boundaryLabel: "Final reply",
          outputNodeIds: ["public_response_output"],
          status: "completed",
          startedAtMs: now - 2400,
          completedAtMs: now,
          durationMs: 2400,
          records: [
            {
              recordId: "boundary:public_response:activity:6:execute_page_operation:1",
              runtimeKey: "activity:6:execute_page_operation",
              kind: "activity",
              label: "Execute page operation / Virtual template run",
              status: "completed",
              startedAtMs: now - 1400,
              completedAtMs: now - 100,
              durationMs: 1300,
              nodeId: "execute_page_operation",
              nodeType: "activity",
              subgraphNodeId: null,
              summary: "Template: report · Input: Build report · Run: run_e2e_target completed",
              artifactLabels: [
                "operation: run_template",
                "template: report",
                "target: library.template.report.open",
                "run: run_e2e_target completed",
                "artifacts: 2",
                "retries: 5",
                "request: vop_e2e_follow",
              ],
              triggeredRunId: "run_e2e_target",
            },
          ],
        },
      },
    },
  });
  expect(messageResponse.ok()).toBeTruthy();
  return sessionId;
}

async function openBuddySession(page: Page, sessionId: string) {
  await page.addInitScript(
    ({ activeSessionId }) => {
      window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeSessionId);
    },
    { activeSessionId: sessionId },
  );
  await page.goto("/");
}

async function openBuddyPanelIfClosed(page: Page) {
  if (await page.locator(".buddy-widget__panel").isVisible()) {
    return;
  }
  await page.locator(".buddy-widget__avatar").click();
  await expect(page.locator(".buddy-widget__panel")).toBeVisible();
}

async function expandTrace(page: Page) {
  await openBuddyPanelIfClosed(page);
  const detail = page.locator(".buddy-widget__run-trace-detail");
  if (await detail.isVisible()) {
    return;
  }
  await page.locator(".buddy-widget__run-trace-summary").first().click();
  await expect(detail).toBeVisible();
}

async function dragBuddy(page: Page, deltaX: number, deltaY: number) {
  const avatar = page.locator(".buddy-widget__avatar");
  const box = await avatar.boundingBox();
  expect(box).not.toBeNull();
  const startX = (box?.x ?? 0) + (box?.width ?? 0) / 2;
  const startY = (box?.y ?? 0) + (box?.height ?? 0) / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 6 });
  await page.mouse.up();
}
