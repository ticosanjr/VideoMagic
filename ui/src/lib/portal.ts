/** Move an overlay to document.body so parent stacking contexts cannot hide it. */
export function portal(node: HTMLElement) {
  const target = typeof document !== "undefined" ? document.body : null;
  if (target && node.parentElement !== target) target.appendChild(node);
  return {
    destroy() {
      node.remove();
    }
  };
}
