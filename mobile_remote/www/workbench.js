const STORAGE_KEY = "chatboks-workbench";
const SESSION_POLL_MS = 2500;
const SESSION_POLL_BUSY_MS = 1500;
const WORKBENCH_POLL_MS = 10000;
const LANE_MESSAGE_LIMIT = 10;
const LANE_AGENT_LIMIT = 3;
const COORD_FEED_LIMIT = 6;
const COORD_FEED_EXPANDED_LIMIT = 40;
const DEFAULT_AGENTS = ["claude", "codex", "gemini"];

const KNOWN_AGENT_STYLES = new Set(["claude", "codex", "gemini", "antigravity", "codex_spark", "coordinator"]);
const AGENT_LABELS = {
  codex_spark: "Codex Spark",
  coordinator: "Coordinator",
};
const AGENT_GLYPHS = {
  codex_spark: "SX",
  coordinator: "CO",
};
const LANE_LABELS = {
  coordinator: "Gemma",
};
const LANE_GLYPHS = {
  coordinator: "GM",
};

const state = {
  token: "",
  bridgeUrl: "",
  theme: "dark",
  connected: false,
  eventCursor: 0,
  sessionTimer: null,
  workbenchTimer: null,
  commandRunning: false,
  agents: [],
  directAgents: [],
  lanes: {},
  streams: {},
  coordItems: [],
  coordExpanded: false,
  showSystemFeed: false,
  currentProject: "",
  lastActivity: "",
  connectionFailures: 0,
  authBlocked: false,
  approvalActive: false,
  approvalProposalId: "",
  approvalSubmitting: false,
};

const previewSession = {
  project: "chatboks",
  projects: ["chatboks", "gracious-eagle-otel", "romantic-otter-otel-7", "chatboks_2.0"],
  session: "multi-agent-refactor",
  session_history: [
    { name: "multi-agent-refactor", age: "2m ago" },
    { name: "remote-control-impl", age: "15m ago" },
    { name: "io-tools-integration", age: "1h ago" },
    { name: "graphify-phase5", age: "1d ago" },
  ],
  status: "active",
  active_task: "multi-agent-refactor",
  next_agent: "codex",
  round: 3,
  expected_agents: DEFAULT_AGENTS,
  completed_agents: ["claude", "codex", "gemini"],
  collaboration_mode: "Default",
  context_mode: "full",
  command_running: false,
  command_text: "",
  agents: DEFAULT_AGENTS,
  lane_agents: DEFAULT_AGENTS,
  agent_statuses: {},
  direct_agents: ["coordinator"],
  token_usage: [
    { agent: "claude", used: 42, limit: 100, warning: 80, percent: 42 },
    { agent: "codex", used: 26, limit: 100, warning: 80, percent: 26 },
    { agent: "gemini", used: 86, limit: 100, warning: 80, percent: 86 },
  ],
  session_budget: null,
  transcript: [
    {
      sender: "claude",
      text: "Claude - Architecture, Security, and Synthesis\n\nPresent and indexed. CodeGraph shows the project is healthy.\n\nCurrent branch: main. Pending uncommitted changes across tests and mobile remote.\n\nADD\nFocus areas: architecture, risk analysis, synthesis, and coordination.\n>>> HANDOFF >> Codex",
    },
    {
      sender: "codex",
      text: "Received handoff from Claude. Starting implementation tasks.\n\n- Added tailnet fallback build\n- Fixed minor import paths\n- Added tests for remote control\n- Updated docs and README\n\nVERIFY\nChanges applied and tests added.\n\nImplementation complete. All tests passing locally.\n>>> HANDOFF >> Gemini",
    },
    {
      sender: "gemini",
      text: "Received handoff from Codex. Running verification and integration checks.\n\n- Verified remote control flows\n- Graph status consistent\n- Sleep memory features intact\n- No regressions detected\n\nAll checks passed.\n\nIntegration verified. Ready for final report.\n>>> TASK_COMPLETE",
    },
  ],
  events: [
    { id: 1, sender: "system", kind: "summary_packet", timestamp: "12:12:06", text: "Summary: Refactor and integration tasks completed across agents." },
  ],
  trace: {
    agent: [
      { message_id: 1, agent: "claude", signal: "HANDOFF", target: "Codex", summary: "Architecture and security pass complete." },
      { message_id: 2, agent: "codex", signal: "HANDOFF", target: "Gemini", summary: "Implementation complete; tests passing locally." },
      { message_id: 3, agent: "gemini", signal: "TASK_COMPLETE", target: null, summary: "Integration verified." },
    ],
    packets: [
      { agent: "codex", stance: "VERIFY", signal: "TASK_COMPLETE", observed_count: 3, risk_count: 0, next_action: "Ready for final report." },
    ],
  },
};

const els = {};
for (const id of [
  "themeToggle", "themeToggleRail", "newTaskButton", "projectList", "sessionList",
  "tokenBalances", "settingsButton", "stripCpu", "stripRam",
  "topbarProject", "topbarSession", "topbarStatus", "liveButton", "liveDot", "liveLabel",
  "sessionButton", "connectionToggle", "connectionPanel", "pairCode", "token", "pairButton",
  "bridgeUrl", "connectButton", "forgetButton", "errorBox", "connectionState", "connectionRecovery",
  "agentLanes", "coordDot", "coordState", "roleCallButton", "systemFeedButton", "logsButton",
  "approvalPanel", "approvalMeta", "approvalSummary", "approvalEstimate",
  "approvalHelper", "approvalRaw", "approvalModification", "approvalStatus", "approvalCommandPreview",
  "approveButton", "modifyButton", "rejectButton", "dismissButton",
    "coordTime", "coordFeed", "statRound", "statMode", "statNext", "statStatus",
    "traceAgentCount", "traceAgentList", "tracePacketCount", "tracePacketList",
    "workbenchPrompt", "sendStatus", "sendButton",
  "envProject", "envBranch", "envCleanDot", "envClean", "envChanges", "envCommit",
  "progressList", "progressCount", "progressPercent",
  "graphDot", "graphHealth", "graphFiles", "graphNodes", "graphEdges", "graphIndexed",
  "monTailscale", "monCpu", "monRam",
  "terminalFocus", "terminalCaption",
]) {
  els[id] = document.getElementById(id);
}

