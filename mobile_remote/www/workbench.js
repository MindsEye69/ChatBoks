const STORAGE_KEY = "chatboks-workbench";
const SESSION_POLL_MS = 2500;
const SESSION_POLL_BUSY_MS = 1500;
const WORKBENCH_POLL_MS = 10000;
const LANE_MESSAGE_LIMIT = 10;
const COORD_FEED_LIMIT = 6;
const COORD_FEED_EXPANDED_LIMIT = 40;
const DEFAULT_AGENTS = ["claude", "codex", "gemini"];

const KNOWN_AGENT_STYLES = new Set(["claude", "codex", "gemini", "antigravity", "codex_spark", "agent_zero"]);

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
  currentProject: "",
  lastActivity: "",
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
  direct_agents: ["agent_zero"],
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
};

const els = {};
for (const id of [
  "themeToggle", "themeToggleRail", "newTaskButton", "projectList", "sessionList",
  "tokenBalances", "settingsButton", "stripCpu", "stripRam",
  "topbarProject", "topbarSession", "topbarStatus", "liveButton", "liveDot", "liveLabel",
  "sessionButton", "connectionToggle", "connectionPanel", "pairCode", "token", "pairButton",
  "bridgeUrl", "connectButton", "forgetButton", "errorBox",
  "agentLanes", "coordDot", "coordState", "roleCallButton", "logsButton",
  "approvalPanel", "approvalMeta", "approvalSummary", "approvalEstimate",
  "approvalModification", "approveButton", "modifyButton", "rejectButton",
  "coordTime", "coordFeed", "statRound", "statMode", "statNext", "statStatus",
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

/* ---------- connection ---------- */

function showError(message, tone = "error") {
  els.errorBox.textContent = message || "";
  els.errorBox.classList.toggle("hidden", !message);
  els.errorBox.classList.toggle("success", Boolean(message) && tone === "success");
  if (message) {
    els.connectionPanel.classList.remove("hidden");
  }
}

function setConnectionPanel(visible) {
  els.connectionPanel.classList.toggle("hidden", !visible);
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
  if (error && error.status === 0) {
    return error.message;
  }
  if (error instanceof TypeError && /fetch/i.test(error.message || "")) {
    const target = (els.bridgeUrl.value || state.bridgeUrl || window.location.origin || "the bridge").trim();
    return `Could not reach the bridge at ${target}. Confirm remote_control.py is running and use the bridge URL shown in its console.`;
  }
  return error && error.message ? error.message : String(error);
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
    throw new Error("Enter the one-time pairing code from the desktop bridge console.");
  }
  const response = await fetch(apiUrl("/api/pair"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pair_code: code }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `Pairing failed (${response.status})`);
  }
  state.token = body.session_token || "";
  els.token.value = state.token;
  els.pairCode.value = "";
  saveSettings();
}

async function connect() {
  state.bridgeUrl = els.bridgeUrl.value.trim();
  state.token = els.token.value.trim() || state.token;
  if (!state.token && els.pairCode.value.trim()) {
    await pairDevice();
  }
  saveSettings();
  resetSessionState();
  await refreshSession();
  await refreshWorkbench();
  setConnectionPanel(false);
  startPolling();
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
  }
  const delay = state.commandRunning ? SESSION_POLL_BUSY_MS : SESSION_POLL_MS;
  state.sessionTimer = window.setTimeout(async () => {
    state.sessionTimer = null;
    try {
      await refreshSession();
    } catch {
      /* refreshSession reports its own errors */
    }
    if (state.connected || state.token) {
      scheduleSessionPoll();
    }
  }, delay);
}

