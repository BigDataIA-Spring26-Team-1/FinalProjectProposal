import { useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, AlertTriangle, ArrowRight, Bot, Brain, CheckCircle, Clock, Cog, Cpu, Database, DollarSign, Factory, Flame, Gauge, Hammer, Layers, Loader, Minus, Package, Play, Plus, RotateCcw, Search, Send, Server, Settings, Shield, Trash2, TrendingUp, Truck, Users, Workflow, Wrench, XCircle, Zap } from "lucide-react";
import { dataSourceCards, datasetProfile, liveFeed } from "./data/demoData";
import { fetchDashboardSnapshot, fetchRagStatus, rebuildRagIndex, sendChatQuestion } from "./api";
import "./styles.css";

const font = "'IBM Plex Mono', 'Fira Code', monospace";
const fontSans = "'Plus Jakarta Sans', 'DM Sans', system-ui, sans-serif";
const C = { bg: "#06090f", surface: "#0c1220", card: "#111a2e", border: "#1a2744", accent: "#22d3a7", warn: "#fbbf24", danger: "#f43f5e", info: "#60a5fa", purple: "#a78bfa", cyan: "#22d3ee", orange: "#fb923c", text: "#e8edf5", textMid: "#8b98b0", textDim: "#4a5568" };
const HIDDEN_SOURCE_KEYS = new Set(["glassdoor", "reddit"]);
const HIDDEN_SOURCE_NAMES = new Set(["Glassdoor", "Reddit"]);
const PIPELINE_SIZE_BY_KEY = {
  sec: "~8 GB",
  osha: "~12 GB",
  itac: "~2 GB",
  catalogs: "~15 GB",
  fred: "~500 MB",
  eia: "~500 MB",
  epa: "~5 GB",
  nasa: "~500 MB",
  stackexchange: "~3 GB",
  reddit: "~3 GB",
  serpapi: "~3 GB",
  glassdoor: "~3 GB",
};
const MACHINES = {
  cnc: { name: "CNC Mill", icon: Cog, time: 12, fail: 0.03, cost: 45000, kw: 15 },
  lathe: { name: "Lathe", icon: Hammer, time: 8, fail: 0.02, cost: 28000, kw: 10 },
  press: { name: "Stamp Press", icon: Hammer, time: 6, fail: 0.04, cost: 35000, kw: 20 },
  welder: { name: "Welder", icon: Flame, time: 10, fail: 0.05, cost: 22000, kw: 25 },
  assembler: { name: "Assembly", icon: Wrench, time: 15, fail: 0.01, cost: 18000, kw: 5 },
  inspector: { name: "QC Station", icon: Search, time: 5, fail: 0.005, cost: 50000, kw: 3 },
  robot: { name: "Robot Arm", icon: Bot, time: 7, fail: 0.015, cost: 75000, kw: 12 },
};

function defaultConfig() {
  return {
    lines: [
      { id: 1, name: "Line A - Chassis", stations: [{ id: 1, type: "press", count: 2, workers: 3 }, { id: 2, type: "cnc", count: 1, workers: 2 }, { id: 3, type: "welder", count: 2, workers: 4 }, { id: 4, type: "inspector", count: 1, workers: 1 }] },
      { id: 2, name: "Line B - Electronics", stations: [{ id: 5, type: "robot", count: 2, workers: 2 }, { id: 6, type: "assembler", count: 3, workers: 6 }, { id: 7, type: "inspector", count: 1, workers: 1 }] },
      { id: 3, name: "Line C - Final Assembly", stations: [{ id: 8, type: "assembler", count: 4, workers: 8 }, { id: 9, type: "robot", count: 1, workers: 1 }, { id: 10, type: "inspector", count: 2, workers: 2 }] },
    ],
    shiftHours: 8,
    shiftsPerDay: 2,
    daysPerWeek: 5,
    laborCost: 28,
    electricityCost: 0.12,
    materialCost: 150,
    sellPrice: 850,
  };
}

function simulate(config, sourceSnapshots = [], hours = 168) {
  const timeline = [];
  const lineModifiers = config.lines.map((line) => deriveLineLiveModifiers(line, sourceSnapshots));
  const lineBreakdown = config.lines.map((line, index) => ({
    name: line.name,
    produced: 0,
    defects: 0,
    downtime: 0,
    timeline: [],
    liveInputs: lineModifiers[index].liveInputs,
    liveSummary: lineModifiers[index].summary,
  }));
  let produced = 0;
  let defects = 0;
  let downtime = 0;
  for (let hour = 0; hour < hours; hour += 1) {
    const active = hour % 24 < config.shiftHours * config.shiftsPerDay && Math.floor(hour / 24) % 7 < config.daysPerWeek;
    let hourlyProduced = 0;
    let hourlyDefects = 0;
    let hourlyDowntime = 0;
    const lineHourSnapshots = config.lines.map(() => ({ produced: 0, defects: 0, downtime: 0, efficiency: 0 }));
    if (active) {
      config.lines.forEach((line, lineIndex) => {
        const modifiers = lineModifiers[lineIndex];
        let rate = Number.POSITIVE_INFINITY;
        line.stations.forEach((station) => {
          const machine = MACHINES[station.type];
          const efficiency = station.count * (1 - machine.fail * (1 + Math.random() * 0.5)) * Math.min(1, station.workers / (station.count * 1.5)) * (0.85 + Math.random() * 0.15);
          rate = Math.min(rate, (60 / machine.time) * efficiency);
        });
        const lineProduced = Math.floor(rate * modifiers.throughputMultiplier * (0.9 + Math.random() * 0.2));
        const lineDefects = Math.floor(lineProduced * (0.01 + Math.random() * 0.03) * modifiers.defectMultiplier);
        const lineDowntime =
          line.stations.reduce((sum, station) => sum + (Math.random() < MACHINES[station.type].fail ? 5 + Math.random() * 15 : 0) * station.count, 0) *
          modifiers.downtimeMultiplier;
        hourlyProduced += lineProduced;
        hourlyDefects += lineDefects;
        hourlyDowntime += lineDowntime;
        lineBreakdown[lineIndex].produced += lineProduced;
        lineBreakdown[lineIndex].defects += lineDefects;
        lineBreakdown[lineIndex].downtime += lineDowntime;
        lineHourSnapshots[lineIndex] = {
          produced: lineProduced * 4,
          defects: lineDefects * 4,
          downtime: lineDowntime,
          efficiency: clamp(
            85 + modifiers.throughputMultiplier * 6 - modifiers.defectMultiplier * 8 - modifiers.downtimeMultiplier * 10 + Math.random() * 6,
            42,
            98,
          ),
        };
      });
    }
    produced += hourlyProduced;
    defects += hourlyDefects;
    downtime += hourlyDowntime;
    if (hour % 4 === 0) {
      timeline.push({ hour, produced: hourlyProduced * 4, cumulativeProduced: produced, efficiency: active ? 85 + Math.random() * 12 : 0, downtime: hourlyDowntime });
      lineHourSnapshots.forEach((snapshot, lineIndex) => {
        lineBreakdown[lineIndex].timeline.push({
          hour,
          produced: snapshot.produced,
          cumulativeProduced: lineBreakdown[lineIndex].produced,
          efficiency: active ? snapshot.efficiency : 0,
          downtime: snapshot.downtime,
        });
      });
    }
  }
  const workers = config.lines.reduce((sum, line) => sum + line.stations.reduce((lineSum, station) => lineSum + station.workers, 0), 0);
  const machines = config.lines.reduce((sum, line) => sum + line.stations.reduce((lineSum, station) => lineSum + station.count, 0), 0);
  const workHours = config.shiftHours * config.shiftsPerDay * config.daysPerWeek;
  const enrichedLineBreakdown = lineBreakdown.map((lineResult, lineIndex) => {
    const line = config.lines[lineIndex];
    const modifiers = lineModifiers[lineIndex];
    const lineWorkers = line.stations.reduce((sum, station) => sum + station.workers, 0);
    const lineMachines = line.stations.reduce((sum, station) => sum + station.count, 0);
    const lineEnergyKw = line.stations.reduce((sum, station) => sum + MACHINES[station.type].kw * station.count, 0);
    const lineLabor = lineWorkers * config.laborCost * workHours;
    const lineEnergy = lineEnergyKw * workHours * config.electricityCost * modifiers.energyCostMultiplier;
    const lineMaterial = lineResult.produced * config.materialCost * modifiers.materialCostMultiplier;
    const lineMaintenance = lineMachines * 200 * modifiers.maintenanceCostMultiplier;
    const lineCost = lineLabor + lineEnergy + lineMaterial + lineMaintenance;
    const lineRevenue = Math.max(0, lineResult.produced - lineResult.defects) * config.sellPrice * modifiers.revenueMultiplier;
    return {
      ...lineResult,
      workers: lineWorkers,
      machines: lineMachines,
      labor: lineLabor,
      energy: lineEnergy,
      material: lineMaterial,
      maintenance: lineMaintenance,
      cost: lineCost,
      revenue: lineRevenue,
      profit: lineRevenue - lineCost,
      oee: Math.min(0.95, ((lineResult.produced - lineResult.defects) / Math.max(1, lineResult.produced)) * (0.9 - (modifiers.downtimeMultiplier - 1) * 0.08)),
      defectRate: lineResult.defects / Math.max(1, lineResult.produced),
    };
  });
  const labor = enrichedLineBreakdown.reduce((sum, line) => sum + line.labor, 0);
  const energy = enrichedLineBreakdown.reduce((sum, line) => sum + line.energy, 0);
  const material = enrichedLineBreakdown.reduce((sum, line) => sum + line.material, 0);
  const maintenance = enrichedLineBreakdown.reduce((sum, line) => sum + line.maintenance, 0);
  const cost = labor + energy + material + maintenance;
  const revenue = enrichedLineBreakdown.reduce((sum, line) => sum + line.revenue, 0);
  return { timeline, lineBreakdown: enrichedLineBreakdown, produced, defects, downtime, workers, machines, labor, energy, material, maintenance, cost, revenue, profit: revenue - cost, oee: Math.min(0.95, ((produced - defects) / Math.max(1, produced)) * 0.92), defectRate: defects / Math.max(1, produced) };
}