/* ---------- settings ---------- */

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    state.token = saved.token || "";
    state.bridgeUrl = saved.bridgeUrl || "";
    state.theme = saved.theme === "light" ? "light" : "dark";
  } catch {
    state.token = "";
    state.bridgeUrl = "";
  }
  els.token.value = state.token;
  els.bridgeUrl.value = state.bridgeUrl || "";
}

function saveSettings() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: state.token, bridgeUrl: state.bridgeUrl, theme: state.theme }));
}

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  els.themeToggle.textContent = theme === "dark" ? "Light" : "Dark";
  saveSettings();
}

function enforceLeftToRightText(element) {
  if (!element) {
    return;
  }
  element.dir = "ltr";
  element.style.direction = "ltr";
  element.style.textAlign = "left";
  element.style.unicodeBidi = "plaintext";
}

/* ---------- connection ---------- */

function showError(message, tone = "error") {
  els.errorBox.textContent = message || "";
  els.errorBox.classList.toggle("hidden", !message);
  els.errorBox.classList.toggle("success", Boolean(message) && tone === "success");
  if (message) {
    els.connectionPanel.classList.remove("hidden");
  }
}

function setConnectionState(message, tone = "muted") {
  els.connectionState.textContent = message;
  els.connectionState.classList.toggle("muted", tone === "muted");
  els.connectionState.classList.toggle("success", tone === "success");
  els.connectionState.classList.toggle("warning", tone === "warning");
  els.connectionState.classList.toggle("error-state", tone === "error");
}

function setConnectionPanel(visible) {
  els.connectionPanel.classList.toggle("hidden", !visible);
}

function setConnectionRecovery(title = "", steps = []) {
  els.connectionRecovery.innerHTML = "";
  els.connectionRecovery.classList.toggle("hidden", !steps.length);
  if (!steps.length) {
    return;
  }
  const label = document.createElement("strong");
  label.textContent = title || "Try this next";
  const list = document.createElement("ul");
  for (const step of steps) {
    const item = document.createElement("li");
    item.textContent = step;
    list.appendChild(item);
  }
  els.connectionRecovery.appendChild(label);
  els.connectionRecovery.appendChild(list);
}

function setConnectionBusy(button, busy, busyText) {
  if (!button.dataset.idleText) {
    button.dataset.idleText = button.textContent;
  }
  button.disabled = busy;
  button.textContent = busy ? busyText : button.dataset.idleText;
}

function setConnected(connected) {
  state.connected = connected;
  els.liveDot.classList.toggle("offline", !connected);
  els.liveLabel.textContent = connected ? "Live" : "Offline";
  els.connectionToggle.textContent = connected ? "Connection ok" : "Connection";
  els.coordDot.classList.toggle("offline", !connected);
  if (!connected) {
    els.coordState.textContent = "Offline";
    els.topbarStatus.textContent = "Offline";
    els.topbarStatus.classList.add("muted-pill");
  }
}

function isAuthError(error) {
  return error && (error.status === 401 || error.status === 403);
}

function apiUrl(path) {
  if (window.location.protocol === "file:") {
    const error = new Error("This page is open as a local file. Start the bridge, then open the Workbench UI URL it prints, such as http://127.0.0.1:8765/workbench.");
    error.status = 0;
    throw error;
  }
  const base = (state.bridgeUrl || "").trim().replace(/\/+$/, "");
  if (base) {
    return `${base}${path}`;
  }
  return path;
}

function friendlyFetchError(error) {
  if (error && error.context === "pair") {
    return "Pairing code was invalid, expired, or already used. Generate a fresh code on the desktop bridge, paste it here, then Pair again.";
  }
  if (error && error.status === 0) {
    return error.message;
  }
  if (error && /pair with/i.test(error.message || "")) {
    return "No session token is saved. Enter a fresh pairing code from the desktop bridge, or paste a saved session token.";
  }
  if (isAuthError(error)) {
    return "Saved session token was rejected or expired. Click Forget token, then pair with a fresh desktop code.";
  }
  if (error instanceof TypeError && /fetch/i.test(error.message || "")) {
    const target = (els.bridgeUrl.value || state.bridgeUrl || window.location.origin || "the bridge").trim();
    return `Could not reach the bridge at ${target}. Confirm remote_control.py is running, Tailscale is connected if needed, and use the bridge URL shown in its console.`;
  }
  return error && error.message ? error.message : String(error);
}

function connectionRecoveryFor(error) {
  if (error && error.context === "pair") {
    return {
      title: "Pairing code recovery",
      steps: [
        "Generate a fresh code on the desktop bridge.",
        "Paste it before the five-minute timer expires.",
        "If a token is already saved, click Forget token before pairing again.",
      ],
    };
  }
  if (error instanceof TypeError && /fetch/i.test(error.message || "")) {
    return {
      title: "Bridge reachability",
      steps: [
        "Confirm the desktop bridge is running.",
        "Use the exact Workbench or bridge URL printed by the bridge.",
        "If you are off-device, confirm Tailscale is connected and the bridge URL is reachable.",
      ],
    };
  }
  if (error && /pair with|session token/i.test(error.message || "")) {
    return {
      title: "Connect with a token",
      steps: [
        "Paste a fresh one-time pairing code from the desktop bridge.",
        "Click Pair; the session token will be filled automatically.",
      ],
    };
  }
  if (isAuthError(error)) {
    return {
      title: "Token recovery",
      steps: [
        "Click Forget token to clear the stale browser token.",
        "Generate a fresh pairing code on the desktop bridge.",
        "Paste the code and click Pair.",
      ],
    };
  }
  return {
    title: "Connection recovery",
    steps: [
      "Open the connection panel and verify the bridge URL.",
      "If the bridge was restarted, pair again with a fresh code.",
    ],
  };
}

