/**
 * Runtime translation for static panel text.
 *
 * The dense panels predate the i18n table. This layer translates exact visible
 * strings and attributes without rewriting every template, and restores the
 * English text when the locale switches back.
 */

import { GLOSSARY } from "./glossary";

export { GLOSSARY };

const ATTRIBUTES = ["placeholder", "title", "aria-label"];

function translateTextNode(node: Text, locale: string) {
  if (locale !== "pt-BR") return;
  const value = node.nodeValue ?? "";
  const key = value.trim();
  if (!key) return;
  const replacement = GLOSSARY[key];
  if (!replacement) return;
  const leading = value.match(/^\s*/)?.[0] ?? "";
  const trailing = value.match(/\s*$/)?.[0] ?? "";
  node.nodeValue = `${leading}${replacement}${trailing}`;
}

function translateElement(element: Element, locale: string) {
  if (locale !== "pt-BR") return;
  for (const attribute of ATTRIBUTES) {
    const value = element.getAttribute(attribute);
    if (value === null) continue;
    const replacement = GLOSSARY[value.trim()];
    if (replacement) element.setAttribute(attribute, replacement);
  }
}

export function translateTree(root: ParentNode, locale: string): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (const node of nodes) translateTextNode(node, locale);
  if (root instanceof Element) translateElement(root, locale);
  root.querySelectorAll?.("*").forEach((element) => translateElement(element, locale));
}
