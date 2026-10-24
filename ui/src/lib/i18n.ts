const STRINGS: Record<string, Record<string, string>> = {
  en: {
    recipes: "Recipes",
    assets: "Assets",
    timeline: "Timeline",
    jobs: "Jobs",
    automation: "Automation",
    library: "Library",
    models: "Models",
    services: "Services",
    providers: "Providers",
    settings: "Settings",
    subtitle: "Editable rough cuts and repeatable content recipes",
    workspace: "Workspace areas",
    activity: "Activity",
    notifications: "Notifications",
    shortcuts: "Keyboard shortcuts"
  },
  "pt-BR": {
    recipes: "Receitas",
    assets: "Assets",
    timeline: "Timeline",
    jobs: "Tarefas",
    automation: "Automação",
    library: "Biblioteca",
    models: "Modelos",
    services: "Serviços",
    providers: "Provedores",
    settings: "Configurações",
    subtitle: "Cortes editáveis e receitas de conteúdo repetíveis",
    workspace: "Áreas de trabalho",
    activity: "Atividade",
    notifications: "Notificações",
    shortcuts: "Atalhos de teclado"
  }
};

export function t(locale: string, key: string): string {
  const table = STRINGS[locale] ?? STRINGS.en;
  return table[key] ?? STRINGS.en[key] ?? key;
}

export function locales(): string[] {
  return Object.keys(STRINGS);
}
