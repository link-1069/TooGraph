export type BuddyVirtualOperationAffordance = {
  element: HTMLElement;
};

export function resolveVirtualOperationAffordance(targetId: string): BuddyVirtualOperationAffordance | null {
  if (targetId.startsWith("buddy.") || targetId === "app.nav.buddy") {
    return null;
  }
  if (typeof document === "undefined") {
    return null;
  }
  const affordanceElements = queryVirtualOperationAffordanceElements(targetId);
  let visibleElement: HTMLElement | null = null;
  for (const element of affordanceElements) {
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      continue;
    }
    visibleElement = element;
  }
  return visibleElement ? { element: visibleElement } : null;
}

export function hasVirtualOperationAffordanceElement(targetId: string) {
  if (targetId.startsWith("buddy.") || targetId === "app.nav.buddy" || typeof document === "undefined") {
    return false;
  }
  return queryVirtualOperationAffordanceElements(targetId).length > 0;
}

function queryVirtualOperationAffordanceElements(targetId: string) {
  return document.querySelectorAll<HTMLElement>(`[data-virtual-affordance-id="${escapeVirtualOperationTargetId(targetId)}"]`);
}

export function resolveVirtualOperationTextInput(targetId: string): HTMLInputElement | HTMLTextAreaElement | null {
  const affordance = resolveVirtualOperationAffordance(targetId);
  if (affordance) {
    return resolveVirtualOperationTextInputElement(affordance.element) ?? resolveVirtualOperationTextInputAffordance(`${targetId}.input`);
  }
  return resolveVirtualOperationTextInputAffordance(`${targetId}.input`);
}

function resolveVirtualOperationTextInputAffordance(targetId: string): HTMLInputElement | HTMLTextAreaElement | null {
  const affordance = resolveVirtualOperationAffordance(targetId);
  if (!affordance) {
    return null;
  }
  return resolveVirtualOperationTextInputElement(affordance.element);
}

export function resolveVirtualOperationTextInputElement(element: HTMLElement): HTMLInputElement | HTMLTextAreaElement | null {
  if (isVirtualOperationTextInputElement(element)) {
    return element;
  }
  const input = element.querySelector<HTMLInputElement | HTMLTextAreaElement>("input, textarea");
  return input && isVirtualOperationTextInputElement(input) ? input : null;
}

function isVirtualOperationTextInputElement(element: Element): element is HTMLInputElement | HTMLTextAreaElement {
  return element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement;
}

export function isVisibleVirtualOperationElement(element: HTMLElement) {
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function escapeVirtualOperationTargetId(targetId: string) {
  return targetId.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}