async function apiFetch(path, options = {}) {
  if (!state.token) {
    const error = new Error("Pair with the desktop bridge first.");
    error.status = 401;
    throw error;
  }
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      Authorization: `Bearer ${state.token}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

async function pairDevice() {
  state.bridgeUrl = els.bridgeUrl.value.trim();
  saveSettings();
  const code = els.pairCode.value.trim().toUpperCase();
  if (!code) {
    const error = new Error("Enter the one-time pairing code from the desktop bridge console.");
    error.context = "pair";
    throw error;
  }
  setConnectionState("Pairing with desktop bridge...", "warning");
  const response = await fetch(apiUrl("/api/pair"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pair_code: code }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error || `Pairing failed (${response.status})`);
    error.status = response.status;
    error.context = "pair";
    throw error;
  }
  state.token = body.session_token || "";
  els.token.value = state.token;
  els.pairCode.value = "";
  state.connectionFailures = 0;
  state.authBlocked = false;
  setConnectionState("Paired. Connecting to session...", "success");
  saveSettings();
}

async function connect() {
  state.bridgeUrl = els.bridgeUrl.value.trim();
  state.token = els.token.value.trim() || state.token;
  state.connectionFailures = 0;
  state.authBlocked = false;
  setConnectionState("Connecting to bridge...", "warning");
  if (!state.token && els.pairCode.value.trim()) {
    await pairDevice();
  }
  saveSettings();
  resetSessionState();
  const connected = await refreshSession();
  if (connected) {
    await refreshWorkbench();
    setConnectionPanel(false);
    startPolling();
  }
  return connected;
}

function resetSessionState() {
  state.eventCursor = 0;
  state.streams = {};
  state.coordItems = [];
  state.lanes = {};
  els.agentLanes.innerHTML = "";
}

/* ---------- polling ---------- */

function startPolling() {
  stopPolling();
  scheduleSessionPoll();
  state.workbenchTimer = window.setInterval(() => {
    refreshWorkbench().catch(() => {});
  }, WORKBENCH_POLL_MS);
}

function stopPolling() {
  if (state.sessionTimer) {
    window.clearTimeout(state.sessionTimer);
    state.sessionTimer = null;
  }
  if (state.workbenchTimer) {
    window.clearInterval(state.workbenchTimer);
    state.workbenchTimer = null;
  }
}

function scheduleSessionPoll() {
  if (state.sessionTimer) {
    window.clearTimeout(state.sessionTimer);
    state.sessionTimer = null;
  }
  if (state.authBlocked) {
    return;
  }
  const delay = state.commandRunning ? SESSION_POLL_BUSY_MS : SESSION_POLL_MS;
  state.sessionTimer = window.setTimeout(async () => {
    state.sessionTimer = null;
    try {
      await refreshSession();
    } catch {
      /* refreshSession reports its own errors */
    }
    if (!state.authBlocked && (state.connected || state.token)) {
      scheduleSessionPoll();
    }
  }, delay);
}

async function refreshSession() {
  try {
    const data = await apiFetch(`/api/session?cursor=${state.eventCursor}`);
    applySession(data);
    state.connectionFailures = 0;
    state.authBlocked = false;
    setConnected(true);
    setConnectionState("Connected to bridge.", "success");
    setConnectionRecovery();
    showError("");
    return true;
  } catch (error) {
    state.connectionFailures += 1;
    setConnected(false);
    const detail = friendlyFetchError(error);
    const recovery = connectionRecoveryFor(error);
    setConnectionRecovery(recovery.title, recovery.steps);
    showError(detail);
    if (isAuthError(error)) {
      state.authBlocked = true;
      stopPolling();
      setConnectionPanel(true);
      setConnectionState("Session token rejected. Pair again with a fresh code.", "error");
      return false;
    }
    setConnectionState(`Bridge unreachable. Retrying (${state.connectionFailures})...`, "warning");
    return false;
  }
}

async function refreshWorkbench() {
  const data = await apiFetch("/api/workbench");
  renderEnvironment(data.environment);
  renderGraph(data.graph);
  renderMonitor(data.monitor);
  els.envProject.textContent = data.project || "-";
}

/* ---------- message helpers ---------- */

function splitSignals(text) {
  const lines = (text || "").split("\n");
  const signals = [];
  while (lines.length && /^\s*>>>\s*\S/.test(lines[lines.length - 1])) {
    signals.unshift(lines.pop().trim().replace(/^>>>\s*/, ""));
  }
  return { body: lines.join("\n").trim(), signals };
}

function signalCard(signal, timestamp) {
  const card = document.createElement("section");
  const upper = signal.toUpperCase();
  card.className = upper.startsWith("TASK_COMPLETE") ? "complete-card" : "handoff-card";
  const arrow = document.createElement("span");
  arrow.textContent = upper.startsWith("TASK_COMPLETE") ? "FLAG" : "->";
  const label = document.createElement("strong");
  label.textContent = `>>> ${signal}`;
  card.appendChild(arrow);
  card.appendChild(label);
  if (timestamp) {
    const time = document.createElement("time");
    time.textContent = timestamp;
    card.appendChild(time);
  }
  return card;
}

function messageCard(text, { streaming = false, timestamp = "" } = {}) {
  const fragment = document.createDocumentFragment();
  const { body, signals } = splitSignals(text);
  if (body || streaming) {
    const card = document.createElement("section");
    card.className = streaming ? "message-card streaming" : "message-card";
    const paragraph = document.createElement("p");
    paragraph.className = "msg-text";
    paragraph.textContent = body;
    card.appendChild(paragraph);
    fragment.appendChild(card);
  }
  for (const signal of signals) {
    fragment.appendChild(signalCard(signal, timestamp));
  }
  return fragment;
}

/* ---------- agent lanes ---------- */

function agentDisplayName(agent) {
  const canonical = canonicalAgent(agent);
  if (AGENT_LABELS[canonical]) {
    return AGENT_LABELS[canonical];
  }
  return canonical.split(/[_-]/).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function agentGlyph(agent) {
  const canonical = canonicalAgent(agent);
  if (AGENT_GLYPHS[canonical]) {
    return AGENT_GLYPHS[canonical];
  }
  const parts = canonical.split(/[_-]/);
  if (parts.length > 1) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return canonical.slice(0, 2).toUpperCase();
}

function laneDisplayName(agent) {
  const canonical = canonicalAgent(agent);
  return LANE_LABELS[canonical] || agentDisplayName(canonical);
}

function laneGlyph(agent) {
  const canonical = canonicalAgent(agent);
  return LANE_GLYPHS[canonical] || agentGlyph(canonical);
}

function laneEmptyText(agent) {
  if (canonicalAgent(agent) === "coordinator") {
    return "Gemma is ready. Direct @coordinator replies appear here.";
  }
  return "No messages this session yet.";
}

function laneStyleClass(agent) {
  const canonical = canonicalAgent(agent);
  return KNOWN_AGENT_STYLES.has(canonical) ? canonical : "generic";
}

function canonicalAgent(agent) {
  const normalized = String(agent || "")
    .trim()
    .toLowerCase()
    .replace(/[-\s]+/g, "_");
  if (normalized === "agent_zero" || normalized === "agentzero" || normalized === "az") {
    return "coordinator";
  }
  return normalized;
}

function uniqueAgents(agents) {
  const seen = new Set();
  const unique = [];
  for (const agent of agents || []) {
    const canonical = canonicalAgent(agent);
    if (!canonical || seen.has(canonical)) {
      continue;
    }
    seen.add(canonical);
    unique.push(canonical);
  }
  return unique;
}

function agentStatusValue(agent, statuses = {}) {
  const canonical = canonicalAgent(agent);
  const record = statuses[canonical] || statuses[agent] || {};
  if (typeof record === "string") {
    return record.toLowerCase();
  }
  return String(record.status || "available").toLowerCase();
}

function agentIsLive(agent, statuses = {}) {
  return ["available", "low"].includes(agentStatusValue(agent, statuses));
}

function deriveLaneAgents(data) {
  const statuses = data.agent_statuses || {};
  const serverLanes = uniqueAgents(data.lane_agents || []).filter((agent) => agentIsLive(agent, statuses));
  if (serverLanes.length) {
    return serverLanes.slice(0, LANE_AGENT_LIMIT);
  }
  const mainAgents = uniqueAgents(data.agents || DEFAULT_AGENTS);
  const directAgents = uniqueAgents(data.direct_agents || []);
  const activeAgents = data.command_running || !["idle", "blocked", "awaiting_approval"].includes(data.status)
    ? uniqueAgents([
      data.next_agent,
      data.last_agent,
      ...(data.expected_agents || []),
    ])
    : [];
  const lanes = [];
  for (const agent of mainAgents) {
    if (agentIsLive(agent, statuses)) {
      lanes.push(agent);
    }
  }
  for (const agent of [...activeAgents, ...directAgents]) {
    if (lanes.length >= LANE_AGENT_LIMIT) {
      break;
    }
    if (!lanes.includes(agent) && agentIsLive(agent, statuses)) {
      lanes.push(agent);
    }
  }
  return (lanes.length ? lanes : mainAgents).slice(0, LANE_AGENT_LIMIT);
}

function ensureLanes(agents) {
  const roster = uniqueAgents(agents.length ? agents : Object.keys(state.lanes));
  if (JSON.stringify(roster) === JSON.stringify(Object.keys(state.lanes))) {
    return;
  }
  els.agentLanes.innerHTML = "";
  state.lanes = {};
  for (const agent of roster) {
    const pane = document.createElement("article");
    pane.className = `agent-pane ${laneStyleClass(agent)}-pane`;

    const header = document.createElement("header");
    header.className = "agent-header";
    const logo = document.createElement("div");
    logo.className = `agent-logo ${laneStyleClass(agent)}-logo`;
    logo.textContent = laneGlyph(agent);
    const title = document.createElement("div");
    const name = document.createElement("h2");
    name.textContent = laneDisplayName(agent);
    const status = document.createElement("p");
    const dot = document.createElement("span");
    dot.className = "live-dot";
    const statusLabel = document.createElement("span");
    statusLabel.textContent = " Offline";
    status.appendChild(dot);
    status.appendChild(statusLabel);
    title.appendChild(name);
    title.appendChild(status);
    header.appendChild(logo);
    header.appendChild(title);
    const menu = document.createElement("button");
    menu.className = "icon-button menu-button";
    menu.type = "button";
    menu.setAttribute("aria-label", `${laneDisplayName(agent)} options`);
    menu.title = `${laneDisplayName(agent)} options`;
    menu.textContent = "...";
    header.appendChild(menu);

    const stream = document.createElement("div");
    stream.className = "agent-stream";

    pane.appendChild(header);
    pane.appendChild(stream);
    els.agentLanes.appendChild(pane);
    state.lanes[agent] = { pane, stream, statusDot: dot, statusLabel };
  }
}

function renderLanes(transcript) {
  for (const [agent, lane] of Object.entries(state.lanes)) {
    const nearBottom = lane.stream.scrollHeight - lane.stream.scrollTop - lane.stream.clientHeight < 60;
    lane.stream.innerHTML = "";
    const messages = transcript.filter((item) => canonicalAgent(item.sender) === agent);
    const recent = messages.slice(-LANE_MESSAGE_LIMIT);
    if (!recent.length && !state.streams[agent]) {
      const empty = document.createElement("p");
      empty.className = "lane-empty";
      empty.textContent = laneEmptyText(agent);
      lane.stream.appendChild(empty);
      continue;
    }
    for (const message of recent) {
      lane.stream.appendChild(messageCard(message.text));
    }
    const active = state.streams[agent];
    if (active) {
      const meta = document.createElement("div");
      meta.className = "event-meta";
      const time = document.createElement("time");
      time.textContent = active.timestamp || "";
      const label = document.createElement("span");
      label.textContent = "streaming";
      meta.appendChild(time);
      meta.appendChild(label);
      lane.stream.appendChild(meta);
      lane.stream.appendChild(messageCard(active.text, { streaming: true, timestamp: active.timestamp }));
    }
    if (nearBottom) {
      lane.stream.scrollTop = lane.stream.scrollHeight;
    }
  }
}

function updateLaneActivity(data) {
  for (const [agent, lane] of Object.entries(state.lanes)) {
    const busy = Boolean(state.streams[agent]) || (data.command_running && canonicalAgent(data.next_agent) === agent);
    lane.statusDot.classList.toggle("offline", !state.connected);
    lane.statusDot.classList.toggle("busy", busy);
    lane.statusLabel.textContent = state.connected ? (busy ? " Working" : " Online") : " Offline";
  }
}

/* ---------- events ---------- */

function ingestEvents(events) {
  for (const event of events) {
    const kind = event.kind || "";
    const sender = canonicalAgent(event.sender);
    if (kind === "message_stream_start") {
      state.streams[sender] = { text: "", timestamp: event.timestamp || "" };
      continue;
    }
    if (kind === "message_delta") {
      if (!state.streams[sender]) {
        state.streams[sender] = { text: "", timestamp: event.timestamp || "" };
      }
      state.streams[sender].text += event.text || "";
      continue;
    }
    if (kind === "message_stream_finish") {
      delete state.streams[sender];
      continue;
    }
    if (kind === "activity") {
      state.lastActivity = `${agentDisplayName(sender)} ${event.text || ""}`;
      continue;
    }
    if (kind === "usage" || kind === "banner") {
      continue;
    }
    if (sender === "system" || !state.lanes[sender]) {
      state.coordItems.push(event);
    }
  }
  const cap = COORD_FEED_EXPANDED_LIMIT * 2;
  if (state.coordItems.length > cap) {
    state.coordItems.splice(0, state.coordItems.length - cap);
  }
}

function renderCoordinator(data) {
  const limit = state.coordExpanded ? COORD_FEED_EXPANDED_LIMIT : COORD_FEED_LIMIT;
  const visibleItems = state.showSystemFeed
    ? state.coordItems
    : state.coordItems.filter((item) => canonicalAgent(item.sender) !== "system");
  const items = visibleItems.slice(-limit);
  els.coordFeed.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "lane-empty";
    empty.textContent = state.showSystemFeed
      ? "No system events yet."
      : "No coordinator responses yet. Click System to show setup and routing events.";
    els.coordFeed.appendChild(empty);
  }
  for (const item of items) {
    const root = document.createElement("div");
    root.className = "coord-item";
    const meta = document.createElement("div");
    meta.className = "coord-meta";
    meta.textContent = `${agentDisplayName(item.sender || "system")} ${item.timestamp || ""} ${item.kind || ""}`.trim();
    const text = document.createElement("div");
    text.className = "msg-text";
    text.textContent = item.text || "";
    root.appendChild(meta);
    root.appendChild(text);
    els.coordFeed.appendChild(root);
  }
  els.coordFeed.scrollTop = els.coordFeed.scrollHeight;
  const latest = items[items.length - 1];
  els.coordTime.textContent = latest ? latest.timestamp || "" : "";
  els.systemFeedButton.classList.toggle("is-active", state.showSystemFeed);
  els.systemFeedButton.setAttribute("aria-pressed", state.showSystemFeed ? "true" : "false");
  els.systemFeedButton.textContent = state.showSystemFeed ? "Hide System" : "System";
  els.coordState.textContent = data.command_running
    ? `Running: ${(data.command_text || "").slice(0, 60) || "command"}`
    : "Idle";
}

function formatExecutionEstimate(estimate) {
  if (!estimate || typeof estimate !== "object") {
    return "Execution estimate unavailable.";
  }
  const parts = [];
  if (estimate.agent) {
    parts.push(`via ${agentDisplayName(String(estimate.agent))}`);
  }
  if (estimate.total_tokens !== undefined) {
    parts.push(`${Number(estimate.total_tokens).toLocaleString()} tokens`);
  } else if (estimate.input_tokens !== undefined || estimate.output_tokens !== undefined) {
    const input = Number(estimate.input_tokens || 0).toLocaleString();
    const output = Number(estimate.output_tokens || 0).toLocaleString();
    parts.push(`${input} in / ${output} out`);
  }
  if (estimate.total_usd !== undefined && estimate.total_usd !== null) {
    parts.push(`$${Number(estimate.total_usd).toFixed(4)}`);
  } else if (estimate.cost_configured === false) {
    parts.push("cost unavailable");
  }
  return parts.length ? parts.join(" · ") : "Execution estimate unavailable.";
}

function setApprovalStatus(message, tone = "muted") {
  els.approvalStatus.textContent = message || "";
  els.approvalStatus.classList.toggle("success", tone === "success");
  els.approvalStatus.classList.toggle("warning", tone === "warning");
  els.approvalStatus.classList.toggle("error-state", tone === "error");
}

function setApprovalControls(disabled) {
  state.approvalSubmitting = disabled;
  els.approveButton.disabled = disabled;
  els.rejectButton.disabled = disabled;
  els.dismissButton.disabled = disabled;
  els.approvalModification.disabled = disabled;
  updateApprovalActionState();
}

function approvalCommandFor(action) {
  const note = els.approvalModification.value.trim();
  if (action === "MODIFY") {
    return note ? `MODIFY ${note}` : "MODIFY <note required>";
  }
  if (action === "DISMISS") {
    return "/dismiss";
  }
  return action;
}

function updateApprovalActionState(action = "APPROVE") {
  const note = els.approvalModification.value.trim();
  els.modifyButton.disabled = state.approvalSubmitting || !note;
  els.approvalCommandPreview.textContent = `Sends: ${approvalCommandFor(action)}`;
}

function proposalRawText(proposal) {
  const raw = String(proposal.raw || "").trim();
  if (!raw) {
    return "No detailed proposal text was included in the session snapshot.";
  }
  return proposal.raw_truncated ? `${raw}\n\n[truncated]` : raw;
}

function renderApproval(data) {
  const proposal = data.proposal || null;
  const awaitingApproval = data.status === "awaiting_approval" && proposal;
  els.approvalPanel.classList.toggle("hidden", !awaitingApproval);
  if (!awaitingApproval) {
    state.approvalActive = false;
    state.approvalProposalId = "";
    setApprovalControls(false);
    setApprovalStatus("");
    els.approvalCommandPreview.textContent = "";
    els.approvalHelper.textContent = "";
    return;
  }
  const proposalId = String(proposal.id || `${proposal.proposed_by || "agent"}:${proposal.summary || ""}`);
  if (state.approvalProposalId !== proposalId) {
    els.approvalModification.value = "";
    setApprovalStatus("Choose an approval action.");
  }
  state.approvalActive = true;
  state.approvalProposalId = proposalId;
  const proposer = proposal.proposed_by ? agentDisplayName(proposal.proposed_by) : "Agent";
  els.approvalMeta.textContent = `${proposer} proposal`;
  els.approvalSummary.textContent = proposal.summary || "Review proposal";
  els.approvalEstimate.textContent = formatExecutionEstimate(proposal.execution_estimate);
  els.approvalHelper.textContent = `Responding to ${
    proposal.id ? `proposal ${proposal.id}` : "the active proposal"
  }. Modify requires a note; Dismiss closes the gate without execution.`;
  els.approvalRaw.textContent = proposalRawText(proposal);
  setApprovalControls(false);
}

/* ---------- left rail ---------- */

function renderProjects(projects, currentProject) {
  state.currentProject = currentProject;
  els.projectList.innerHTML = "";
  for (const project of projects) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = project === currentProject ? "rail-item active" : "rail-item";
    const icon = document.createElement("span");
    icon.className = "folder-icon";
    const label = document.createElement("span");
    label.textContent = project;
    item.appendChild(icon);
    item.appendChild(label);
    if (project !== currentProject) {
      item.addEventListener("click", () => switchProject(project));
    }
    els.projectList.appendChild(item);
  }
}

function renderSession(data) {
  els.sessionList.innerHTML = "";
  const sessions = data.session_history || [{ name: data.session || "current", age: data.context_mode || "" }];
  for (const session of sessions) {
    const item = document.createElement("div");
    item.className = session.name === data.session ? "rail-item active" : "rail-item";
    const icon = document.createElement("span");
    icon.className = "folder-icon";
    const label = document.createElement("span");
    label.textContent = session.name || "current";
    const mode = document.createElement("time");
    mode.textContent = session.age || "";
    item.appendChild(icon);
    item.appendChild(label);
    item.appendChild(mode);
    els.sessionList.appendChild(item);
  }
}

function formatTokens(value) {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}m`;
  }
  if (value >= 1_000) {
    return `${Math.round(value / 1_000)}k`;
  }
  return String(value);
}

