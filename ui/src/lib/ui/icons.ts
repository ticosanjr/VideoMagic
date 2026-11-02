/**
 * Local SVG icon registry. No runtime dependency and no network fetch: every
 * path is shipped with the UI so the local build stays self-contained.
 */

const path = (d: string) => `<path d="${d}"/>`;
const circle = (cx: number, cy: number, r: number) => `<circle cx="${cx}" cy="${cy}" r="${r}"/>`;
const rect = (x: number, y: number, w: number, h: number, rx = 1.5) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}"/>`;
const line = (x1: number, y1: number, x2: number, y2: number) =>
  `<path d="M${x1} ${y1}L${x2} ${y2}"/>`;

export const ICONS = {
  play: `<path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none"/>`,
  pause: `<path d="M8 5h3v14H8zM13 5h3v14h-3z" fill="currentColor" stroke="none"/>`,
  "skip-back": `<path d="M6 5v14M18 5v14L7 12z" fill="currentColor" stroke="none"/>`,
  "skip-forward": `<path d="M18 5v14M6 5v14l11-7z" fill="currentColor" stroke="none"/>`,
  "chevron-left": path("M15 6l-6 6 6 6"),
  "chevron-right": path("M9 6l6 6-6 6"),
  scissors: `${circle(6, 6, 2.5)}${circle(6, 18, 2.5)}${line(8.2, 7.5, 20, 18)}${line(8.2, 16.5, 20, 6)}`,
  activity: path("M3 12h4l2.5-7 4 14 2.5-7H21"),
  library: `${rect(4, 4, 4, 16)}${rect(10, 4, 4, 16)}${rect(16, 4, 4, 16)}`,
  settings: `${circle(12, 12, 3)}${path("M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1")}`,
  list: `${line(8, 6, 21, 6)}${line(8, 12, 21, 12)}${line(8, 18, 21, 18)}${circle(4, 6, 1)}${circle(4, 12, 1)}${circle(4, 18, 1)}`,
  folder: path("M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"),
  sparkles: `${path("M12 3l1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7z")}${path("M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z")}`,
  film: `${rect(3, 5, 18, 14, 2)}${line(7, 5, 7, 19)}${line(17, 5, 17, 19)}${line(3, 9, 21, 9)}${line(3, 15, 21, 15)}`,
  calendar: `${rect(3, 5, 18, 16, 2)}${line(3, 10, 21, 10)}${line(8, 3, 8, 7)}${line(16, 3, 16, 7)}${circle(12, 15, 1.4)}`,
  image: `${rect(3, 4, 18, 16, 2)}${circle(8.5, 9, 1.8)}${path("M21 16l-5-5-9 9")}`,
  palette: `${path("M12 3a9 9 0 1 0 0 18h1.5a2 2 0 0 0 0-4H13a2 2 0 0 1 0-4h5a3 3 0 0 0 3-3c0-3.9-4-7-9-7z")}${circle(7.5, 10, 1)}${circle(10, 6.8, 1)}${circle(14, 7, 1)}`,
  cpu: `${rect(6, 6, 12, 12, 2)}${rect(9.5, 9.5, 5, 5, 1)}${line(9, 2, 9, 6)}${line(15, 2, 15, 6)}${line(9, 18, 9, 22)}${line(15, 18, 15, 22)}${line(2, 9, 6, 9)}${line(2, 15, 6, 15)}${line(18, 9, 22, 9)}${line(18, 15, 22, 15)}`,
  plug: `${path("M9 3v6M15 3v6")}${path("M7 9h10v3a5 5 0 0 1-10 0z")}${line(12, 17, 12, 21)}`,
  server: `${rect(3, 4, 18, 6, 2)}${rect(3, 14, 18, 6, 2)}${line(7, 7, 7.01, 7)}${line(7, 17, 7.01, 17)}`,
  puzzle: path("M4 8h3a2 2 0 1 1 0 4H4v7h6v-2.5a2 2 0 1 1 4 0V19h6v-7h-2.5a2 2 0 1 1 0-4H20V4h-6v2.5a2 2 0 1 1-4 0V4H4z"),
  link: `${path("M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1")}${path("M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1")}`,
  sliders: `${line(4, 6, 20, 6)}${line(4, 12, 20, 12)}${line(4, 18, 20, 18)}${circle(9, 6, 2)}${circle(15, 12, 2)}${circle(8, 18, 2)}`,
  waveform: `${line(3, 12, 5, 12)}${line(7, 8, 7, 16)}${line(10, 5, 10, 19)}${line(13, 9, 13, 15)}${line(16, 3, 16, 21)}${line(19, 8, 19, 16)}${line(21, 12, 22, 12)}`,
  captions: `${rect(3, 5, 18, 14, 2)}${line(6, 11, 11, 11)}${line(13, 11, 18, 11)}${line(6, 15, 15, 15)}`,
  repeat: `${path("M17 2l3 3-3 3")}${path("M4 11V9a4 4 0 0 1 4-4h12")}${path("M7 22l-3-3 3-3")}${path("M20 13v2a4 4 0 0 1-4 4H4")}`,
  share: `${circle(18, 5, 2.2)}${circle(6, 12, 2.2)}${circle(18, 19, 2.2)}${line(8, 11, 16, 6)}${line(8, 13, 16, 18)}`,
  smartphone: `${rect(7, 2, 10, 20, 2.5)}${line(10, 18, 14, 18)}`,
  crop: `${path("M6 2v14a2 2 0 0 0 2 2h14")}${path("M2 6h14a2 2 0 0 1 2 2v14")}`,
  search: `${circle(10.5, 10.5, 6.5)}${line(15.5, 15.5, 21, 21)}`,
  music: `${circle(7, 18, 3)}${circle(18, 16, 3)}${line(10, 18, 10, 5)}${line(21, 16, 21, 3)}${line(10, 5, 21, 3)}`,
  volume: `${path("M4 9h4l5-4v14l-5-4H4z")}${path("M16 8a5 5 0 0 1 0 8")}${path("M19 5a9 9 0 0 1 0 14")}`,
  check: path("M4 12.5l5 5L20 6.5"),
  type: `${line(4, 6, 20, 6)}${line(12, 6, 12, 20)}${line(8, 20, 16, 20)}`,
  users: `${circle(9, 8, 3.5)}${path("M2.5 20a6.5 6.5 0 0 1 13 0")}${circle(18, 9, 2.5)}${path("M16 15a5 5 0 0 1 5.5 5")}`,
  mic: `${rect(9, 3, 6, 11, 3)}${path("M5 11a7 7 0 0 0 14 0")}${line(12, 18, 12, 22)}`,
  tag: `${path("M3 12l9-9h8v8l-9 9z")}${circle(16.5, 7.5, 1.5)}`,
  send: `${path("M22 2L11 13")}${path("M22 2l-7 20-4-9-9-4z")}`,
  bookmark: path("M6 3h12v18l-6-4-6 4z"),
  package: `${path("M3 7l9-4 9 4-9 4z")}${path("M3 7v10l9 4 9-4V7")}${line(12, 11, 12, 21)}`,
  chart: `${line(4, 3, 4, 21)}${line(4, 21, 21, 21)}${path("M7 16l4-5 3 3 5-7")}`,
  bulb: `${path("M9 18h6")}${path("M10 22h4")}${path("M8.5 14a6 6 0 1 1 7 0c-.8.6-1.5 1.8-1.5 3h-4c0-1.2-.7-2.4-1.5-3z")}`,
  file: `${path("M6 2h8l4 4v16H6z")}${path("M14 2v5h5")}${line(9, 13, 15, 13)}${line(9, 17, 15, 17)}`,
  webhook: `${circle(6, 6, 2.5)}${circle(18, 8, 2.5)}${circle(11, 19, 2.5)}${path("M8 7l8 1M16.5 10l-4 7M9 17L7 8")}`,
  workflow: `${rect(3, 3, 6, 6)}${rect(15, 3, 6, 6)}${rect(9, 15, 6, 6)}${line(9, 6, 15, 6)}${line(6, 9, 6, 12)}${line(6, 12, 12, 12)}${line(12, 12, 12, 15)}`,
  flask: `${path("M9 3h6")}${path("M10 3v6l-6 10a2 2 0 0 0 1.7 3h12.6a2 2 0 0 0 1.7-3L14 9V3")}${line(7.5, 15, 16.5, 15)}`,
  plus: `${line(12, 5, 12, 19)}${line(5, 12, 19, 12)}`,
  save: `${path("M4 3h12l4 4v14H4z")}${path("M8 3v6h8V3")}${rect(8, 13, 8, 6, 0.5)}`,
  more: `${circle(5, 12, 1.3)}${circle(12, 12, 1.3)}${circle(19, 12, 1.3)}`,
  undo: `${path("M9 7L4 12l5 5")}${path("M4 12h9a6 6 0 0 1 6 6")}`,
  redo: `${path("M15 7l5 5-5 5")}${path("M20 12h-9a6 6 0 0 0-6 6")}`,
  layout: `${rect(3, 3, 7, 7)}${rect(14, 3, 7, 7)}${rect(3, 14, 7, 7)}${rect(14, 14, 7, 7)}`,
  code: `${path("M8 7l-5 5 5 5")}${path("M16 7l5 5-5 5")}${line(13, 4, 11, 20)}`,
  star: `<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>`,
  trash: `${path("M4 6h16")}${path("M9 6V3h6v3")}${path("M6 6l1 15h10l1-15")}${line(10, 10, 10, 17)}${line(14, 10, 14, 17)}`,
  duplicate: `${rect(8, 8, 12, 12, 2)}${path("M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2")}`,
  logs: `${rect(3, 4, 18, 16, 2)}${line(6, 8, 18, 8)}${line(6, 12, 18, 12)}${line(6, 16, 14, 16)}`,
  panel: `${rect(3, 4, 18, 16, 2)}${line(15, 4, 15, 20)}`,
  warning: `${path("M12 3L2.5 21h19z")}${line(12, 9, 12, 15)}${circle(12, 18.2, 0.9)}`,
  info: `${circle(12, 12, 9)}${line(12, 11, 12, 17)}${circle(12, 7.5, 0.9)}`,
  close: `${line(6, 6, 18, 18)}${line(18, 6, 6, 18)}`,
  refresh: `${path("M20 11a8 8 0 1 0-2.3 5.7")}${path("M20 4v7h-7")}`,
  external: `${path("M14 4h6v6")}${path("M20 4l-9 9")}${path("M18 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5")}`,
  chevron: path("M6 9l6 6 6-6"),
  "arrow-up": path("M12 19V5M5 12l7-7 7 7"),
  "arrow-down": path("M12 5v14M5 12l7 7 7-7"),
  home: `${path("M3 11l9-8 9 8")}${path("M5 10v11h14V10")}${path("M10 21v-6h4v6")}`,
  clock: `${circle(12, 12, 9)}${path("M12 7v5l3 2")}`,
  database: `${path("M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z")}${path("M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6")}${path("M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6")}`,
  layers: `${path("M12 3l9 5-9 5-9-5z")}${path("M3 12l9 5 9-5")}${path("M3 16l9 5 9-5")}`,
  grid: `${rect(3, 3, 7, 7)}${rect(14, 3, 7, 7)}${rect(3, 14, 7, 7)}${rect(14, 14, 7, 7)}`,
  circle: circle(12, 12, 9)
} as const;

