import type { BuddyVirtualOperation } from "../stores/buddyMascotDebug.ts";

import {
  isVisibleVirtualOperationElement,
  resolveVirtualOperationAffordance,
  resolveVirtualOperationTextInputElement,
} from "./buddyVirtualOperationTargets.ts";

export function resolveTemplateRunTargetAffordance(operation: Extract<BuddyVirtualOperation, { kind: "run_template" }>) {
  const exactTargetIds = [
    operation.targetId,
    operation.templateId ? `library.template.${operation.templateId}.open` : "",
  ].filter(Boolean);
  for (const targetId of exactTargetIds) {
    const affordance = resolveVirtualOperationAffordance(targetId);
    if (affordance) {
      return affordance;
    }
  }
  if (typeof document === "undefined") {
    return null;
  }
  const candidates = Array.from(
    document.querySelectorAll<HTMLElement>('[data-virtual-affordance-id^="library.template."][data-virtual-affordance-id$=".open"]'),
  ).filter(isVisibleVirtualOperationElement);
  if (candidates.length === 0) {
    return null;
  }
  const expectedTexts = [operation.templateId, operation.templateName, operation.searchText]
    .map(normalizeTemplateRunMatchText)
    .filter(Boolean);
  if (expectedTexts.length === 0) {
    return { element: candidates[0]! };
  }
  for (const element of candidates) {
    const haystack = normalizeTemplateRunMatchText(
      `${element.dataset.virtualAffordanceId ?? ""} ${element.dataset.virtualAffordanceLabel ?? ""} ${element.textContent ?? ""}`,
    );
    if (expectedTexts.some((text) => haystack.includes(text))) {
      return { element };
    }
  }
  return null;
}

export function resolveTemplateRunInputTextInput() {
  if (typeof document === "undefined") {
    return null;
  }
  const candidates = Array.from(
    document.querySelectorAll<HTMLElement>(
      '[data-virtual-affordance-id^="editor.canvas.node."][data-virtual-affordance-id$=".input.value"]',
    ),
  ).filter(isVisibleVirtualOperationElement);
  for (const element of candidates) {
    const input = resolveVirtualOperationTextInputElement(element);
    if (input) {
      return input;
    }
  }
  return null;
}

export function routeMatchesVirtualOperationTargetPath(currentPath: string, expectedPath: string) {
  const current = currentPath.split("?", 1)[0]?.split("#", 1)[0] || "/";
  const expected = expectedPath.split("?", 1)[0]?.split("#", 1)[0] || "/";
  return current === expected || current.startsWith(`${expected}/`);
}

export function normalizeTemplateRunMatchText(value: unknown) {
  return String(value ?? "").trim().toLowerCase();
}