function tokenRow(name, glyph, used, limit, warning, percent, styleClass) {
  const row = document.createElement("div");
  row.className = `token-row ${styleClass}`;
  const glyphEl = document.createElement("span");
  glyphEl.className = "agent-glyph";
  glyphEl.textContent = glyph;
  const label = document.createElement("span");
  label.textContent = name;
  const value = document.createElement("span");
  value.textContent = percent === null || percent === undefined
    ? formatTokens(used)
    : `${Math.round(percent)}%`;
  const meter = document.createElement("div");
  meter.className = "meter";
  if (limit > 0 && used >= limit) {
    meter.classList.add("over");
  } else if (warning > 0 && used >= warning) {
    meter.classList.add("warn");
  }
  const fill = document.createElement("span");
  fill.style.width = `${Math.max(0, Math.min(100, percent || 0))}%`;
  meter.appendChild(fill);
  row.appendChild(glyphEl);
  row.appendChild(label);
  row.appendChild(value);
  row.appendChild(meter);
  return row;
}

function renderTokenBalances(tokenUsage, sessionBudget) {
  els.tokenBalances.innerHTML = "";
  for (const usage of tokenUsage || []) {
    els.tokenBalances.appendChild(
      tokenRow(
        agentDisplayName(usage.agent),
        agentGlyph(usage.agent),
        usage.used,
        usage.limit,
        usage.warning,
        usage.percent,
        laneStyleClass(usage.agent),
      ),
    );
  }
  if (sessionBudget && sessionBudget.limit > 0) {
    const percent = (sessionBudget.used * 100) / sessionBudget.limit;
    els.tokenBalances.appendChild(
      tokenRow("Session", "SUM", sessionBudget.used, sessionBudget.limit, sessionBudget.warning, percent, "total"),
    );
  }
}

