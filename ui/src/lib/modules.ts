export type Status = "cached" | "dirty" | "running" | "bypassed" | "failed" | "blocked";

export type RackModule = {
  index: string;
  id: string;
  name: string;
  summary: string;
  status: Status;
  enabled: boolean;
  portable: boolean;
  settings: { label: string; value: string }[];
};

export const modules: RackModule[] = [
  {
    index: "01",
    id: "ingest",
    name: "Ingest",
    summary: "Validate the container, fix VFR, extract analysis audio.",
    status: "cached",
    enabled: true,
    portable: true,
    settings: [
      { label: "Force CFR", value: "On" },
      { label: "PCM", value: "Media sample rate" },
      { label: "Proxy", value: "Off" }
    ]
  },
  {
    index: "02",
    id: "vad",
    name: "Voice detect",
    summary: "Find speech and remove silence with protected pads.",
    status: "cached",
    enabled: true,
    portable: true,
    settings: [
      { label: "Engine", value: "FFmpeg silencedetect" },
      { label: "Noise floor", value: "-30 dB" },
      { label: "Min silence", value: "400 ms" }
    ]
  },
  {
    index: "03",
    id: "transcribe",
    name: "Transcribe",
    summary: "Word-level timestamps on source samples.",
    status: "cached",
    enabled: true,
    portable: false,
    settings: [
      { label: "Model", value: "small" },
      { label: "Language", value: "pt" },
      { label: "Device", value: "cpu / int8" }
    ]
  },
  {
    index: "04",
    id: "retakes",
    name: "Retakes",
    summary: "Drop failed takes; the keeper guard protects the last one.",
    status: "dirty",
    enabled: true,
    portable: false,
    settings: [
      { label: "Strictness", value: "balanced" },
      { label: "Strategy", value: "keep_last" },
      { label: "Window", value: "15 sentences" }
    ]
  },
  {
    index: "05",
    id: "jl_cuts",
    name: "J/L-cuts",
    summary: "Offset audio and add logarithmic micro-fades.",
    status: "dirty",
    enabled: true,
    portable: true,
    settings: [
      { label: "J-cuts", value: "On" },
      { label: "Offset", value: "200 ms" },
      { label: "Crossfade", value: "20 ms" }
    ]
  },
  {
    index: "06",
    id: "zooms",
    name: "Zooms",
    summary: "Alternate punch-ins to hide jump cuts.",
    status: "bypassed",
    enabled: false,
    portable: true,
    settings: [
      { label: "Mode", value: "alternate_cuts" },
      { label: "Scale", value: "1.15" },
      { label: "Anchor", value: "upper third" }
    ]
  },
  {
    index: "07",
    id: "shorts",
    name: "Shorts",
    summary: "Find three vertical moments with burned captions.",
    status: "bypassed",
    enabled: false,
    portable: false,
    settings: [
      { label: "Duration", value: "30–60 s" },
      { label: "Count", value: "3" },
      { label: "Reframe", value: "center crop" }
    ]
  },
  {
    index: "08",
    id: "export",
    name: "Export",
    summary: "Write FCPXML, xmeml, and OTIO from one timeline.",
    status: "dirty",
    enabled: true,
    portable: true,
    settings: [
      { label: "Resolve", value: "FCPXML 1.9" },
      { label: "Premiere", value: "xmeml" },
      { label: "Kdenlive", value: "OTIO" }
    ]
  }
];

export const statusStyles: Record<Status, string> = {
  cached: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  dirty: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  running: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  bypassed: "bg-neutral-600/20 text-neutral-400 ring-neutral-600/40",
  failed: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  blocked: "bg-orange-500/15 text-orange-300 ring-orange-500/30"
};