async function refreshSession() {
  try {
    const data = await apiFetch(`/api/session?cursor=${state.eventCursor}`);
    applySession(data);
    setConnected(true);
    showError("");
  } catch (error) {
    setConnected(false);
    showError(friendlyFetchError(error));
    if (isAuthError(error)) {
      setConnectionPanel(true);
    }
    throw error;
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
  return agent.split(/[_-]/).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function agentGlyph(agent) {
  const parts = agent.split(/[_-]/);
  if (parts.length > 1) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return agent.slice(0, 2).toUpperCase();
}

function laneStyleClass(agent) {
  return KNOWN_AGENT_STYLES.has(agent) ? agent : "generic";
}

function ensureLanes(agents) {
  const roster = agents.length ? agents : Object.keys(state.lanes);
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
    logo.textContent = agentGlyph(agent);
    const title = document.createElement("div");
    const name = document.createElement("h2");
    name.textContent = agentDisplayName(agent);
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
    menu.setAttribute("aria-label", `${agentDisplayName(agent)} options`);
    menu.title = `${agentDisplayName(agent)} options`;
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
    const messages = transcript.filter((item) => (item.sender || "").toLowerCase() === agent);
    const recent = messages.slice(-LANE_MESSAGE_LIMIT);
    if (!recent.length && !state.streams[agent]) {
      const empty = document.createElement("p");
      empty.className = "lane-empty";
      empty.textContent = "No messages this session yet.";
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
    const busy = Boolean(state.streams[agent]) || (data.command_running && (data.next_agent || "").toLowerCase() === agent);
    lane.statusDot.classList.toggle("offline", !state.connected);
    lane.statusDot.classList.toggle("busy", busy);
    lane.statusLabel.textContent = state.connected ? (busy ? " Working" : " Online") : " Offline";
  }
}

/* ---------- events ---------- */

function ingestEvents(events) {
  for (const event of events) {
    const kind = event.kind || "";
    const sender = (event.sender || "").toLowerCase();
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
      state.lastActivity = `${sender.toUpperCase()} ${event.text || ""}`;
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
  const items = state.coordItems.slice(-limit);
  els.coordFeed.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "lane-empty";
    empty.textContent = "No system events yet.";
    els.coordFeed.appendChild(empty);
  }
  for (const item of items) {
    const root = document.createElement("div");
    root.className = "coord-item";
    const meta = document.createElement("div");
    meta.className = "coord-meta";
    meta.textContent = `${item.sender || "system"} ${item.timestamp || ""} ${item.kind || ""}`.trim();
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

function renderApproval(data) {
  const proposal = data.proposal || null;
  const awaitingApproval = data.status === "awaiting_approval" && proposal;
  els.approvalPanel.classList.toggle("hidden", !awaitingApproval);
  if (!awaitingApproval) {
    return;
  }
  const proposer = proposal.proposed_by ? agentDisplayName(proposal.proposed_by) : "Agent";
  els.approvalMeta.textContent = `${proposer} proposal`;
  els.approvalSummary.textContent = proposal.summary || "Review proposal";
  els.approvalEstimate.textContent = formatExecutionEstimate(proposal.execution_estimate);
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
  const expected = data.expected_agents || [];
  const completed = new Set(data.completed_agents || []);
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
    const isDone = completed.has(agent);
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
  state.agents = data.agents || [];
  state.directAgents = data.direct_agents || [];
  els.roleCallButton.classList.toggle("hidden", !state.directAgents.includes("agent_zero"));

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

  els.statRound.textContent = data.round === null || data.round === undefined ? "-" : String(data.round);
  els.statMode.textContent = data.collaboration_mode || "-";
  els.statNext.textContent = data.next_agent || "-";
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
    return;
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
  } catch (error) {
    setSendState(false, `Send failed: ${friendlyFetchError(error)}`);
    if (isAuthError(error)) {
      setConnectionPanel(true);
    }
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
    setSendState(false, "Project switch failed.");
    showError(friendlyFetchError(error));
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
  try {
    await pairDevice();
    await connect();
    showError("Paired and connected. Session token saved in this browser.", "success");
    setSendState(false, "Paired and connected.");
  } catch (error) {
    showError(friendlyFetchError(error));
  }
});

els.connectButton.addEventListener("click", async () => {
  try {
    await connect();
    showError("Connected to the bridge.", "success");
    setSendState(false, "Connected to bridge.");
  } catch (error) {
    showError(friendlyFetchError(error));
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
  setSendState(false, "Session token forgotten.");
  showError("Session token forgotten. Pair again with a fresh desktop code before reconnecting.", "success");
});

els.sendButton.addEventListener("click", () => sendPrompt(els.workbenchPrompt.value));
els.workbenchPrompt.addEventListener("keydown", (event) => {
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

els.roleCallButton.addEventListener("click", () => sendPrompt("@zero role call"));
els.approveButton.addEventListener("click", () => sendPrompt("APPROVE"));
els.rejectButton.addEventListener("click", () => sendPrompt("REJECT"));
els.modifyButton.addEventListener("click", () => {
  const note = els.approvalModification.value.trim();
  sendPrompt(note ? `MODIFY ${note}` : "MODIFY");
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

loadSettings();
setTheme(state.theme);
if (state.token) {
  connect().catch(() => setConnectionPanel(true));
} else {
  renderOfflineWorkbench();
  setConnectionPanel(false);
}