/* ---------- right rail ---------- */

function renderEnvironment(environment) {
  if (!environment) {
    els.envBranch.textContent = "-";
    els.envClean.textContent = "unknown";
    els.envCleanDot.classList.add("offline");
    els.envChanges.textContent = "-";
    els.envCommit.textContent = "-";
    return;
  }
  els.envBranch.textContent = environment.branch || "-";
  els.envClean.textContent = environment.clean ? "Clean" : "Dirty";
  els.envCleanDot.classList.toggle("offline", !environment.clean);
  els.envChanges.textContent = `${environment.staged} staged, ${environment.unstaged} unstaged`;
  els.envCommit.textContent = environment.last_commit
    ? `${environment.last_commit} (${environment.last_commit_age})`
    : "-";
}

function renderGraph(graph) {
  if (!graph) {
    els.graphHealth.textContent = "not found";
    els.graphDot.classList.add("offline");
    for (const el of [els.graphFiles, els.graphNodes, els.graphEdges, els.graphIndexed]) {
      el.textContent = "-";
    }
    return;
  }
  els.graphHealth.textContent = "Healthy";
  els.graphDot.classList.remove("offline");
  els.graphFiles.textContent = graph.files.toLocaleString();
  els.graphNodes.textContent = graph.nodes.toLocaleString();
  els.graphEdges.textContent = graph.edges.toLocaleString();
  els.graphIndexed.textContent = graph.last_indexed || "-";
}