export type IconName = keyof typeof ICONS;

export const AREA_ICON_NAMES = {
  produce: "play",
  edit: "scissors",
  runs: "activity",
  library: "library",
  setup: "settings"
} as const satisfies Record<string, IconName>;

export const TAB_ICON_NAMES = {
  recipes: "list",
  assistant: "sparkles",
  timeline: "film",
  jobs: "activity",
  schedules: "calendar",
  media: "image",
  brand: "palette",
  models: "cpu",
  providers: "plug",
  services: "server",
  extensions: "puzzle",
  connect: "link",
  settings: "settings"
} as const satisfies Record<string, IconName>;

export const STEP_ICON_NAMES: Record<string, IconName> = {
  ingest: "film",
  "audio.vad": "waveform",
  transcribe: "captions",
  "retakes.cull": "repeat",
  "edit.timeline": "scissors",
  "timeline.load": "folder",
  "export.nle": "share",
  "shorts.select": "smartphone",
  "shorts.score": "chart",
  "shorts.reframe": "crop",
  "shorts.captions": "captions",
  "shorts.render": "smartphone",
  "shorts.ab": "duplicate",
  "broll.plan": "image",
  "assets.shots": "film",
  "assets.match": "search",
  "assets.index": "database",
  "music.beat": "music",
  "sfx.plan": "volume",
  "audio.master": "sliders",
  "audio.qa": "check",
  "audio.diarize": "users",
  "color.grade": "palette",
  "titles.plan": "type",
  "thumbnail.generate": "image",
  "thumbnail.pack": "grid",
  "storyboard.plan": "layout",
  "transcript.translate": "link",
  "localization.dub": "mic",
  "human.gate": "users",
  "metadata.pack": "tag",
  "publish.queue": "send",
  "publish.webhook": "webhook",
  "chapters.plan": "bookmark",
  "nle.qa": "check",
  "delivery.package": "package",
  "analytics.import": "chart",
  "analytics.review": "chart",
  "review.queue": "list",
  "content.idea": "bulb",
  "content.research": "search",
  "content.script": "file",
  "flow.conditional": "workflow",
  "flow.loop": "repeat",
  "flow.map": "workflow",
  "flow.reduce": "workflow",
  "flow.subflow": "workflow",
  "experiment.evaluate": "flask"
};

export function stepIcon(type: string): IconName {
  return STEP_ICON_NAMES[type] ?? "circle";
}
