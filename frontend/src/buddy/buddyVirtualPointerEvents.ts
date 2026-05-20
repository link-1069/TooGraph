import type { BuddyPosition } from "./buddyPosition.ts";

const BUDDY_VIRTUAL_POINTER_ID = 9001;
const TOOGRAPH_VIRTUAL_POINTER_EVENT_KEY = "__toographVirtualPointerEvent";
const TOOGRAPH_VIRTUAL_EMPTY_CANVAS_POINTER_EVENT_KEY = "__toographVirtualEmptyCanvasPointerEvent";

export function dispatchVirtualClick(element: HTMLElement) {
  const rect = element.getBoundingClientRect();
  const clientX = rect.left + rect.width / 2;
  const clientY = rect.top + rect.height / 2;
  dispatchVirtualPointerTap(element);
  element.dispatchEvent(
    new MouseEvent("click", {
      bubbles: true,
      cancelable: true,
      clientX,
      clientY,
      view: window,
    }),
  );
}

export function dispatchVirtualDoubleClick(element: HTMLElement, point?: BuddyPosition | null) {
  const rect = element.getBoundingClientRect();
  const clientX = point?.x ?? rect.left + rect.width / 2;
  const clientY = point?.y ?? rect.top + rect.height / 2;
  dispatchVirtualPointerTap(element, point);
  dispatchVirtualPointerTap(element, point);
  element.dispatchEvent(
    new MouseEvent("dblclick", {
      bubbles: true,
      cancelable: true,
      clientX,
      clientY,
      view: window,
    }),
  );
}

export function dispatchVirtualPointerTap(element: HTMLElement, point?: BuddyPosition | null) {
  const rect = element.getBoundingClientRect();
  const clientX = point?.x ?? rect.left + rect.width / 2;
  const clientY = point?.y ?? rect.top + rect.height / 2;
  dispatchVirtualPointerEvent(element, "pointerdown", clientX, clientY);
  dispatchVirtualPointerEvent(element, "pointerup", clientX, clientY);
}

export function dispatchVirtualInputEvents(element: HTMLInputElement | HTMLTextAreaElement, inputType: string, data: string) {
  if (typeof InputEvent === "function") {
    element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType, data }));
  } else {
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

export function dispatchVirtualPointerEvent(
  element: HTMLElement,
  type: "pointerdown" | "pointermove" | "pointerup",
  clientX: number,
  clientY: number,
  options: { forceEmptyCanvasDrop?: boolean } = {},
) {
  const eventInit = {
    bubbles: true,
    cancelable: true,
    clientX,
    clientY,
    pointerId: BUDDY_VIRTUAL_POINTER_ID,
    pointerType: "mouse",
    button: 0,
    buttons: type === "pointerup" ? 0 : 1,
    view: window,
  };
  if (typeof PointerEvent === "function") {
    element.dispatchEvent(markVirtualPointerEvent(new PointerEvent(type, eventInit), options));
    return;
  }
  element.dispatchEvent(markVirtualPointerEvent(new MouseEvent(type, eventInit), options));
}

function markVirtualPointerEvent<T extends Event>(event: T, options: { forceEmptyCanvasDrop?: boolean } = {}): T {
  Object.defineProperty(event, TOOGRAPH_VIRTUAL_POINTER_EVENT_KEY, {
    configurable: true,
    value: true,
  });
  if (options.forceEmptyCanvasDrop) {
    Object.defineProperty(event, TOOGRAPH_VIRTUAL_EMPTY_CANVAS_POINTER_EVENT_KEY, {
      configurable: true,
      value: true,
    });
  }
  return event;
}