function renderMonitor(monitor) {
  const cpu = monitor && monitor.cpu_percent !== undefined ? `${Math.round(monitor.cpu_percent)}%` : "-";
  const ram = monitor && monitor.ram_percent !== undefined ? `${Math.round(monitor.ram_percent)}%` : "-";
  els.monTailscale.textContent = (monitor && monitor.tailnet_ip) || "loopback";
  els.monCpu.textContent = cpu;
  els.monRam.textContent = ram;
  els.stripCpu.textContent = `CPU ${cpu}`;
  els.stripRam.textContent = `RAM ${ram}`;
}

function renderOfflineWorkbench() {
  applySession(previewSession);
  renderEnvironment({
    branch: "main",
    clean: true,
    staged: 0,
    unstaged: 0,
    last_commit: "a1b2c3d",
    last_commit_age: "2h ago",
  });
  renderGraph({
    healthy: true,
    files: 52,
    nodes: 1431,
    edges: 1507,
    last_indexed: "current",
  });
  renderMonitor({
    tailnet_ip: "100.94.205.69",
    cpu_percent: 8,
    ram_percent: 42,
  });
  els.envProject.textContent = "gear";
  els.topbarStatus.textContent = "Offline";
  els.topbarStatus.classList.add("muted-pill");
  els.coordState.textContent = "Offline";
  els.terminalCaption.textContent = "bridge idle - click to focus";
}

