import { expect, test, type Page } from "@playwright/test";

const LOCALE_STORAGE_KEY = "toograph:locale";

test("global language switching updates library navigation copy", async ({ page }) => {
  const problems = collectBrowserProblems(page);
  await openWithLocale(page, "/library", "zh-CN");

  await expect(page.getByRole("heading", { name: "图与模板管理" })).toBeVisible();
  await page.getByRole("button", { name: "当前语言" }).click();
  await page.getByRole("menuitemradio", { name: /English/ }).click();

  await expect(page.getByRole("heading", { name: "Graph and template management" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Current language" })).toHaveAttribute("title", "English");
  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: "Knowledge Center" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  expect(problems).toEqual([]);
});

test("gallery template opens as an editable editor draft", async ({ page }) => {
  const problems = collectBrowserProblems(page);
  await openWithLocale(page, "/library", "en-US");
  await expect(page.getByRole("heading", { name: "Graph and template management" })).toBeVisible();

  await page.locator(".graph-library-page__search input").fill("policy_navigator_agent");
  const policyTemplate = page.locator('[data-virtual-affordance-id="library.template.policy_navigator_agent.open"]');
  await expect(policyTemplate).toBeVisible();
  await policyTemplate.click();

  await expect(page).toHaveURL(/\/editor\/new\?template=policy_navigator_agent/);
  await expect(page.locator(".editor-workspace-shell__workspace")).toBeVisible();
  await expect(page.locator(".editor-tab-bar__tab-title").filter({ hasText: "政策导航助手" })).toBeVisible();
  await expect.poll(() => page.locator(".node-card").count()).toBeGreaterThan(4);
  await expect(page.locator('[data-virtual-affordance-id="editor.action.validateActiveGraph"]')).toBeVisible();
  await expect(page.locator('[data-virtual-affordance-id="editor.action.runActiveGraph"]')).toBeVisible();
  await expect(page.locator('[data-virtual-affordance-id="editor.action.toggleStatePanel"]')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  expect(problems).toEqual([]);
});

async function openWithLocale(page: Page, path: string, locale: string) {
  await page.goto(path);
  await page.evaluate(
    ({ localeKey, localeValue }) => {
      window.localStorage.setItem(localeKey, localeValue);
    },
    { localeKey: LOCALE_STORAGE_KEY, localeValue: locale },
  );
  await page.reload();
}

async function expectNoHorizontalOverflow(page: Page) {
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(hasOverflow).toBe(false);
}

function collectBrowserProblems(page: Page) {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      problems.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => {
    problems.push(`pageerror: ${error.message}`);
  });
  return problems;
}