function formatCompact(value) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: value >= 1000 ? 1 : 0 }).format(value);
}

function formatRelativeTime(timestamp) {
  if (!timestamp) return "awaiting sync";
  const deltaMinutes = Math.max(0, Math.round((Date.now() - new Date(timestamp).getTime()) / 60000));
  if (deltaMinutes < 1) return "just now";
  if (deltaMinutes < 60) return `${deltaMinutes} min ago`;
  const hours = Math.round(deltaMinutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} day ago`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function toNumericValue(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const cleaned = value.replace(/,/g, "").replace(/[^\d.-]/g, "");
  if (!cleaned || cleaned === "-" || cleaned === ".") return null;
  const parsed = Number.parseFloat(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function findSourceSnapshot(sourceSnapshots, key) {
  return sourceSnapshots.find((snapshot) => snapshot.key === key);
}

function readNumericFromRecords(snapshot, preferredFields = []) {
  if (!snapshot?.records?.length) return null;
  for (const record of snapshot.records) {
    for (const field of preferredFields) {
      const parsed = toNumericValue(record?.[field]);
      if (parsed != null) return parsed;
    }
    for (const value of Object.values(record)) {
      const parsed = toNumericValue(value);
      if (parsed != null) return parsed;
    }
  }
  return null;
}

function deriveLineLiveModifiers(line, sourceSnapshots) {
  const stationCount = Math.max(1, line.stations.length);
  const typeCounts = line.stations.reduce((counts, station) => {
    counts[station.type] = (counts[station.type] ?? 0) + 1;
    return counts;
  }, {});
  const energyIntensity =
    line.stations.reduce((sum, station) => sum + MACHINES[station.type].kw * station.count, 0) /
    Math.max(
      1,
      line.stations.reduce((sum, station) => sum + station.count, 0) * 25,
    );
  const heavyOps =
    ((typeCounts.press ?? 0) + (typeCounts.welder ?? 0) + (typeCounts.cnc ?? 0) + (typeCounts.lathe ?? 0)) /
    stationCount;
  const automation = ((typeCounts.robot ?? 0) + (typeCounts.inspector ?? 0)) / stationCount;
  const assembly = ((typeCounts.assembler ?? 0) + (typeCounts.robot ?? 0)) / stationCount;
  const precision = ((typeCounts.cnc ?? 0) + (typeCounts.inspector ?? 0) + (typeCounts.robot ?? 0)) / stationCount;

  const sec = findSourceSnapshot(sourceSnapshots, "sec");
  const osha = findSourceSnapshot(sourceSnapshots, "osha");
  const itac = findSourceSnapshot(sourceSnapshots, "itac");
  const epa = findSourceSnapshot(sourceSnapshots, "epa");
  const nasa = findSourceSnapshot(sourceSnapshots, "nasa");
  const fred = findSourceSnapshot(sourceSnapshots, "fred");
  const eia = findSourceSnapshot(sourceSnapshots, "eia");
  const stackexchange = findSourceSnapshot(sourceSnapshots, "stackexchange");
  const reddit = findSourceSnapshot(sourceSnapshots, "reddit");
  const catalogs = findSourceSnapshot(sourceSnapshots, "catalogs");

  const eiaPrice = readNumericFromRecords(eia, ["price", "value"]);
  const nasaTemp = readNumericFromRecords(nasa, ["temp_max_c", "temp_min_c"]);
  const energyPenalty = Math.max((eiaPrice ?? 9) - 9, 0) / 100 * (0.6 + energyIntensity);
  const heatPenalty = Math.max((nasaTemp ?? 24) - 24, 0) / 120 * (0.5 + energyIntensity);
  const safetyPenalty = (osha?.state === "online" ? 0.05 : osha?.state === "partial" ? 0.03 : 0) * (0.4 + heavyOps);
  const emissionsPenalty = (epa?.state === "online" ? 0.03 : epa?.state === "partial" ? 0.015 : 0) * (0.35 + heavyOps);
  const auditLift = (itac?.state === "online" ? 0.06 : itac?.state === "partial" ? 0.03 : 0) * (0.5 + energyIntensity);
  const maintenanceLift =
    ((stackexchange?.state === "online" ? 0.03 : 0) +
      (reddit?.state === "online" ? 0.02 : 0) +
      (catalogs?.state === "online" ? 0.04 : catalogs?.state === "partial" ? 0.02 : 0)) *
    (0.4 + automation + precision);
  const marketLift =
    ((fred?.state === "online" ? 0.04 : 0) + (sec?.state === "online" ? 0.03 : 0)) *
    (0.4 + assembly + precision);

  const throughputMultiplier = clamp(
    1 + marketLift + auditLift + maintenanceLift * 0.5 - energyPenalty * 0.45 - heatPenalty * 0.35 - safetyPenalty * 0.3,
    0.72,
    1.28,
  );
  const defectMultiplier = clamp(
    1 + safetyPenalty * 0.8 + heatPenalty * 0.45 - maintenanceLift * 0.5 - auditLift * 0.25,
    0.55,
    1.45,
  );
  const downtimeMultiplier = clamp(
    1 + energyPenalty * 0.6 + heatPenalty * 0.85 + safetyPenalty + emissionsPenalty * 0.4 - maintenanceLift * 0.5 - auditLift * 0.35,
    0.55,
    1.7,
  );
  const energyCostMultiplier = clamp(1 + energyPenalty * 1.8 + heatPenalty * 0.6 - auditLift * 0.3, 0.7, 1.9);
  const revenueMultiplier = clamp(1 + marketLift * 0.8, 0.9, 1.3);
  const maintenanceCostMultiplier = clamp(1 + safetyPenalty * 0.8 + emissionsPenalty * 0.5 - maintenanceLift * 0.25, 0.8, 1.6);
  const materialCostMultiplier = clamp(1 + (sec?.state === "online" ? 0.02 : 0) * (0.4 + precision), 0.95, 1.15);

  const liveInputs = [
    eia?.state === "online" && eiaPrice != null ? `EIA ${eiaPrice.toFixed(1)} c/kWh` : null,
    nasa?.state === "online" && nasaTemp != null ? `NASA ${nasaTemp.toFixed(1)} C` : null,
    osha?.state === "online" ? "OSHA safety signal" : null,
    epa?.state === "online" ? "EPA compliance signal" : null,
    itac?.state === "online" ? "ITAC audit guidance" : null,
    stackexchange?.state === "online" || reddit?.state === "online" ? "Forum maintenance signal" : null,
    catalogs?.state === "online" ? "Catalog spec signal" : null,
    fred?.state === "online" || sec?.state === "online" ? "Market demand signal" : null,
  ].filter(Boolean);

  return {
    throughputMultiplier,
    defectMultiplier,
    downtimeMultiplier,
    energyCostMultiplier,
    revenueMultiplier,
    maintenanceCostMultiplier,
    materialCostMultiplier,
    liveInputs,
    summary:
      liveInputs.length > 0
        ? `Live adjustment factors: ${liveInputs.join(", ")}`
        : "Using local simulation defaults until live sources finish syncing.",
  };
}

function mapSnapshotStatus(snapshot) {
  const { state, count = 0, warning = "", key = "" } = snapshot ?? {};
  const loweredWarning = String(warning ?? "").toLowerCase();
  if (state === "online") return "online";
  if (state === "partial") {
    if (key === "catalogs" && count > 0) return "online";
    if (count > 0) return "degraded";
    if (loweredWarning.includes("waiting for") || loweredWarning.includes("temporarily unavailable")) {
      return "degraded";
    }
    return "syncing";
  }
  if (state === "offline") {
    if (
      key === "fred" ||
      loweredWarning.includes("waiting for") ||
      loweredWarning.includes("temporarily unavailable") ||
      loweredWarning.includes("authentication failed") ||
      loweredWarning.includes("rate limit")
    ) {
      return "degraded";
    }
    return "error";
  }
  return "idle";
}

function normalizeDatasetProfile(profile) {
  if (!profile) return datasetProfile;
  return {
    totalEstimatedSize: profile.totalEstimatedSize ?? profile.total_estimated_size ?? datasetProfile.totalEstimatedSize,
    sourceCount: profile.sourceCount ?? profile.source_count ?? datasetProfile.sourceCount,
    joinKeys: profile.joinKeys ?? profile.join_keys ?? datasetProfile.joinKeys,
    engineeringNote: profile.engineeringNote ?? profile.engineering_note ?? datasetProfile.engineeringNote,
    sources: (profile.sources ?? datasetProfile.sources).map((source, index) => ({
      name: source.name ?? datasetProfile.sources[index]?.name ?? "Source",
      acquisition: source.acquisition ?? datasetProfile.sources[index]?.acquisition ?? "",
      estimatedSize: source.estimatedSize ?? source.estimated_size ?? datasetProfile.sources[index]?.estimatedSize ?? "",
      challenge: source.challenge ?? datasetProfile.sources[index]?.challenge ?? "",
    })),
  };
}

function normalizeRagStatus(status) {
  if (!status) return { configured: false, ready: false, detail: "RAG status unavailable.", indexName: null, namespace: null, documentCount: 0, sourceBreakdown: {}, indexedAt: null, warnings: [] };
  return {
    configured: status.configured ?? false,
    ready: status.ready ?? false,
    detail: status.detail ?? "RAG status unavailable.",
    indexName: status.indexName ?? status.index_name ?? null,
    namespace: status.namespace ?? null,
    documentCount: status.documentCount ?? status.document_count ?? 0,
    sourceBreakdown: status.sourceBreakdown ?? status.source_breakdown ?? {},
    indexedAt: status.indexedAt ?? status.indexed_at ?? null,
    warnings: status.warnings ?? [],
  };
}

function ragLifecycleState(ragStatus) {
  if (!ragStatus.configured) return "idle";
  if (ragStatus.ready) return "online";
  if (String(ragStatus.detail ?? "").toLowerCase().includes("fresh sync")) return "warming";
  return "syncing";
}

function sourceEstimatedSize(snapshot, fallbackCards, profile) {
  if (snapshot?.key && PIPELINE_SIZE_BY_KEY[snapshot.key]) {
    return PIPELINE_SIZE_BY_KEY[snapshot.key];
  }
  const fallbackCard = fallbackCards.find((card) => card.name === snapshot?.name);
  if (fallbackCard?.volume) return fallbackCard.volume;
  const profileSource = profile.sources.find((source) => source.name === snapshot?.name);
  if (profileSource?.estimatedSize) return profileSource.estimatedSize;
  return profile.totalEstimatedSize;
}

function makeStationPayload(station, stationIndex) {
  return {
    id: station.id,
    position: stationIndex + 1,
    type: station.type,
    label: MACHINES[station.type]?.name ?? station.type,
    machines: station.count,
    workers: station.workers,
    worker_to_machine_ratio: Number((station.workers / Math.max(1, station.count)).toFixed(2)),
  };
}

function makeLinePayload(line, lineIndex, breakdown) {
  return {
    id: line.id,
    index: lineIndex,
    name: line.name,
    stations: line.stations.length,
    workers: line.stations.reduce((sum, station) => sum + station.workers, 0),
    machines: line.stations.reduce((sum, station) => sum + station.count, 0),
    station_details: line.stations.map((station, stationIndex) => makeStationPayload(station, stationIndex)),
    output: breakdown?.produced ?? null,
    defects: breakdown?.defects ?? null,
    downtime: breakdown?.downtime ?? null,
  };
}

function makeSelectedLinePayload(config, selectedLineIndex, results) {
  const lineIndex = config.lines[selectedLineIndex] ? selectedLineIndex : 0;
  const line = config.lines[lineIndex];
  const breakdown = results?.lineBreakdown?.[lineIndex];
  return makeLinePayload(line, lineIndex, breakdown);
}

function makeFactoryStatePayload(config, selectedLineIndex, results) {
  const lines = config.lines.map((line, lineIndex) => makeLinePayload(line, lineIndex, results?.lineBreakdown?.[lineIndex]));
  const selectedLine = lines[selectedLineIndex] ?? lines[0] ?? null;
  return {
    source: "live_client_ui",
    focused_line_index: selectedLineIndex,
    focused_line_name: selectedLine?.name ?? null,
    totals: {
      lines: config.lines.length,
      stations: config.lines.reduce((sum, line) => sum + line.stations.length, 0),
      workers: config.lines.reduce((sum, line) => sum + line.stations.reduce((lineSum, station) => lineSum + station.workers, 0), 0),
      machines: config.lines.reduce((sum, line) => sum + line.stations.reduce((lineSum, station) => lineSum + station.count, 0), 0),
    },
    lines,
  };
}

function buildPipelineSources(sourceSnapshots, fallbackCards, profile, fetchedAt) {
  if (sourceSnapshots.length) {
    return sourceSnapshots.map((snapshot) => {
      const status = mapSnapshotStatus(snapshot);
      const color = status === "online" ? C.accent : status === "degraded" ? C.warn : status === "syncing" ? C.warn : status === "error" ? C.danger : C.textDim;
      return { name: snapshot.name, status, rows: snapshot.count ? `${formatCompact(snapshot.count)} rows` : "Sampled records", size: sourceEstimatedSize(snapshot, fallbackCards, profile), last: formatRelativeTime(snapshot.updated_at ?? fetchedAt), color, summary: snapshot.summary, warning: snapshot.warning };
    }).filter((source) => !HIDDEN_SOURCE_NAMES.has(source.name));
  }
  return profile.sources.filter((source) => !HIDDEN_SOURCE_NAMES.has(source.name)).map((source, index) => ({ name: source.name, status: "idle", rows: fallbackCards[index]?.detail ?? source.challenge, size: source.estimatedSize, last: "fallback", color: C.textDim, summary: source.acquisition, warning: null }));
}

const s = {
  app: { background: C.bg, color: C.text, fontFamily: fontSans, minHeight: "100vh", display: "flex", flexDirection: "column" },
  header: { background: `${C.surface}ee`, backdropFilter: "blur(12px)", borderBottom: `1px solid ${C.border}`, padding: "10px 20px", display: "flex", alignItems: "center", gap: 12, position: "sticky", top: 0, zIndex: 50, flexWrap: "wrap" },
  nav: { display: "flex", gap: 2, marginLeft: 20, background: C.card, borderRadius: 10, padding: 3, overflowX: "auto" },
  navBtn: (active) => ({ padding: "8px 14px", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600, fontFamily: fontSans, display: "inline-flex", alignItems: "center", gap: 5, transition: "all 0.2s", background: active ? C.accent : "transparent", color: active ? C.bg : C.textDim, flexShrink: 0 }),
  main: { flex: 1, padding: "16px 20px", maxWidth: 1440, margin: "0 auto", width: "100%" },
  card: { background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: 18, marginBottom: 14 },
  cardTitle: { fontFamily: font, fontSize: 11, fontWeight: 600, color: C.textMid, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10, display: "flex", alignItems: "center", gap: 7 },
  grid: (cols) => ({ display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 14 }),
  btn: (color = C.accent) => ({ padding: "9px 18px", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 12, fontFamily: fontSans, display: "inline-flex", alignItems: "center", gap: 5, background: color, color: color === C.accent ? C.bg : "#fff", transition: "all 0.15s" }),
  btnOutline: { padding: "7px 14px", border: `1px solid ${C.border}`, borderRadius: 8, cursor: "pointer", background: "transparent", color: C.textMid, fontSize: 12, fontFamily: fontSans, fontWeight: 500, display: "inline-flex", alignItems: "center", gap: 5 },
  input: { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6, padding: "7px 11px", color: C.text, fontFamily: font, fontSize: 12, width: "100%", outline: "none" },
  badge: (color) => ({ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 9px", borderRadius: 20, fontSize: 10, fontWeight: 600, fontFamily: font, background: `${color}18`, color }),
  tag: (color = C.accent) => ({ display: "inline-flex", alignItems: "center", gap: 3, padding: "1px 7px", borderRadius: 4, fontSize: 10, fontFamily: font, background: `${color}15`, color, fontWeight: 600 }),
  dot: (color) => ({ width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0 }),
};

function Metric({ icon: Icon, label, value, unit, color = C.accent, sub }) {
  return (
    <div style={{ ...s.card, padding: 14, display: "flex", alignItems: "flex-start", gap: 11 }}>
      <div style={{ width: 36, height: 36, borderRadius: 9, background: `${color}12`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <Icon size={16} color={color} />
      </div>
      <div>
        <div style={{ fontSize: 10, color: C.textDim, fontFamily: font, letterSpacing: "0.04em", marginBottom: 1 }}>{label}</div>
        <div style={{ fontFamily: font, fontSize: 20, fontWeight: 700, color }}>{value}{unit ? <span style={{ fontSize: 11, color: C.textDim, marginLeft: 3 }}>{unit}</span> : null}</div>
        {sub ? <div style={{ fontSize: 10, color: C.textDim, marginTop: 1 }}>{sub}</div> : null}
      </div>
    </div>
  );
}

function StatusPill({ status, label }) {
  const colors = { online: C.accent, degraded: C.warn, syncing: C.warn, warming: C.warn, error: C.danger, idle: C.textDim };
  const color = colors[status] || C.textDim;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: C.textMid }}>
      <div style={{ ...s.dot(color), animation: ["syncing", "warming"].includes(status) ? "pulse 1.5s ease-in-out infinite" : "none" }} />
      <span>{label}</span>
    </div>
  );
}

function FloorTab({ config, setConfig, selectedLineIndex, setSelectedLineIndex }) {
  function addStation(lineIndex) {
    const next = JSON.parse(JSON.stringify(config));
    const maxId = Math.max(...next.lines.flatMap((line) => line.stations.map((station) => station.id)), 0);
    next.lines[lineIndex].stations.push({ id: maxId + 1, type: "assembler", count: 1, workers: 2 });
    setConfig(next);
  }
  function removeStation(lineIndex, stationIndex) {
    const next = JSON.parse(JSON.stringify(config));
    next.lines[lineIndex].stations.splice(stationIndex, 1);
    setConfig(next);
  }
  function updateStation(lineIndex, stationIndex, key, value) {
    const next = JSON.parse(JSON.stringify(config));
    next.lines[lineIndex].stations[stationIndex][key] = value;
    setConfig(next);
  }
  function addLine() {
    const next = JSON.parse(JSON.stringify(config));
    const maxId = Math.max(...next.lines.flatMap((line) => line.stations.map((station) => station.id)), 0);
    next.lines.push({ id: next.lines.length + 1, name: `Line ${String.fromCharCode(65 + next.lines.length)}`, stations: [{ id: maxId + 1, type: "assembler", count: 1, workers: 2 }] });
    setConfig(next);
  }
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, gap: 14, flexWrap: "wrap" }}>
        <div><h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Factory Floor Layout</h2><p style={{ fontSize: 12, color: C.textDim, margin: "3px 0 0" }}>Design production lines, add machines, allocate workers</p></div>
        <button style={s.btn()} onClick={addLine}><Plus size={13} /> Add Line</button>
      </div>
      {config.lines.map((line, lineIndex) => (
        <div key={line.id} style={{ ...s.card, borderColor: lineIndex === selectedLineIndex ? C.accent : C.border, cursor: "pointer" }} onClick={() => setSelectedLineIndex(lineIndex)}>
          <div style={{ ...s.cardTitle, marginBottom: 12 }}><Layers size={13} color={C.accent} />{line.name}<span style={s.badge(C.info)}>{line.stations.length} stations</span><span style={s.badge(C.purple)}>{line.stations.reduce((sum, station) => sum + station.workers, 0)} workers</span></div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, overflowX: "auto", paddingBottom: 8 }}>
            <div style={{ background: `${C.accent}15`, border: `1px dashed ${C.accent}`, borderRadius: 8, padding: "8px 12px", textAlign: "center", flexShrink: 0 }}><Package size={14} color={C.accent} /><div style={{ fontSize: 9, color: C.accent, fontWeight: 600, marginTop: 1 }}>IN</div></div>
            {line.stations.map((station, stationIndex) => {
              const machine = MACHINES[station.type];
              const Icon = machine.icon;
              return (
                <div key={station.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <ArrowRight size={12} color={C.textDim} />
                  <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: 12, minWidth: 145, position: "relative" }}>
                    <button onClick={(event) => { event.stopPropagation(); removeStation(lineIndex, stationIndex); }} style={{ position: "absolute", top: 3, right: 3, background: "none", border: "none", cursor: "pointer", color: C.textDim, padding: 2 }}><Trash2 size={10} /></button>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 7 }}>
                      <Icon size={16} color={C.accent} />
                      <select value={station.type} onClick={(event) => event.stopPropagation()} onChange={(event) => updateStation(lineIndex, stationIndex, "type", event.target.value)} style={{ ...s.input, padding: "3px 5px", fontSize: 11, flex: 1 }}>
                        {Object.entries(MACHINES).map(([key, value]) => <option key={key} value={key}>{value.name}</option>)}
                      </select>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      {[["count", "Machines"], ["workers", "Workers"]].map(([key, label]) => (
                        <div key={key} style={{ flex: 1 }}>
                          <div style={{ fontSize: 9, color: C.textDim, marginBottom: 2 }}>{label}</div>
                          <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
                            <button onClick={(event) => { event.stopPropagation(); updateStation(lineIndex, stationIndex, key, Math.max(1, station[key] - 1)); }} style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 4, width: 20, height: 20, cursor: "pointer", color: C.text, display: "flex", alignItems: "center", justifyContent: "center" }}><Minus size={10} /></button>
                            <span style={{ fontFamily: font, fontSize: 13, fontWeight: 700, minWidth: 16, textAlign: "center" }}>{station[key]}</span>
                            <button onClick={(event) => { event.stopPropagation(); updateStation(lineIndex, stationIndex, key, station[key] + 1); }} style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 4, width: 20, height: 20, cursor: "pointer", color: C.text, display: "flex", alignItems: "center", justifyContent: "center" }}><Plus size={10} /></button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
            <ArrowRight size={12} color={C.textDim} />
            <div style={{ background: `${C.accent}15`, border: `1px dashed ${C.accent}`, borderRadius: 8, padding: "8px 12px", textAlign: "center", flexShrink: 0 }}><Truck size={14} color={C.accent} /><div style={{ fontSize: 9, color: C.accent, fontWeight: 600, marginTop: 1 }}>OUT</div></div>
            <button style={s.btnOutline} onClick={(event) => { event.stopPropagation(); addStation(lineIndex); }}><Plus size={11} /></button>
          </div>
        </div>
      ))}
      <div style={s.card}>
        <div style={s.cardTitle}><Settings size={13} color={C.accent} />Factory Parameters</div>
        <div style={s.grid(4)}>
          {[["shiftHours", "Shift (hrs)", 1], ["shiftsPerDay", "Shifts/Day", 1], ["daysPerWeek", "Days/Week", 1], ["laborCost", "Labor $/hr", 1], ["electricityCost", "Electric $/kWh", 0.01], ["materialCost", "Material $/unit", 1], ["sellPrice", "Sell $/unit", 1]].map(([key, label, step]) => (
            <div key={key}><label style={{ fontSize: 10, color: C.textDim, display: "block", marginBottom: 3 }}>{label}</label><input type="number" value={config[key]} step={step} onChange={(event) => setConfig({ ...config, [key]: Number(event.target.value) })} style={s.input} /></div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SimTab({ config, results, running, progress, onRun, selectedLineIndex, setSelectedLineIndex }) {
  const selectedLine = config.lines[selectedLineIndex] ?? config.lines[0];
  const selectedLineResult = results?.lineBreakdown?.[selectedLineIndex] ?? null;
  const costBreakdown = selectedLineResult
    ? [
        { name: "Labor", value: selectedLineResult.labor },
        { name: "Materials", value: selectedLineResult.material },
        { name: "Energy", value: selectedLineResult.energy },
        { name: "Maintenance", value: selectedLineResult.maintenance },
      ]
    : [];
  return (
    <div>
      <div style={{ ...s.card, display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ flex: 1 }}><div style={{ fontSize: 14, fontWeight: 700, marginBottom: 3 }}>Run Simulation</div><div style={{ fontSize: 11, color: C.textDim }}>Selected line: {selectedLine.name}. Live source modifiers are applied per line before forecasting.</div>{selectedLineResult?.liveInputs?.length ? <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>{selectedLineResult.liveInputs.map((input) => <span key={input} style={s.tag(C.info)}>{input}</span>)}</div> : null}</div>
        <select value={selectedLineIndex} onChange={(event) => setSelectedLineIndex(Number(event.target.value))} style={{ ...s.input, width: 220 }}>
          {config.lines.map((line, index) => <option key={line.id} value={index}>{line.name}</option>)}
        </select>
        <button style={s.btn(running ? C.danger : C.accent)} onClick={onRun} disabled={running}>{running ? <><Loader size={14} style={{ animation: "pulse 1.2s ease-in-out infinite" }} /> Simulating...</> : <><Play size={14} /> Run</>}</button>
      </div>
      {running ? <div style={s.card}><div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: C.textDim, marginBottom: 4 }}><span>Processing current line configuration through the simulation engine...</span><span style={{ fontFamily: font, color: C.accent }}>{progress.toFixed(0)}%</span></div><div style={{ background: C.surface, borderRadius: 20, height: 6, overflow: "hidden" }}><div style={{ background: `linear-gradient(90deg, ${C.accent}, ${C.cyan})`, height: "100%", width: `${progress}%`, borderRadius: 20, transition: "width 0.1s" }} /></div></div> : null}
      {selectedLineResult ? <>
        <div style={s.grid(4)}>
          <Metric icon={Package} label="UNITS PRODUCED" value={selectedLineResult.produced.toLocaleString()} color={C.accent} sub={selectedLine.name} />
          <Metric icon={Gauge} label="OEE SCORE" value={(selectedLineResult.oee * 100).toFixed(1)} unit="%" color={selectedLineResult.oee > 0.7 ? C.accent : C.warn} sub={selectedLineResult.liveSummary} />
          <Metric icon={DollarSign} label="WEEKLY PROFIT" value={`$${(selectedLineResult.profit / 1000).toFixed(0)}K`} color={selectedLineResult.profit > 0 ? C.accent : C.danger} sub={`${selectedLineResult.machines} machines · ${selectedLineResult.workers} workers`} />
          <Metric icon={AlertTriangle} label="DEFECT RATE" value={(selectedLineResult.defectRate * 100).toFixed(2)} unit="%" color={selectedLineResult.defectRate < 0.02 ? C.accent : C.warn} sub={`${Math.round(selectedLineResult.downtime)} downtime min`} />
        </div>
        <div style={s.grid(2)}>
          <div style={s.card}><div style={s.cardTitle}><TrendingUp size={13} color={C.accent} />Production Over Time - {selectedLine.name}</div><ResponsiveContainer width="100%" height={220}><AreaChart data={selectedLineResult.timeline}><defs><linearGradient id="production-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.accent} stopOpacity={0.25} /><stop offset="95%" stopColor={C.accent} stopOpacity={0} /></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke={C.border} /><XAxis dataKey="hour" stroke={C.textDim} tick={{ fontSize: 9 }} /><YAxis stroke={C.textDim} tick={{ fontSize: 9 }} /><Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, fontFamily: font, fontSize: 11 }} /><Area type="monotone" dataKey="produced" stroke={C.accent} fill="url(#production-gradient)" strokeWidth={2} /></AreaChart></ResponsiveContainer></div>
          <div style={s.card}><div style={s.cardTitle}><DollarSign size={13} color={C.warn} />Cost Breakdown - {selectedLine.name}</div><ResponsiveContainer width="100%" height={220}><PieChart><Pie data={costBreakdown} cx="50%" cy="50%" outerRadius={75} innerRadius={42} paddingAngle={3} dataKey="value">{[C.info, C.purple, C.orange, C.cyan].map((color) => <Cell key={color} fill={color} />)}</Pie><Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, fontFamily: font, fontSize: 11 }} formatter={(value) => `$${(Number(value) / 1000).toFixed(1)}K`} /><Legend wrapperStyle={{ fontSize: 10 }} /></PieChart></ResponsiveContainer></div>
        </div>
      </> : null}
    </div>
  );
}

function AdvisorTab({ config, results, ragStatus, sourceSnapshots, selectedLineIndex, messages, input, setInput, loading, error, onSend }) {
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);
  const onlineSources = sourceSnapshots.filter((snapshot) => snapshot.state === "online").length;
  const totalSources = sourceSnapshots.length || 7;
  const selectedLine = makeSelectedLinePayload(config, selectedLineIndex, results);
  return (
    <div>
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ width: 220, flexShrink: 0 }}>
          <div style={s.card}>
            <div style={s.cardTitle}><Workflow size={13} color={C.purple} />Agent Status</div>
            {[["Supervisor", "online", C.accent], ["Retriever", ragLifecycleState(ragStatus), ragStatus.ready ? C.accent : ragStatus.configured ? C.warn : C.textDim], ["Live Sources", onlineSources ? "online" : "error", onlineSources ? C.accent : C.danger], ["Focused Line", selectedLine.name, C.info]].map(([name, state, color]) => (
              <div key={name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "5px 0", borderBottom: `1px solid ${C.border}` }}>
                <span style={{ fontSize: 11, color: C.textMid }}>{name}</span>
                {typeof state === "string" && ["online", "degraded", "syncing", "warming", "idle", "error"].includes(state) ? <div style={{ ...s.dot(color) }} /> : <span style={{ fontSize: 10, color: C.info, fontFamily: font }}>{state}</span>}
              </div>
            ))}
          </div>
          <div style={s.card}>
            <div style={s.cardTitle}><Database size={13} color={C.info} />Retrieval</div>
            {[["Pinecone Index", ragStatus.indexName ?? "Configured"], ["Voyage Embeddings", ragStatus.configured ? "Ready" : "Idle"], ["Indexed Chunks", ragStatus.documentCount ? formatCompact(ragStatus.documentCount) : "0"], ["Live Inputs", `${onlineSources}/${totalSources}`]].map(([name, value]) => (
              <div key={name} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 11 }}><span style={{ color: C.textDim }}>{name}</span><span style={{ color: C.accent, fontFamily: font, fontSize: 10 }}>{value}</span></div>
            ))}
          </div>
          <div style={s.card}>
            <div style={s.cardTitle}><Shield size={13} color={C.warn} />Guardrails</div>
            {[["Citation grounding", true], ["Live source context", true], ["Provider fallback", true], ["Free-form chat", true]].map(([name, enabled]) => (
              <div key={name} style={{ display: "flex", alignItems: "center", gap: 5, padding: "3px 0", fontSize: 11, color: C.textMid }}>{enabled ? <CheckCircle size={12} color={C.accent} /> : <XCircle size={12} color={C.danger} />}<span>{name}</span></div>
            ))}
          </div>
        </div>
        <div style={{ ...s.card, flex: 1, display: "flex", flexDirection: "column", height: 520, padding: 0, overflow: "hidden", minWidth: 320 }}>
          <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 8 }}>
            <Brain size={16} color={C.accent} /><span style={{ fontSize: 13, fontWeight: 600 }}>AI Manufacturing Advisor</span>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>{[["Claude", C.accent], ["Voyage", C.info], ["Pinecone", C.warn]].map(([name, color]) => <span key={name} style={s.tag(color)}>{name}</span>)}</div>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
            {messages.length === 0 ? <div style={{ textAlign: "center", padding: "50px 20px" }}><Brain size={36} color={C.accent} style={{ marginBottom: 10, opacity: 0.6 }} /><div style={{ fontSize: 14, fontWeight: 600, color: C.textMid, marginBottom: 5 }}>Ask your AI Advisor</div><div style={{ fontSize: 11, color: C.textDim, marginBottom: 16 }}>Free-form project, operations, architecture, market, and live-source questions</div></div> : null}
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} style={{ display: "flex", justifyContent: message.role === "user" ? "flex-end" : "flex-start", marginBottom: 10 }}>
                <div style={{ maxWidth: "78%", padding: "9px 13px", borderRadius: 12, fontSize: 12, lineHeight: 1.6, background: message.role === "user" ? C.accent : C.surface, color: message.role === "user" ? C.bg : C.text, border: message.role === "user" ? "none" : `1px solid ${C.border}`, whiteSpace: "pre-wrap" }}>
                  {message.content}
                  {message.citations?.length ? <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>{message.citations.map((citation) => <span key={citation} style={s.tag(C.info)}>{citation}</span>)}</div> : null}
                </div>
              </div>
            ))}
            {loading ? <div style={{ display: "flex", gap: 5, padding: 10 }}>{[0, 1, 2].map((value) => <div key={value} style={{ width: 7, height: 7, borderRadius: "50%", background: C.accent, animation: `pulse 1.2s ease-in-out ${value * 0.2}s infinite` }} />)}</div> : null}
            <div ref={endRef} />
          </div>
          <div style={{ borderTop: `1px solid ${C.border}`, padding: 10, display: "flex", gap: 7 }}>
            <input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onSend(input); } }} placeholder="Ask about bottlenecks, architecture, data sources, companies, or optimization..." style={{ ...s.input, flex: 1 }} />
            <button onClick={() => onSend(input)} disabled={loading || !input.trim()} style={{ ...s.btn(), opacity: loading || !input.trim() ? 0.4 : 1 }}><Send size={14} /></button>
          </div>
          {error ? <div style={{ padding: "0 14px 12px", color: C.danger, fontSize: 11 }}>{error}</div> : null}
        </div>
      </div>
    </div>
  );
}

function PipelineTab({ sources, ragStatus, profile, fetchedAt, dashboardError }) {
  const totalRows = sources.reduce((sum, source) => {
    const match = source.rows.match(/([\d.]+)([MK])?/);
    if (!match) return sum;
    return sum + Number(match[1]) * (match[2] === "M" ? 1000000 : match[2] === "K" ? 1000 : 1);
  }, 0);
  const onlineCount = sources.filter((source) => source.status === "online").length;
  const degradedCount = sources.filter((source) => source.status === "degraded").length;
  const syncingCount = sources.filter((source) => ["syncing", "warming"].includes(source.status)).length;
  const pipelineHealth = Math.round(((onlineCount + degradedCount * 0.8 + syncingCount * 0.6) / Math.max(1, sources.length)) * 100);
  const freshness = fetchedAt ? Math.max(1, Math.round((Date.now() - new Date(fetchedAt).getTime()) / 60000)) : 0;
  const jobs = [
    { name: "Dashboard refresh", status: dashboardError ? "running" : "success", detail: dashboardError ? "Fallback payload active while live adapters recover." : `Last sync ${formatRelativeTime(fetchedAt)}` },
    { name: "Vector index", status: ragStatus.ready ? "success" : ragStatus.configured ? "running" : "pending", detail: ragStatus.ready ? `${formatCompact(ragStatus.documentCount)} chunks indexed` : ragStatus.detail },
    { name: "Source joins", status: onlineCount ? "success" : "running", detail: `Join keys: ${profile.joinKeys.join(", ")}` },
    { name: "Advisor packaging", status: ragStatus.configured ? "success" : "pending", detail: `Namespace: ${ragStatus.namespace ?? "default"}` },
  ];
  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 14px" }}>Data Pipeline Status</h2>
      <div style={s.grid(4)}>
        <Metric icon={Database} label="TOTAL RECORDS" value={totalRows ? formatCompact(totalRows) : "sampled"} color={C.info} />
        <Metric icon={Server} label="STORAGE" value={profile.totalEstimatedSize.replace("+", "")} color={C.purple} />
        <Metric icon={Activity} label="PIPELINE HEALTH" value={pipelineHealth.toFixed(1)} unit="%" color={C.accent} />
        <Metric icon={Clock} label="SYNC AGE" value={fetchedAt ? freshness : 0} unit="min" color={C.cyan} />
      </div>
      <div style={s.card}>
        <div style={s.cardTitle}><Database size={13} color={C.info} />Data Sources ({sources.length} Active)</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {sources.map((source) => (
            <div key={source.name} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 14px", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={s.dot(source.color)} />
              <div style={{ flex: 1 }}><div style={{ fontSize: 12, fontWeight: 600 }}>{source.name}</div><div style={{ fontSize: 10, color: C.textDim }}>{source.rows} · {source.size} · {source.last}</div></div>
              <span style={s.badge(source.status === "online" ? C.accent : ["degraded", "syncing", "warming"].includes(source.status) ? C.warn : source.status === "error" ? C.danger : C.textDim)}>{source.status}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={s.card}>
        <div style={s.cardTitle}><Workflow size={13} color={C.purple} />Pipeline Jobs</div>
        {jobs.map((job) => (
          <div key={job.name} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${C.border}` }}>
            {job.status === "running" ? <Loader size={14} color={C.warn} /> : job.status === "success" ? <CheckCircle size={14} color={C.accent} /> : <Clock size={14} color={C.textDim} />}
            <div style={{ flex: 1 }}><div style={{ fontSize: 12, fontWeight: 500 }}>{job.name}</div><div style={{ fontSize: 10, color: C.textDim }}>{job.detail}</div></div>
            <span style={s.badge(job.status === "running" ? C.warn : job.status === "success" ? C.accent : C.textDim)}>{job.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("floor");
  const [config, setConfig] = useState(defaultConfig());
  const [results, setResults] = useState(null);
  const [selectedLineIndex, setSelectedLineIndex] = useState(0);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dashboardData, setDashboardData] = useState(null);
  const [ragStatus, setRagStatus] = useState(null);
  const [dashboardError, setDashboardError] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const ragReindexTriggeredRef = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const [dashboardResult, ragResult] = await Promise.allSettled([fetchDashboardSnapshot(controller.signal), fetchRagStatus(controller.signal)]);
      if (dashboardResult.status === "fulfilled") { setDashboardData(dashboardResult.value); setDashboardError(""); } else { setDashboardError(dashboardResult.reason?.message ?? "Failed to load dashboard data."); }
      if (ragResult.status === "fulfilled") {
        setRagStatus(ragResult.value);
        if ((ragResult.value?.configured ?? false) && !(ragResult.value?.ready ?? false) && !ragReindexTriggeredRef.current) {
          ragReindexTriggeredRef.current = true;
          setRagStatus((current) => ({
            ...(current ?? ragResult.value),
            detail: "Refreshing the Pinecone index in the background.",
          }));
          try {
            const rebuilt = await rebuildRagIndex();
            if (!controller.signal.aborted) {
              setRagStatus(rebuilt);
              if (rebuilt?.ready) {
                ragReindexTriggeredRef.current = false;
              }
            }
          } catch {
            if (!controller.signal.aborted) {
              setRagStatus((current) => ({
                ...(current ?? ragResult.value),
                detail: "Pinecone index is stale. Reindex is available from the backend.",
              }));
              ragReindexTriggeredRef.current = false;
            }
          }
        }
      }
    }
    void load();
    const refreshTimer = window.setInterval(() => {
      void load();
    }, 30000);
    return () => {
      window.clearInterval(refreshTimer);
      controller.abort();
    };
  }, []);
  const remoteDatasetProfile = useMemo(() => normalizeDatasetProfile(dashboardData?.datasetProfile), [dashboardData]);
  const remoteSourceCards = dashboardData?.sourceCards ?? dataSourceCards;
  const remoteSourceSnapshots = dashboardData?.sourceSnapshots ?? [];
  const remoteLiveFeed = (dashboardData?.liveFeed ?? liveFeed).filter((item) => !HIDDEN_SOURCE_NAMES.has(item.source));
  const remoteRagStatus = normalizeRagStatus(ragStatus);
  const pipelineSources = useMemo(() => buildPipelineSources(remoteSourceSnapshots, remoteSourceCards, remoteDatasetProfile, dashboardData?.fetched_at), [remoteSourceSnapshots, remoteSourceCards, remoteDatasetProfile, dashboardData]);
  const platformPills = [{ label: "FastAPI", status: dashboardError ? "error" : "online" }, { label: "Pinecone", status: ragLifecycleState(remoteRagStatus) }, { label: "Voyage", status: remoteRagStatus.configured ? "online" : "idle" }];
  const workerTotal = config.lines.reduce((sum, line) => sum + line.stations.reduce((lineSum, station) => lineSum + station.workers, 0), 0);
  const machineTotal = config.lines.reduce((sum, line) => sum + line.stations.reduce((lineSum, station) => lineSum + station.count, 0), 0);
  function runSimulation() {
    if (running) return;
    setRunning(true);
    setProgress(0);
    let value = 0;
    const timer = window.setInterval(() => {
      value += Math.random() * 18 + 4;
      if (value >= 100) { window.clearInterval(timer); setResults(simulate(config, remoteSourceSnapshots)); setProgress(100); setRunning(false); return; }
      setProgress(Math.min(value, 100));
    }, 100);
  }
  function resetConsole() {
    setConfig(defaultConfig());
    setResults(null);
    setProgress(0);
    setRunning(false);
    setSelectedLineIndex(0);
    setMessages([]);
    setInput("");
    setChatError("");
  }
  async function handleSend(text) {
    const question = text.trim();
    if (!question || chatLoading) return;
    const nextMessages = [...messages, { role: "user", content: question, citations: [] }];
    const selectedLine = makeSelectedLinePayload(config, selectedLineIndex, results);
    const factoryState = makeFactoryStatePayload(config, selectedLineIndex, results);
    setMessages(nextMessages);
    setInput("");
    setChatError("");
    setChatLoading(true);
    try {
      const response = await sendChatQuestion({
        question,
        history: nextMessages.map(({ role, content }) => ({ role, content })),
        active_view: tab,
        selected_line: selectedLine,
        factory_state: factoryState,
      });
      setMessages((current) => [...current, { role: "assistant", content: response.answer, citations: response.citations ?? [] }]);
    } catch (error) {
      setChatError(error.message ?? "Chat request failed.");
      setMessages((current) => current.slice(0, -1));
    } finally {
      setChatLoading(false);
    }
  }
  const tabs = [{ id: "floor", label: "Factory Floor", icon: Factory }, { id: "sim", label: "Simulate", icon: Play }, { id: "advisor", label: "AI Advisor", icon: Brain }, { id: "pipeline", label: "Data Pipeline", icon: Database }];
  return (
    <div style={s.app}>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
      <style>{`@keyframes pulse{0%,80%,100%{opacity:.3;transform:scale(.8)}40%{opacity:1;transform:scale(1.2)}} ::-webkit-scrollbar{width:5px;height:5px} ::-webkit-scrollbar-track{background:${C.bg}} ::-webkit-scrollbar-thumb{background:${C.border};border-radius:4px}`}</style>
      <div style={s.header}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: `linear-gradient(135deg, ${C.accent}, ${C.cyan})`, display: "flex", alignItems: "center", justifyContent: "center" }}><Cpu size={17} color={C.bg} /></div>
        <div><div style={{ fontFamily: font, fontSize: 14, fontWeight: 700, letterSpacing: "0.05em", color: C.accent }}>DIGITAL TWIN</div><div style={{ fontSize: 9, color: C.textDim, fontFamily: font, letterSpacing: "0.1em" }}>FACTORY SIMULATOR</div></div>
        <div style={s.nav}>{tabs.map((item) => <button key={item.id} onClick={() => setTab(item.id)} style={s.navBtn(tab === item.id)}><item.icon size={13} />{item.label}</button>)}</div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          {platformPills.map((pill) => <StatusPill key={pill.label} status={pill.status} label={pill.label} />)}
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}><Users size={12} color={C.textDim} /><span style={{ fontFamily: font, fontSize: 12, color: C.textMid }}>{workerTotal}</span></div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}><Cpu size={12} color={C.textDim} /><span style={{ fontFamily: font, fontSize: 12, color: C.textMid }}>{machineTotal}</span></div>
          <button onClick={resetConsole} style={s.btnOutline}><RotateCcw size={11} /> Reset</button>
        </div>
      </div>
      <div style={s.main}>
        {tab === "floor" ? <FloorTab config={config} setConfig={setConfig} selectedLineIndex={selectedLineIndex} setSelectedLineIndex={setSelectedLineIndex} /> : null}
        {tab === "sim" ? <SimTab config={config} results={results} running={running} progress={progress} onRun={runSimulation} selectedLineIndex={selectedLineIndex} setSelectedLineIndex={setSelectedLineIndex} /> : null}
        {tab === "advisor" ? <AdvisorTab config={config} results={results} ragStatus={remoteRagStatus} sourceSnapshots={remoteSourceSnapshots} selectedLineIndex={selectedLineIndex} messages={messages} input={input} setInput={setInput} loading={chatLoading} error={chatError} onSend={handleSend} /> : null}
        {tab === "pipeline" ? <PipelineTab sources={pipelineSources} ragStatus={remoteRagStatus} profile={remoteDatasetProfile} fetchedAt={dashboardData?.fetched_at} dashboardError={dashboardError} /> : null}
        {dashboardError ? <div style={{ ...s.card, marginTop: 14, padding: 12, color: C.warn, fontSize: 11 }}>Live backend data is temporarily unavailable. The interface is falling back to the bundled demo payload until the API reconnects.</div> : null}
        {tab !== "advisor" && remoteLiveFeed.length ? <div style={{ ...s.card, marginTop: 14 }}><div style={s.cardTitle}><Zap size={13} color={C.accent} />Live Telemetry Feed</div><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>{remoteLiveFeed.slice(0, 4).map((item) => <div key={`${item.source}-${item.text}`} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 14px" }}><div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 4 }}><strong style={{ fontSize: 11 }}>{item.source}</strong><span style={s.tag(item.tone === "alert" ? C.danger : item.tone === "warn" ? C.warn : C.accent)}>{item.tone}</span></div><div style={{ fontSize: 11, color: C.textMid, lineHeight: 1.5 }}>{item.text}</div></div>)}</div></div> : null}
      </div>
    </div>
  );
}