function renderProgress(data) {
  const expected = uniqueAgents(data.expected_agents || []);
  const completed = new Set(uniqueAgents(data.completed_agents || []));
  els.progressList.innerHTML = "";
  if (!expected.length) {
    const item = document.createElement("li");
    item.className = "pending";
    item.textContent = "No active round.";
    els.progressList.appendChild(item);
    els.progressCount.textContent = "idle";
    els.progressPercent.textContent = "-";
    return;
  }
  let done = 0;
  for (const agent of expected) {
    const item = document.createElement("li");
    const isDone = completed.has(canonicalAgent(agent));
    if (isDone) {
      done += 1;
    } else {
      item.className = "pending";
    }
    item.textContent = `${agentDisplayName(agent)} ${isDone ? "responded" : "pending"}`;
    els.progressList.appendChild(item);
  }
  els.progressCount.textContent = `${done} / ${expected.length} complete`;
  els.progressPercent.textContent = `${Math.round((done * 100) / expected.length)}%`;
}

function traceSignalLabel(item) {
  const signal = String(item.signal || "UNKNOWN").replace("_", " ");
  const target = item.target ? ` -> ${agentDisplayName(String(item.target))}` : "";
  return `${signal}${target}`;
}

function renderTraceList(container, items, emptyText, rowBuilder) {
  container.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "lane-empty";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  for (const item of items.slice(-6)) {
    const row = document.createElement("div");
    row.className = "trace-row";
    rowBuilder(row, item);
    container.appendChild(row);
  }
}

function appendTraceText(row, className, text) {
  const node = document.createElement("div");
  node.className = className;
  node.textContent = text || "-";
  row.appendChild(node);
}

function renderTrace(trace = {}) {
  const agents = trace.agent || [];
  const packets = trace.packets || [];
  els.traceAgentCount.textContent = String(agents.length);
  els.tracePacketCount.textContent = String(packets.length);
  renderTraceList(els.traceAgentList, agents, "No handoffs or terminal signals yet.", (row, item) => {
    appendTraceText(row, "trace-kicker", agentDisplayName(String(item.agent || "unknown")));
    appendTraceText(row, "trace-title", traceSignalLabel(item));
    appendTraceText(row, "trace-summary", item.summary || `message #${item.message_id ?? "-"}`);
  });
  renderTraceList(els.tracePacketList, packets, "No thought packets captured yet.", (row, item) => {
    appendTraceText(row, "trace-kicker", `${agentDisplayName(String(item.agent || "unknown"))} ${item.stance || ""}`.trim());
    appendTraceText(row, "trace-title", String(item.signal || "UNKNOWN").replace("_", " "));
    appendTraceText(
      row,
      "trace-summary",
      `${item.observed_count || 0} observed / ${item.risk_count || 0} risks${item.next_action ? ` - ${item.next_action}` : ""}`,
    );
  });
}

/* ---------- session apply ---------- */

function applySession(data) {
  els.topbarProject.textContent = data.project || "-";
  els.topbarSession.textContent = data.session || "-";
  const awaitingApproval = data.status === "awaiting_approval";
  const statusText = data.command_running ? "Working" : awaitingApproval ? "Approval needed" : data.status || "unknown";
  els.topbarStatus.textContent = statusText;
  els.topbarStatus.classList.toggle("muted-pill", Boolean(data.command_running) === false && !awaitingApproval && data.status !== "idle" && data.status !== "active");
  els.sessionButton.textContent = awaitingApproval ? "Approval" : data.command_running ? "Working" : "Session";

  state.commandRunning = Boolean(data.command_running);
  state.agents = deriveLaneAgents(data);
  state.directAgents = uniqueAgents(data.direct_agents || []);
  els.roleCallButton.classList.toggle("hidden", !state.directAgents.includes("coordinator"));

  ensureLanes(state.agents);
  renderProjects(data.projects || [], data.project || "");
  renderSession(data);
  renderTokenBalances(data.token_usage, data.session_budget);

  const events = (data.events || []).filter((event) => Number(event.id || 0) > state.eventCursor);
  if (events.length) {
    state.eventCursor = events[events.length - 1].id;
    ingestEvents(events);
  }

  renderLanes(data.transcript || []);
  updateLaneActivity(data);
  renderCoordinator(data);
  renderApproval(data);
  renderProgress(data);
  renderTrace(data.trace || {});

  els.statRound.textContent = data.round === null || data.round === undefined ? "-" : String(data.round);
  els.statMode.textContent = data.collaboration_mode || "-";
  els.statNext.textContent = data.next_agent ? agentDisplayName(data.next_agent) : "-";
  els.statStatus.textContent = statusText;
  els.statStatus.classList.toggle("muted-pill", statusText !== "idle" && !data.command_running && !awaitingApproval);

  els.terminalCaption.textContent = awaitingApproval
    ? "approval needed"
    : state.lastActivity || (state.commandRunning ? "agents working..." : "bridge idle - click to focus");

  if (state.commandRunning) {
    setSendState(true, "Agents working...");
  } else if (awaitingApproval) {
    setSendState(false, "Proposal awaiting approval.");
  } else if (els.sendButton.disabled) {
    setSendState(false, "Latest response shown.");
  }
}

/* ---------- composer ---------- */

function setSendState(sending, message) {
  els.sendButton.disabled = sending;
  els.sendButton.textContent = sending ? "Working" : "Send";
  if (message !== undefined) {
    els.sendStatus.textContent = message;
  }
}

async function sendPrompt(text) {
  const cleaned = text.trim();
  if (!cleaned || els.sendButton.disabled) {
    return false;
  }
  setSendState(true, "Sending to ChatBoks...");
  try {
    const data = await apiFetch("/api/command", {
      method: "POST",
      body: JSON.stringify({ text: cleaned }),
    });
    els.workbenchPrompt.value = "";
    applySession(data);
    scheduleSessionPoll();
    return true;
  } catch (error) {
    const detail = friendlyFetchError(error);
    setSendState(false, `Send failed: ${detail}`);
    setConnectionState(detail, isAuthError(error) ? "error" : "warning");
    if (isAuthError(error)) {
      setConnectionPanel(true);
    }
    return false;
  }
}

async function submitApproval(action) {
  if (!state.approvalActive) {
    setApprovalStatus("No active proposal is waiting for approval.", "error");
    return;
  }
  const note = els.approvalModification.value.trim();
  if (action === "MODIFY" && !note) {
    setApprovalStatus("Add a modification note before sending MODIFY.", "warning");
    els.approvalModification.focus();
    return;
  }
  const command = approvalCommandFor(action);
  const label = action === "APPROVE"
    ? "Approval"
    : action === "REJECT"
      ? "Rejection"
      : action === "DISMISS"
        ? "Dismissal"
        : "Modification";
  setApprovalControls(true);
  setApprovalStatus(`${label} sent. Waiting for ChatBoks...`, "warning");
  const sent = await sendPrompt(command);
  if (sent) {
    setApprovalStatus(`${label} accepted by the bridge. Waiting for session update...`, "success");
  } else {
    setApprovalStatus(`${label} did not send. Check the connection message above.`, "error");
    setApprovalControls(false);
  }
}

