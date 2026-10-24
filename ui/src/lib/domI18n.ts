/**
 * Runtime translation for static panel text.
 *
 * The dense panels predate the i18n table. This layer translates exact visible
 * strings and attributes without rewriting every template, and restores the
 * English text when the locale switches back.
 */

export const GLOSSARY: Record<string, string> = {
  "Refresh": "Atualizar",
  "Delete": "Excluir",
  "Cancel": "Cancelar",
  "Undo": "Desfazer",
  "Redo": "Refazer",
  "Add": "Adicionar",
  "Remove": "Remover",
  "Clear": "Limpar",
  "Browse": "Procurar",
  "Download": "Baixar",
  "Save": "Salvar",
  "Save as": "Salvar como",
  "Run": "Executar",
  "Stop": "Parar",
  "Retry": "Tentar de novo",
  "Review": "Revisar",
  "Approve": "Aprovar",
  "Reject": "Rejeitar",
  "Edit": "Editar",
  "Edit Short": "Editar Short",
  "Pick": "Escolher",
  "Verify": "Verificar",
  "Install": "Instalar",
  "Apply": "Aplicar",
  "Close": "Fechar",
  "Reload": "Recarregar",
  "Validate": "Validar",
  "Dry run": "Simulação",
  "Batch": "Lote",
  "Runs": "Execuções",
  "Config": "Configuração",
  "Inspector": "Inspetor",
  "History": "Histórico",
  "Templates": "Modelos de receita",
  "Timeline": "Timeline",
  "Assets": "Assets",
  "Library": "Biblioteca",
  "Models": "Modelos",
  "Services": "Serviços",
  "Providers": "Provedores",
  "Settings": "Configurações",
  "Automation": "Automação",
  "Plugins": "Plugins",
  "Jobs": "Tarefas",
  "Shorts": "Shorts",
  "Markers": "Marcadores",
  "Overlays": "Sobreposições",
  "Clip comments": "Comentários do clipe",
  "B-roll approval": "Aprovação de B-roll",
  "Thumbnail A/B": "A/B de thumbnail",
  "Step logs": "Logs da etapa",
  "Step inspector": "Inspetor da etapa",
  "Support bundle": "Pacote de suporte",
  "Warnings": "Avisos",
  "Variants": "Variantes",
  "Waveform": "Forma de onda",
  "Transitions": "Transições",
  "Trim": "Cortar",
  "Split": "Dividir",
  "Duplicate": "Duplicar",
  "Ripple delete": "Excluir com ripple",
  "Slide": "Deslizar",
  "Add marker here": "Adicionar marcador aqui",
  "Properties / comments": "Propriedades / comentários",
  "Render preview": "Renderizar prévia",
  "Rebuild preview": "Reconstruir prévia",
  "Add step": "Adicionar etapa",
  "+ Add step": "+ Adicionar etapa",
  "Recipe builder": "Construtor de receitas",
  "Auto layout": "Layout automático",
  "Queue": "Fila",
  "Doctor": "Diagnóstico",
  "Restart service": "Reiniciar serviço",
  "Stop service": "Parar serviço"
};

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
