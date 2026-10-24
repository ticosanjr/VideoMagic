export function nextFocusIndex(current: number, length: number, shift: boolean): number {
  if (length <= 0) return 0;
  if (shift) return current <= 0 ? length - 1 : current - 1;
  return current >= length - 1 ? 0 : current + 1;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

export function focusTrap(node: HTMLElement) {
  function onKeydown(event: KeyboardEvent) {
    if (event.key !== "Tab") return;
    const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (item) => item.offsetParent !== null
    );
    if (!items.length) return;
    const active = document.activeElement as HTMLElement | null;
    const current = active ? items.indexOf(active) : -1;
    event.preventDefault();
    const target = items[nextFocusIndex(current, items.length, event.shiftKey)];
    target?.focus();
  }

  node.addEventListener("keydown", onKeydown);
  return {
    destroy() {
      node.removeEventListener("keydown", onKeydown);
    }
  };
}

export function restoreFocus(element: HTMLElement | null) {
  element?.focus?.();
}