async function switchProject(project) {
  if (state.commandRunning) {
    showError("Cannot switch projects while a command is running.");
    return;
  }
  setSendState(true, `Switching to ${project}...`);
  try {
    resetSessionState();
    const data = await apiFetch("/api/project", {
      method: "POST",
      body: JSON.stringify({ project }),
    });
    applySession(data);
    await refreshWorkbench();
    setSendState(false, `Project switched to ${project}.`);
    showError("");
  } catch (error) {
    const detail = friendlyFetchError(error);
    setSendState(false, "Project switch failed.");
    setConnectionState(detail, isAuthError(error) ? "error" : "warning");
    showError(detail);
  }
}

/* ---------- event wiring ---------- */

els.themeToggle.addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));
els.themeToggleRail.addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));

els.connectionToggle.addEventListener("click", () => {
  setConnectionPanel(els.connectionPanel.classList.contains("hidden"));
});
els.settingsButton.addEventListener("click", () => setConnectionPanel(true));

els.pairButton.addEventListener("click", async () => {
  setConnectionBusy(els.pairButton, true, "Pairing...");
  setConnectionBusy(els.connectButton, true, "Connect");
  try {
    await pairDevice();
    if (await connect()) {
      setConnectionRecovery();
      showError("Paired and connected. Session token saved in this browser.", "success");
      setSendState(false, "Paired and connected.");
    }
  } catch (error) {
    const detail = friendlyFetchError(error);
    const recovery = connectionRecoveryFor(error);
    setConnectionRecovery(recovery.title, recovery.steps);
    setConnectionState(detail, "error");
    showError(detail);
  } finally {
    setConnectionBusy(els.pairButton, false, "Pairing...");
    setConnectionBusy(els.connectButton, false, "Connect");
  }
});

els.connectButton.addEventListener("click", async () => {
  setConnectionBusy(els.connectButton, true, "Connecting...");
  setConnectionBusy(els.pairButton, true, "Pair");
  try {
    if (await connect()) {
      setConnectionRecovery();
      showError("Connected to the bridge.", "success");
      setSendState(false, "Connected to bridge.");
    }
  } catch (error) {
    const detail = friendlyFetchError(error);
    const recovery = connectionRecoveryFor(error);
    setConnectionRecovery(recovery.title, recovery.steps);
    setConnectionState(detail, "error");
    showError(detail);
  } finally {
    setConnectionBusy(els.connectButton, false, "Connecting...");
    setConnectionBusy(els.pairButton, false, "Pair");
  }
});

els.forgetButton.addEventListener("click", () => {
  state.token = "";
  els.token.value = "";
  els.pairCode.value = "";
  saveSettings();
  stopPolling();
  setConnected(false);
  resetSessionState();
  renderOfflineWorkbench();
  setConnectionPanel(true);
  state.connectionFailures = 0;
  state.authBlocked = false;
  setConnectionRecovery();
  setConnectionState("No session token saved. Pair with a fresh desktop code.", "muted");
  setSendState(false, "Session token forgotten.");
  showError("Session token forgotten. Pair again with a fresh desktop code before reconnecting.", "success");
});

els.sendButton.addEventListener("click", () => sendPrompt(els.workbenchPrompt.value));
for (const textField of [els.workbenchPrompt, els.approvalModification]) {
  enforceLeftToRightText(textField);
  textField.addEventListener("focus", () => enforceLeftToRightText(textField));
  textField.addEventListener("click", () => enforceLeftToRightText(textField));
  textField.addEventListener("input", () => enforceLeftToRightText(textField));
  textField.addEventListener("compositionend", () => enforceLeftToRightText(textField));
}
els.approvalModification.addEventListener("input", () => updateApprovalActionState("MODIFY"));
els.workbenchPrompt.addEventListener("keydown", (event) => {
  enforceLeftToRightText(els.workbenchPrompt);
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendPrompt(els.workbenchPrompt.value);
  }
});

els.newTaskButton.addEventListener("click", () => {
  els.workbenchPrompt.focus();
  els.workbenchPrompt.select();
});

els.terminalFocus.addEventListener("click", () => {
  els.terminalFocus.classList.add("is-focused");
  els.workbenchPrompt.focus();
});

els.roleCallButton.addEventListener("click", () => sendPrompt("@coordinator role call"));
els.approveButton.addEventListener("focus", () => updateApprovalActionState("APPROVE"));
els.modifyButton.addEventListener("focus", () => updateApprovalActionState("MODIFY"));
els.rejectButton.addEventListener("focus", () => updateApprovalActionState("REJECT"));
els.dismissButton.addEventListener("focus", () => updateApprovalActionState("DISMISS"));
els.approveButton.addEventListener("click", () => submitApproval("APPROVE"));
els.rejectButton.addEventListener("click", () => submitApproval("REJECT"));
els.modifyButton.addEventListener("click", () => submitApproval("MODIFY"));
els.dismissButton.addEventListener("click", () => submitApproval("DISMISS"));
els.systemFeedButton.addEventListener("click", () => {
  state.showSystemFeed = !state.showSystemFeed;
  renderCoordinator({ command_running: state.commandRunning, command_text: "" });
});
els.logsButton.addEventListener("click", () => {
  state.coordExpanded = !state.coordExpanded;
  els.logsButton.textContent = state.coordExpanded ? "Less" : "Logs";
  renderCoordinator({ command_running: state.commandRunning, command_text: "" });
});

els.liveButton.addEventListener("click", () => {
  refreshSession().catch(() => {});
  refreshWorkbench().catch(() => {});
});

/* ---------- boot ---------- */

document.documentElement.dir = "ltr";
loadSettings();
setTheme(state.theme);
if (state.token) {
  setConnectionState("Saved session token found. Verifying bridge connection...", "muted");
  connect().catch(() => setConnectionPanel(true));
} else {
  renderOfflineWorkbench();
  setConnectionPanel(false);
  setConnectionState("No session token saved. Pair with a fresh desktop code.", "muted");
}
