const STORAGE_KEY = "chatboks-workbench";
const SESSION_POLL_MS = 1500;
const SESSION_POLL_BUSY_MS = 350;
const WORKBENCH_POLL_MS = 10000;
const TRANSCRIPT_POLL_LIMIT = 120;
const HISTORY_RESTORE_QUERY = "all";
const LANE_MESSAGE_LIMIT = 60;
const LANE_AGENT_LIMIT = 3;
// applies to the working agents only; the coordinator lane is additive
const COORDINATOR_LANE_AGENT = "coordinator";
const COORD_FEED_LIMIT = 6;
const COORD_FEED_EXPANDED_LIMIT = 40;
const TRACE_ROW_LIMIT = 6;
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
  coordinator: "Orchestrator",
};
const LANE_GLYPHS = {
  coordinator: "GM",
};
const AGENT_IMAGES = {
  claude: "./assets/claude.png",
  codex: "./assets/codex.png",
  coordinator: "./assets/orchestrator.png",
};

/* Themes live in workbench.css as [data-theme="..."] blocks. The picked one
   is persisted with the rest of the workbench settings, so the app reopens in
   whatever the operator last chose. LEGACY_THEMES migrates the old two-way
   dark/light setting that earlier builds wrote to localStorage. */
const THEMES = ["carbon", "chrome", "console"];
const DEFAULT_THEME = "carbon";
const LEGACY_THEMES = { dark: "carbon", light: "chrome" };

const state = {
  token: "",
  bridgeUrl: "",
  theme: DEFAULT_THEME,
  focusMode: false,
  connected: false,
  eventCursor: 0,
  sessionTimer: null,
  workbenchTimer: null,
  commandRunning: false,
  agents: [],
  directAgents: [],
  lanes: {},
  streams: {},
  eventMessages: {},
  coordItems: [],
  coordExpanded: false,
  systemDetailsVisible: true,
  traceVisible: false,
  showSystemFeed: false,
  systemDrawerOpen: false,
  trace: {},
  currentProject: "",
  lastActivity: "",
  connectionFailures: 0,
  authBlocked: false,
  approvalActive: false,
  approvalProposalId: "",
  approvalSubmitting: false,
  projectCatalog: [],
  modelSelection: {},
  composerExpanded: false,
  activePrompt: "",
  newTaskClicks: 0,
  skills: [],
  selectedSkills: [],
  skillsFilter: "All",
  sessionId: "",
  transcript: [],
  historyLoaded: false,
  historyQuery: "",
  latestSession: null,
  uiSaveTimer: null,
  uiRestoredSession: "",
  completionOptions: [],
  completionIndex: 0,
  completionRequest: 0,
  completionTimer: null,
};

const previewSession = {
  project: "chatboks",
  projects: ["chatboks", "gracious-eagle-otel", "romantic-otter-otel-7", "chatboks_2.0"],
  project_catalog: [
    { name: "chatboks", path: "C:/workspace/chatboks", agents: ["claude", "codex"], primary: "codex" },
    { name: "gracious-eagle-otel", path: "C:/workspace/gracious-eagle-otel", agents: ["claude", "codex"], primary: "claude" },
    { name: "romantic-otter-otel-7", path: "C:/workspace/romantic-otter-otel-7", agents: ["codex"], primary: "codex" },
    { name: "chatboks_2.0", path: "C:/workspace/chatboks-2", agents: ["claude", "codex", "coordinator"], primary: "codex" },
  ],
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
    "workArea", "focusButton", "focusLabel", "newTaskButton", "railProjectsButton",
  "projectButton", "projectDialog", "projectDialogBackdrop", "projectDialogClose", "projectSearch", "projectPath", "projectBrowseButton", "projectAddButton", "projectPickerList",
    "tokenBalances", "activePromptText", "settingsButton", "stripCpu", "stripRam",
  "topbarProject", "topbarSession", "topbarStatus", "liveButton", "liveDot", "liveLabel", "previewButton", "systemDrawerButton", "claudeUpdateButton", "systemDrawer",
  "sessionButton", "connectionToggle", "connectionPanel", "pairCode", "token", "pairButton",
  "bridgeUrl", "connectButton", "forgetButton", "errorBox", "connectionState", "connectionRecovery",
  "agentLanes", "coordDot", "coordState", "roleCallButton", "systemFeedButton", "logsButton", "systemDetailsButton", "traceButton", "systemDetails", "tracePanel",
  "approvalPanel", "approvalMeta", "approvalSummary", "approvalEstimate",
  "approvalHelper", "approvalRaw", "approvalModification", "approvalStatus", "approvalCommandPreview",
  "approvalBuildActions", "approveButton", "modifyButton", "rejectButton", "dismissButton",
  "attentionPanel", "attentionMeta", "attentionTitle", "attentionSummary", "attentionRaw", "attentionGuidance",
  "resumePanel", "resumeSummary", "resumeButton", "endTaskButton",
    "coordTime", "coordFeed", "statRound", "statMode", "statNext", "statStatus", "historySearch",
    "traceAgentCount", "traceAgentList", "tracePacketCount", "tracePacketList",
    "composerCard", "composerExpandButton", "workbenchPrompt", "commandCompletionPalette", "sendStatus", "sendButton", "stopButton",
    "skillsButton", "skillsPanel", "skillsCloseButton", "skillsSearch", "skillsFilters", "skillsList", "selectedSkills",
  "envProject", "envBranch", "envCleanDot", "envClean", "envChanges", "envCommit",
  "bridgeDot", "bridgePid", "bridgePairTtl", "bridgeOperator",
  "progressList", "progressCount", "progressPercent",
  "graphDot", "graphHealth", "graphFiles", "graphNodes", "graphEdges", "graphIndexed",
  "monTailscale", "monCpu", "monRam",
]) {
  els[id] = document.getElementById(id);
}

/* ---------- settings ---------- */

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    state.token = saved.token || "";
    state.bridgeUrl = saved.bridgeUrl || "";
    state.theme = normaliseTheme(saved.theme);
  } catch {
    state.token = "";
    state.bridgeUrl = "";
    state.theme = DEFAULT_THEME;
  }
  els.token.value = state.token;
  els.bridgeUrl.value = state.bridgeUrl || "";
}

function saveSettings() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: state.token, bridgeUrl: state.bridgeUrl, theme: state.theme }));
}

function normaliseTheme(value) {
  const name = String(value || "");
  if (THEMES.includes(name)) return name;
  return LEGACY_THEMES[name] || DEFAULT_THEME;
}

function setTheme(theme) {
  state.theme = normaliseTheme(theme);
  document.documentElement.dataset.theme = state.theme;
  for (const swatch of document.querySelectorAll(".swatch")) {
    swatch.setAttribute("aria-pressed", String(swatch.dataset.setTheme === state.theme));
  }
  saveSettings();
  scheduleWorkbenchUiSave();
}

function setFocusMode(on) {
  state.focusMode = Boolean(on);
  document.body.classList.toggle("is-focus", state.focusMode);
  els.focusButton.setAttribute("aria-pressed", String(state.focusMode));
  els.focusLabel.textContent = state.focusMode ? "Exit focus" : "Focus";
  scheduleWorkbenchUiSave();
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
  window.clearTimeout(state.uiSaveTimer);
  state.uiSaveTimer = null;
  state.eventCursor = 0;
  state.streams = {};
  state.eventMessages = {};
  state.coordItems = [];
  state.trace = {};
  state.lanes = {};
  state.activePrompt = "";
  state.sessionId = "";
  state.transcript = [];
  state.historyLoaded = false;
  state.historyQuery = "";
  state.latestSession = null;
  state.uiRestoredSession = "";
  if (els.historySearch) els.historySearch.value = "";
  renderActivePrompt("");
  els.agentLanes.innerHTML = "";
}

function scheduleWorkbenchUiSave() {
  if (!state.sessionId || !state.token || !state.bridgeUrl) return;
  window.clearTimeout(state.uiSaveTimer);
  state.uiSaveTimer = window.setTimeout(saveWorkbenchUi, 350);
}

async function saveWorkbenchUi() {
  state.uiSaveTimer = null;
  const lanes = {};
  for (const [agent, lane] of Object.entries(state.lanes)) {
    const scrollRange = Math.max(0, lane.stream.scrollHeight - lane.stream.clientHeight);
    lanes[agent] = {
      at_bottom: lane.atBottom !== false,
      scroll_ratio: scrollRange > 0 ? lane.stream.scrollTop / scrollRange : 1,
      history_limit: lane.historyLimit || LANE_MESSAGE_LIMIT,
    };
  }
  try {
    await apiFetch("/api/session/ui", {
      method: "POST",
      body: JSON.stringify({
        session: state.sessionId,
        theme: state.theme,
        history_query: state.historyQuery,
        composer_draft: els.workbenchPrompt.value,
        composer_expanded: state.composerExpanded,
        focus_mode: state.focusMode,
        selected_skills: state.selectedSkills,
        lanes,
      }),
    });
  } catch {
    // Session polling reports connection failures; UI-state persistence is best effort.
  }
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
    const limit = state.historyLoaded ? TRANSCRIPT_POLL_LIMIT : HISTORY_RESTORE_QUERY;
    const data = await apiFetch(`/api/session?cursor=${state.eventCursor}&limit=${limit}`);
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
  renderBridge(data.bridge);
  renderGraph(data.graph);
  renderMonitor(data.monitor);
  els.envProject.textContent = data.project || "-";
}

/* ---------- message helpers ---------- */

async function copyText(text) {
  const value = String(text || "");
  if (!value) return false;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // Fall through to the textarea fallback below.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

function copyButtonFor(text) {
  const button = document.createElement("button");
  button.className = "card-copy-button";
  button.type = "button";
  button.textContent = "Copy";
  button.setAttribute("aria-label", "Copy this response");
  button.title = "Copy this response";
  button.addEventListener("click", async (event) => {
    event.stopPropagation();
    const copied = await copyText(text);
    button.textContent = copied ? "Copied" : "Copy failed";
    button.classList.toggle("copied", copied);
    window.setTimeout(() => {
      button.textContent = "Copy";
      button.classList.remove("copied");
    }, 1500);
  });
  return button;
}

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
  const key = upper.startsWith("TASK_COMPLETE")
    ? "complete"
    : upper.startsWith("PROPOSAL")
      ? "proposal"
      : upper.startsWith("BLOCKED")
        ? "blocked"
        : upper.startsWith("QUESTION")
          ? "question"
          : upper.startsWith("HANDOFF")
            ? "handoff"
            : upper.startsWith("SKIP")
              ? "skip"
              : "signal";
  const presentation = {
    complete: { icon: "FLAG", title: "Complete" },
    proposal: { icon: "!", title: "Approval required" },
    blocked: { icon: "!", title: "Needs your input" },
    question: { icon: "?", title: "Question" },
    handoff: { icon: "->", title: "Handoff" },
    skip: { icon: "-", title: "No additional work" },
    signal: { icon: ">", title: "Agent signal" },
  }[key];
  card.className = `signal-card signal-${key}`;
  const arrow = document.createElement("span");
  arrow.className = "signal-icon";
  arrow.textContent = presentation.icon;
  const content = document.createElement("span");
  content.className = "signal-copy";
  const title = document.createElement("strong");
  title.textContent = presentation.title;
  const label = document.createElement("strong");
  label.textContent = `>>> ${signal}`;
  content.append(title, label);
  card.appendChild(arrow);
  card.appendChild(content);
  if (timestamp) {
    const time = document.createElement("time");
    time.textContent = timestamp;
    card.appendChild(time);
  }
  return card;
}

function messageCard(text, { streaming = false, timestamp = "", user = false } = {}) {
  const fragment = document.createDocumentFragment();
  const { body, signals } = splitSignals(text);
  if (body || streaming) {
    const card = document.createElement("section");
      card.className = user ? "message-card user-message-card" : streaming ? "message-card streaming" : "message-card";
        if (!user && body) {
          card.classList.add("copyable-message-card");
          const tools = document.createElement("div");
          tools.className = "message-card-tools";
          tools.appendChild(copyButtonFor(body));
          card.appendChild(tools);
        }
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
    return "Orchestrator is ready. Direct @coordinator replies appear here.";
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

/* The coordinator lane is the synthesis seat: it reads what the working
   agents produced and sums it up before the operator decides. So it is pinned
   to the right of them, it does not spend one of their LANE_AGENT_LIMIT slots,
   and it stays on screen while idle or offline instead of being filtered out
   with the live agents. */
function pinCoordinatorLast(agents, data) {
  const roster = uniqueAgents(agents).filter((agent) => agent !== COORDINATOR_LANE_AGENT);
  const configured = uniqueAgents([
    ...(data.agents || []),
    ...(data.direct_agents || []),
    ...(data.lane_agents || []),
  ]);
  const capped = roster.slice(0, LANE_AGENT_LIMIT);
  if (configured.includes(COORDINATOR_LANE_AGENT)) {
    capped.push(COORDINATOR_LANE_AGENT);
  }
  return capped;
}

function deriveLaneAgents(data) {
  const statuses = data.agent_statuses || {};
  const serverLanes = uniqueAgents(data.lane_agents || []).filter(
    (agent) => agent === COORDINATOR_LANE_AGENT || agentIsLive(agent, statuses),
  );
  if (serverLanes.length) {
    return pinCoordinatorLast(serverLanes, data);
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
  return pinCoordinatorLast(lanes.length ? lanes : mainAgents, data);
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
    const imageSource = AGENT_IMAGES[canonicalAgent(agent)];
    if (imageSource) {
      const image = document.createElement("img");
      image.src = imageSource;
      image.alt = "";
      logo.classList.add("agent-avatar");
      logo.appendChild(image);
    } else {
      logo.textContent = laneGlyph(agent);
    }
    const title = document.createElement("div");
    const name = document.createElement("h2");
    name.textContent = laneDisplayName(agent);
    const status = document.createElement("p");
    const dot = document.createElement("span");
    dot.className = "live-dot";
    const statusLabel = document.createElement("span");
    statusLabel.textContent = " Offline";
    const activity = document.createElement("span");
    activity.className = "agent-activity hidden";
    activity.textContent = "Working";
    status.appendChild(dot);
    status.appendChild(statusLabel);
    status.appendChild(activity);
    title.appendChild(name);
    title.appendChild(status);
    header.appendChild(logo);
    header.appendChild(title);
    const menu = document.createElement("button");
    menu.className = "icon-button menu-button";
    menu.type = "button";
    menu.setAttribute("aria-label", `${laneDisplayName(agent)} options`);
    menu.title = `${laneDisplayName(agent)} options`;
    if (agent === "claude" || agent === "codex") {
      const modelControl = document.createElement("div");
      modelControl.className = "agent-model-control";
      const modelSelect = document.createElement("select");
      modelSelect.className = "agent-model-select";
      modelSelect.setAttribute("aria-label", `${laneDisplayName(agent)} model`);
      modelSelect.addEventListener("change", () => chooseAgentModel(agent, modelSelect));
      const modelWarning = document.createElement("span");
      modelWarning.className = "agent-model-warning hidden";
      modelControl.appendChild(modelSelect);
      modelControl.appendChild(modelWarning);
      header.appendChild(modelControl);
      state.lanes[agent] = { pane, stream: null, statusDot: dot, statusLabel, activity, modelSelect, modelWarning };
    }
    if (agent === "claude") {
      menu.className = "ghost-button claude-auth-button";
      menu.textContent = "Sign in";
      menu.addEventListener("click", startClaudeLogin);
    } else if (agent === "codex") {
      menu.className = "ghost-button claude-auth-button";
      menu.textContent = "Update";
      menu.title = "Update Codex";
      menu.addEventListener("click", updateCodex);
    } else {
      menu.textContent = "...";
    }
    header.appendChild(menu);

    const stream = document.createElement("div");
    stream.className = "agent-stream";
    const promptNav = document.createElement("nav");
    promptNav.className = "lane-prompt-nav hidden";
    promptNav.setAttribute("aria-label", `${laneDisplayName(agent)} prompt navigation`);
    const jumpButton = document.createElement("button");
    jumpButton.className = "lane-jump-button hidden";
    jumpButton.type = "button";
    jumpButton.textContent = "↓";
    jumpButton.setAttribute("aria-label", `Jump to latest ${laneDisplayName(agent)} output`);
    jumpButton.title = "Jump to latest output";
    jumpButton.addEventListener("click", () => {
      stream.scrollTop = stream.scrollHeight;
      updateLaneScrollState(agent);
    });
    stream.addEventListener("scroll", () => {
      updateLaneScrollState(agent);
      scheduleWorkbenchUiSave();
    });

    pane.appendChild(header);
    pane.appendChild(stream);
    pane.appendChild(promptNav);
    pane.appendChild(jumpButton);
    els.agentLanes.appendChild(pane);
    state.lanes[agent] = {
      ...(state.lanes[agent] || {}),
      pane,
      stream,
      promptNav,
      jumpButton,
      statusDot: dot,
      statusLabel,
      activity,
      atBottom: true,
      savedScrollTop: 0,
      historyLimit: LANE_MESSAGE_LIMIT,
    };
  }
}

function renderModelSelectors(selection = {}) {
  state.modelSelection = selection || {};
  for (const [agent, lane] of Object.entries(state.lanes)) {
    if (!lane.modelSelect) continue;
    const details = state.modelSelection[agent] || { current: "", options: [""] };
    const options = Array.isArray(details.options) ? details.options : [""];
    lane.modelSelect.innerHTML = "";
    for (const model of options) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model || "Model: Default";
      lane.modelSelect.appendChild(option);
    }
    const custom = document.createElement("option");
    custom.value = "__custom__";
    custom.textContent = "Custom model...";
    lane.modelSelect.appendChild(custom);
    lane.modelSelect.value = details.current || "";
    if (lane.modelWarning) {
      const warning = String((details.warnings || {})[details.current || ""] || "");
      lane.modelWarning.textContent = warning;
      lane.modelWarning.classList.toggle("hidden", !warning);
    }
  }
}

function updateLaneScrollState(agent) {
  const lane = state.lanes[agent];
  if (!lane?.stream) return;
  const distanceFromBottom = lane.stream.scrollHeight - lane.stream.scrollTop - lane.stream.clientHeight;
  lane.atBottom = distanceFromBottom < 48;
  lane.savedScrollTop = lane.stream.scrollTop;
  lane.jumpButton?.classList.toggle("hidden", lane.atBottom);
  updatePromptNavigation(lane);
}

function updatePromptNavigation(lane) {
  if (!lane?.promptNav) return;
  const anchors = [...lane.stream.querySelectorAll("[data-prompt-anchor]")];
  let currentId = anchors[0]?.dataset.promptAnchor || "";
  const threshold = lane.stream.scrollTop + 36;
  for (const anchor of anchors) {
    if (anchor.offsetTop <= threshold) currentId = anchor.dataset.promptAnchor;
  }
  for (const pip of lane.promptNav.querySelectorAll("button")) {
    pip.classList.toggle("active", pip.dataset.target === currentId);
  }
}

function renderPromptNavigation(agent, lane) {
  lane.promptNav.replaceChildren();
  const anchors = [...lane.stream.querySelectorAll("[data-prompt-anchor]")];
  lane.promptNav.classList.toggle("hidden", anchors.length < 2);
  anchors.forEach((anchor, index) => {
    const button = document.createElement("button");
    const prompt = anchor.dataset.promptText || "";
    button.type = "button";
    button.className = "lane-prompt-pip";
    button.dataset.target = anchor.dataset.promptAnchor;
    button.setAttribute("aria-label", `Jump to prompt ${index + 1}`);
    button.title = `Prompt ${index + 1}: ${prompt.slice(0, 100)}`;
    button.addEventListener("click", () => {
      lane.stream.scrollTop = Math.max(0, anchor.offsetTop - 16);
      updateLaneScrollState(agent);
    });
    lane.promptNav.appendChild(button);
  });
  updatePromptNavigation(lane);
}

async function chooseAgentModel(agent, select) {
  let model = select.value;
  if (model === "__custom__") {
    model = window.prompt(`Model identifier for ${laneDisplayName(agent)}:`)?.trim() || "";
    if (!model) {
      renderModelSelectors(state.modelSelection);
      return;
    }
  }
  select.disabled = true;
  try {
    const data = await apiFetch("/api/agent/model", {
      method: "POST",
      body: JSON.stringify({ agent, model }),
    });
    applySession(data);
  } catch (error) {
    showError(friendlyFetchError(error));
    renderModelSelectors(state.modelSelection);
  } finally {
    select.disabled = false;
  }
}

function renderLanes(transcript) {
  const indexedTranscript = (transcript || []).map((item, index) => ({ ...item, index }));
  const latestUserMessage = [...indexedTranscript].reverse().find((item) => canonicalAgent(item.sender) === "you");
  for (const [agent, lane] of Object.entries(state.lanes)) {
    updateLaneScrollState(agent);
    const stickToBottom = lane.atBottom !== false;
    const previousScrollTop = lane.savedScrollTop || 0;
    lane.stream.innerHTML = "";
    const messages = [];
    const seenTranscriptIndexes = new Set();
    for (const message of indexedTranscript.filter((item) => canonicalAgent(item.sender) === agent)) {
      const prompt = [...indexedTranscript]
        .reverse()
        .find((item) => item.index < message.index && canonicalAgent(item.sender) === "you");
      if (prompt && !seenTranscriptIndexes.has(prompt.index)) {
        messages.push(prompt);
        seenTranscriptIndexes.add(prompt.index);
      }
      messages.push(message);
      seenTranscriptIndexes.add(message.index);
    }
    const transcriptText = new Set(
      transcript
        .filter((item) => canonicalAgent(item.sender) === agent)
        .map((message) => String(message.text || "").trim()),
    );
    const eventMessages = (state.eventMessages[agent] || [])
      .filter((message) => !transcriptText.has(String(message.text || "").trim()));
    if (eventMessages.length && latestUserMessage && !seenTranscriptIndexes.has(latestUserMessage.index)) {
      messages.push(latestUserMessage);
    }
    const combined = [...messages, ...eventMessages];
    const query = state.historyQuery.trim().toLowerCase();
    let visible = combined;
    if (query) {
      const matchingIndexes = new Set();
      combined.forEach((message, index) => {
        if (String(message.text || "").toLowerCase().includes(query)) {
          matchingIndexes.add(index);
          if (canonicalAgent(message.sender) !== "you") {
            for (let promptIndex = index - 1; promptIndex >= 0; promptIndex -= 1) {
              if (canonicalAgent(combined[promptIndex].sender) === "you") {
                matchingIndexes.add(promptIndex);
                break;
              }
            }
          }
        }
      });
      visible = combined.filter((_message, index) => matchingIndexes.has(index));
    }
    const historyLimit = query ? Math.max(LANE_MESSAGE_LIMIT, visible.length) : (lane.historyLimit || LANE_MESSAGE_LIMIT);
    const hasEarlier = visible.length > historyLimit;
    const recent = visible.slice(-historyLimit);
    if (!recent.length && !state.streams[agent]) {
      const empty = document.createElement("p");
      empty.className = "lane-empty";
      empty.textContent = laneEmptyText(agent);
      lane.stream.appendChild(empty);
      lane.promptNav.replaceChildren();
      continue;
    }
    if (hasEarlier) {
      const loadEarlier = document.createElement("button");
      loadEarlier.type = "button";
      loadEarlier.className = "load-earlier-button";
      loadEarlier.textContent = `Load ${Math.min(LANE_MESSAGE_LIMIT, visible.length - historyLimit)} earlier`;
      loadEarlier.addEventListener("click", () => {
        lane.historyLimit = historyLimit + LANE_MESSAGE_LIMIT;
        renderLanes(state.transcript);
        scheduleWorkbenchUiSave();
      });
      lane.stream.appendChild(loadEarlier);
    }
    for (const message of recent) {
      const isPrompt = canonicalAgent(message.sender) === "you";
      if (isPrompt) {
        const anchor = document.createElement("div");
        const promptId = `${agent}-${message.id ?? message.index}`;
        anchor.dataset.promptAnchor = promptId;
        anchor.dataset.promptText = String(message.text || "");
        anchor.appendChild(messageCard(message.text, { user: true }));
        lane.stream.appendChild(anchor);
      } else {
        lane.stream.appendChild(messageCard(message.text));
      }
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
    if (stickToBottom) {
      lane.stream.scrollTop = lane.stream.scrollHeight;
    } else {
      lane.stream.scrollTop = Math.min(previousScrollTop, lane.stream.scrollHeight);
    }
    renderPromptNavigation(agent, lane);
    updateLaneScrollState(agent);
  }
}

function updateLaneActivity(data) {
  const status = String(data.status || "idle").toLowerCase();
  const proposalOwner = canonicalAgent(data.proposal?.proposed_by || "");
  for (const [agent, lane] of Object.entries(state.lanes)) {
    const busy = Boolean(state.streams[agent]) || (data.command_running && canonicalAgent(data.next_agent) === agent);
    const awaitingApproval = status === "awaiting_approval" && proposalOwner === agent;
    const needsInput = (status === "blocked" || status === "awaiting_input") && canonicalAgent(data.last_agent) === agent;
    lane.statusDot.classList.toggle("offline", !state.connected);
    lane.statusDot.classList.toggle("busy", busy);
    lane.pane.classList.toggle("awaiting-approval", awaitingApproval);
    lane.pane.classList.toggle("needs-input", needsInput);
    lane.pane.classList.toggle("is-working", busy);
    lane.activity.classList.toggle("hidden", !busy);
    lane.statusLabel.textContent = !state.connected
      ? " Offline"
      : busy
        ? " Working"
        : awaitingApproval
          ? " Awaiting approval"
          : needsInput
            ? " Needs input"
            : " Online";
  }
}

function previewTargetFromTranscript(transcript) {
  for (const item of [...(transcript || [])].reverse()) {
    const text = String(item.text || "");
    const url = text.match(/https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?[^\s"')\]]*/i)?.[0];
    if (url) return { target: url, label: "Open preview" };
    const artifact = text.match(/[A-Za-z]:\\[^\n"']+?\.(?:html?|exe)\b/i)?.[0];
    if (artifact) return { target: artifact, label: artifact.toLowerCase().endsWith(".exe") ? "Open app" : "Open HTML" };
  }
  return null;
}

function updatePreviewButton(data) {
  const preview = previewTargetFromTranscript(data.transcript);
  state.previewTarget = preview?.target || "";
  els.previewButton.disabled = !state.previewTarget || !window.pywebview?.api?.open_preview;
  els.previewButton.textContent = preview?.label || "Preview";
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
    if (kind === "message" && state.lanes[sender]) {
      if (!state.eventMessages[sender]) state.eventMessages[sender] = [];
      state.eventMessages[sender].push({
        id: event.id || 0,
        sender,
        text: event.text || "",
        timestamp: event.timestamp || "",
      });
      state.eventMessages[sender] = state.eventMessages[sender].slice(-LANE_MESSAGE_LIMIT);
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

function isSystemFeedItem(item) {
  return canonicalAgent(item.sender || "system") === "system";
}

function renderCoordinator(data) {
  const limit = state.coordExpanded ? COORD_FEED_EXPANDED_LIMIT : COORD_FEED_LIMIT;
  const visibleItems = state.showSystemFeed
    ? state.coordItems
    : state.coordItems.filter((item) => !isSystemFeedItem(item));
  const hiddenSystemCount = state.showSystemFeed
    ? 0
    : state.coordItems.length - visibleItems.length;
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
  els.systemFeedButton.textContent = state.showSystemFeed
    ? "Hide System"
    : hiddenSystemCount
      ? `System (${hiddenSystemCount})`
      : "System";
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
  for (const button of els.approvalBuildActions.querySelectorAll("button")) button.disabled = disabled;
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
  const candidates = Array.isArray(proposal.candidates) ? proposal.candidates : [];
  if (candidates.length) {
    return candidates.map((candidate) => {
      const name = agentDisplayName(String(candidate.agent || "agent"));
      const raw = String(candidate.raw || candidate.summary || "No detailed proposal text was included.").trim();
      return `${name}\n${raw}${candidate.raw_truncated ? "\n\n[truncated]" : ""}`;
    }).join("\n\n---\n\n");
  }
  const raw = String(proposal.raw || "").trim();
  if (!raw) {
    return "No detailed proposal text was included in the session snapshot.";
  }
  return proposal.raw_truncated ? `${raw}\n\n[truncated]` : raw;
}

function proposalCandidates(proposal) {
  const supplied = Array.isArray(proposal.candidates) ? proposal.candidates : [];
  const candidates = supplied.length ? supplied : [{
    agent: proposal.proposed_by,
    summary: proposal.summary,
    execution_estimate: proposal.execution_estimate,
  }];
  const seen = new Set();
  return candidates.filter((candidate) => {
    const agent = canonicalAgent(candidate.agent || "");
    if (!agent || seen.has(agent)) return false;
    seen.add(agent);
    return true;
  });
}

function renderBuildChoices(proposal) {
  const candidates = proposalCandidates(proposal);
  els.approvalBuildActions.innerHTML = "";
  for (const candidate of candidates) {
    const agent = canonicalAgent(candidate.agent);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "approval-button builder-action";
    button.textContent = `Build with ${agentDisplayName(agent)}`;
    button.title = `Approve this plan and let only ${agentDisplayName(agent)} make changes`;
    button.disabled = state.approvalSubmitting;
    button.addEventListener("click", () => submitApproval(`APPROVE ${agent}`));
    button.addEventListener("focus", () => updateApprovalActionState(`APPROVE ${agent}`));
    els.approvalBuildActions.appendChild(button);
  }
  els.approveButton.classList.toggle("hidden", candidates.length > 0);
}

function criteriaGateText(gate) {
  const reasonLabels = {
    multi_agent: "Multi-agent prompt",
    broad: "Broad scope",
    durable: "Durable protocol or memory impact",
    security: "Safety, auth, remote access, or execution impact",
    ambiguous: "Ambiguous outcome",
  };
  const agents = uniqueAgents(gate.agents || []).map(agentDisplayName).join(", ") || "selected agents";
  const reasons = (gate.reasons || []).map((reason) => reasonLabels[reason] || reason).join(", ") || "criteria gate";
  const lines = [
    `Task: ${gate.routed_text || gate.original_text || "No task text was recorded."}`,
    `Agents: ${agents}`,
    `Why paused: ${reasons}`,
    "",
    "Minimum acceptance criteria:",
    "- Desired outcome is explicit enough that agents can verify completion.",
    "- Safety, auth, remote access, or durable memory impact is named when relevant.",
    "- Verification evidence is expected before TASK_COMPLETE.",
  ];
  return lines.join("\n");
}

function setApprovalDetails(label, open) {
  const details = els.approvalRaw.closest("details");
  if (!details) return;
  const summary = details.querySelector("summary");
  if (summary) summary.textContent = label;
  details.open = open;
}

function renderApproval(data) {
  const proposal = data.proposal || null;
  const awaitingApproval = data.status === "awaiting_approval" && proposal;
  const gate = data.criteria_gate || null;
  const awaitingCriteria = data.status === "awaiting_criteria" && gate;
  els.approvalPanel.classList.toggle("hidden", !awaitingApproval && !awaitingCriteria);
  if (!awaitingApproval && !awaitingCriteria) {
    state.approvalActive = false;
    state.approvalProposalId = "";
    setApprovalControls(false);
    setApprovalStatus("");
    els.approvalCommandPreview.textContent = "";
    els.approvalHelper.textContent = "";
    els.approvalBuildActions.innerHTML = "";
    els.dismissButton.classList.remove("hidden");
    els.approveButton.textContent = "Build with primary";
    setApprovalDetails("Proposal details", false);
    return;
  }
  if (awaitingCriteria) {
    const gateId = String(gate.id || `${gate.routed_text || gate.original_text || "criteria"}`);
    if (state.approvalProposalId !== gateId) {
      els.approvalModification.value = "";
      setApprovalStatus("Choose whether to run this task, add criteria, or cancel it.");
    }
    state.approvalActive = true;
    state.approvalProposalId = gateId;
    els.approvalMeta.textContent = "Acceptance criteria gate";
    els.approvalSummary.textContent = "Approve, modify, or reject before agents run";
    els.approvalEstimate.textContent = "No agent has started this task yet.";
    els.approvalHelper.textContent = "Approve starts the selected agents. Modify appends extra criteria. Reject cancels this pending task.";
    els.approvalRaw.textContent = criteriaGateText(gate);
    setApprovalDetails("Criteria details", true);
    els.approvalBuildActions.innerHTML = "";
    els.approveButton.textContent = "Approve criteria";
    els.approveButton.classList.remove("hidden");
    els.dismissButton.classList.add("hidden");
    setApprovalControls(false);
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
  const candidates = proposalCandidates(proposal);
  els.approvalMeta.textContent = candidates.length > 1 ? `${candidates.length} plans ready` : `${proposer} proposal`;
  els.approvalSummary.textContent = candidates.length > 1 ? "Choose who should build" : proposal.summary || "Review proposal";
  els.approvalEstimate.textContent = candidates
    .map((candidate) => `${agentDisplayName(candidate.agent)}: ${formatExecutionEstimate(candidate.execution_estimate)}`)
    .join(" | ") || formatExecutionEstimate(proposal.execution_estimate);
  els.approvalHelper.textContent = "Review the plans, then choose the one agent allowed to build. Modify requires a note; Dismiss closes the gate without execution.";
  els.approvalRaw.textContent = proposalRawText(proposal);
  setApprovalDetails("Proposal details", false);
  els.approveButton.textContent = "Build with primary";
  els.dismissButton.classList.remove("hidden");
  renderBuildChoices(proposal);
  setApprovalControls(false);
}

function latestSignalMessage(items, signal) {
  const marker = `>>> ${signal}`;
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const text = String(items[index].text || "");
    if (text.toUpperCase().includes(marker)) return items[index];
  }
  return null;
}

function firstMeaningfulLine(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line && !line.startsWith(">>>")) || "";
}

function renderAttention(data) {
  const status = String(data.status || "").toLowerCase();
  const signal = status === "awaiting_input" ? "QUESTION" : status === "blocked" ? "BLOCKED" : "";
  els.attentionPanel.classList.toggle("hidden", !signal);
  if (!signal) return;
  const message = latestSignalMessage(data.transcript || [], signal);
  const raw = String(message?.text || data.active_task || "No agent detail was recorded in this session snapshot.");
  const isQuestion = signal === "QUESTION";
  els.attentionMeta.textContent = `${agentDisplayName(message?.sender || data.next_agent || "agent")} · ${signal}`;
  els.attentionTitle.textContent = isQuestion ? "Question needs your input" : "Work is blocked";
  els.attentionSummary.textContent = firstMeaningfulLine(raw) || (isQuestion ? "Reply with the decision or missing detail." : "Review the blocker and provide the next direction.");
  els.attentionRaw.textContent = raw;
  els.attentionGuidance.textContent = isQuestion
    ? "Reply in the composer below to continue."
    : "Reply in the composer below with direction, a workaround, or a new task.";
}

/* ---------- left rail ---------- */

function latestUserPrompt(transcript = []) {
  for (let index = transcript.length - 1; index >= 0; index -= 1) {
    const item = transcript[index] || {};
    if (canonicalAgent(item.sender) === "you") {
      return { index, text: String(item.text || "").trim() };
    }
  }
  return { index: -1, text: "" };
}

function activePromptFromSession(data, transcript = []) {
  const explicit = String(data.command_text || data.active_task || "").trim();
  if (explicit) {
    return explicit;
  }
  const status = String(data.status || "").toLowerCase();
  const canUseLatestPrompt = Boolean(data.command_running)
    || ["active", "handoff", "awaiting_approval", "awaiting_input", "blocked", "awaiting_criteria"].includes(status);
  if (canUseLatestPrompt) {
    return latestUserPrompt(transcript).text;
  }
  return "";
}

function hasVisibleTask(data) {
  const status = String(data.status || "").toLowerCase();
  return Boolean(data.command_running)
    || Boolean(String(data.command_text || data.active_task || "").trim())
    || ["active", "handoff", "awaiting_approval", "awaiting_input", "blocked", "awaiting_criteria", "awaiting_resume"].includes(status);
}

function laneTranscriptForSession(data, transcript = []) {
  return transcript;
}

function renderActivePrompt(text) {
  const prompt = String(text || "").trim();
  state.activePrompt = prompt;
  els.activePromptText.textContent = prompt || "No active prompt.";
  els.activePromptText.classList.toggle("is-empty", !prompt);
  els.activePromptText.scrollTop = 0;
}

function renderProjects(projects, currentProject) {
  state.currentProject = currentProject;
  els.railProjectsButton.title = currentProject
    ? `Choose or manage projects. Current project: ${currentProject}`
    : "Choose or manage projects";
}

function projectDetails(project) {
  return state.projectCatalog.find((item) => item.name === project) || { name: project, path: "", agents: [], primary: "" };
}

function renderProjectPicker(query = "") {
  const normalizedQuery = query.trim().toLowerCase();
  const projects = state.projectCatalog.length ? state.projectCatalog : (state.currentProject ? [projectDetails(state.currentProject)] : []);
  const matching = projects.filter((project) => {
    const searchable = [project.name, project.path, ...(project.agents || [])].join(" ").toLowerCase();
    return !normalizedQuery || searchable.includes(normalizedQuery);
  });
  els.projectPickerList.innerHTML = "";
  if (!matching.length) {
    const empty = document.createElement("p");
    empty.className = "project-picker-empty";
    empty.textContent = "No projects match that search.";
    els.projectPickerList.appendChild(empty);
    return;
  }
  for (const project of matching) {
    const row = document.createElement("div");
    row.className = "project-picker-row";
    const item = document.createElement("button");
    item.type = "button";
    item.className = project.name === state.currentProject ? "project-picker-item active" : "project-picker-item";
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", String(project.name === state.currentProject));
    const title = document.createElement("strong");
    title.textContent = project.name;
    const path = document.createElement("span");
    path.className = "project-picker-path";
    path.textContent = project.path || "Path is not configured";
    const meta = document.createElement("span");
    meta.className = "project-picker-meta";
    const agents = project.agents?.length ? project.agents.join(" + ") : "No agents configured";
    meta.textContent = project.primary ? `${agents}  |  primary: ${project.primary}` : agents;
    item.append(title, path, meta);
    item.addEventListener("click", async () => {
      closeProjectPicker();
      if (project.name !== state.currentProject) await switchProject(project.name);
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "project-remove-button";
    remove.textContent = "X";
    remove.title = project.name === state.currentProject
      ? "Switch projects before removing this one"
      : `Remove ${project.name} from ChatBoks`;
    remove.setAttribute("aria-label", remove.title);
    remove.disabled = project.name === state.currentProject;
    remove.addEventListener("click", () => removeProject(project.name));
    row.append(item, remove);
    els.projectPickerList.appendChild(row);
  }
}

function renderResumePrompt(data) {
  const pending = Boolean(data.recovery_pending) && data.status === "awaiting_resume";
  els.resumePanel.classList.toggle("hidden", !pending);
  if (pending) {
    els.resumeSummary.textContent = String(data.active_task || "A previous task was interrupted before it completed.");
  }
}

async function removeProject(project) {
  if (project === state.currentProject || !window.confirm(`Remove ${project} from ChatBoks? The project files will not be deleted.`)) return;
  try {
    await apiFetch("/api/projects/remove", {
      method: "POST",
      body: JSON.stringify({ project }),
    });
    state.projectCatalog = state.projectCatalog.filter((item) => item.name !== project);
    renderProjectPicker(els.projectSearch.value);
    renderProjects(state.projectCatalog.map((item) => item.name), state.currentProject);
    setSendState(false, `${project} removed from ChatBoks.`);
  } catch (error) {
    showError(friendlyFetchError(error));
  }
}

function openProjectPicker() {
  renderProjectPicker(els.projectSearch.value);
  els.projectDialog.classList.remove("hidden");
  els.projectSearch.focus();
}

function closeProjectPicker() {
  els.projectDialog.classList.add("hidden");
  els.projectSearch.value = "";
}

async function browseProjectFolder() {
  const selectedPath = await window.pywebview?.api?.choose_project_folder?.();
  if (selectedPath) els.projectPath.value = selectedPath;
}

async function addProject() {
  const path = els.projectPath.value.trim();
  if (!path) {
    els.projectPath.focus();
    return;
  }
  setConnectionBusy(els.projectAddButton, true, "Adding...");
  try {
    const result = await apiFetch("/api/projects", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    els.projectPath.value = "";
    await refreshWorkbench();
    const projects = Array.isArray(result.projects) ? result.projects : [];
    if (projects.length === 1 && projects[0] !== state.currentProject) {
      await switchProject(projects[0]);
    } else if (projects.length > 1) {
      setSendState(false, `${projects.length} projects added. Choose one from Projects.`);
    }
    showError("");
  } catch (error) {
    showError(friendlyFetchError(error));
  } finally {
    setConnectionBusy(els.projectAddButton, false, "Adding...");
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

function formatSeconds(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) {
    return "-";
  }
  if (value >= 60) {
    const minutes = Math.floor(value / 60);
    const remainder = Math.round(value % 60);
    return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
  }
  return `${Math.round(value)}s`;
}

function renderBridge(bridge) {
  if (!bridge) {
    els.bridgeDot.classList.add("offline");
    els.bridgePid.textContent = "unknown";
    els.bridgePairTtl.textContent = "-";
    els.bridgeOperator.textContent = "-";
    return;
  }

  const running = bridge.status === "running";
  els.bridgeDot.classList.toggle("offline", !running);
  els.bridgePid.textContent = running ? `PID ${bridge.pid || "-"}` : bridge.status || "offline";
  els.bridgePairTtl.textContent = bridge.pair_code_ttl_seconds !== undefined
    ? `${formatSeconds(bridge.pair_code_ttl_seconds)} remaining`
    : "-";
  els.bridgeOperator.textContent = bridge.operator_file_exists ? "Fresh" : "Missing";
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
  if (!graph.healthy) {
    const status = graph.status || "unavailable";
    els.graphHealth.textContent = status === "indexing" ? "Indexing" : status;
    els.graphDot.classList.toggle("offline", status !== "indexing");
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
  renderBridge(null);
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
}

function progressItem(label, state = "done") {
  const item = document.createElement("li");
  item.className = state === "done" ? "" : state;
  item.textContent = label;
  return item;
}

function renderProgress(data) {
  const expected = uniqueAgents(data.expected_agents || []);
  const completed = new Set(uniqueAgents(data.completed_agents || []));
  const nextAgent = canonicalAgent(data.next_agent || "");
  const status = String(data.status || "idle");
  const awaitingApproval = status === "awaiting_approval" && data.proposal;
  const awaitingCriteria = status === "awaiting_criteria" && data.criteria_gate;
  const rows = [];
  let done = 0;
  let total = 0;

  if (data.command_text || data.active_task) {
    rows.push(progressItem(`Command accepted: ${(data.command_text || data.active_task || "").slice(0, 52)}`));
  }

  if (awaitingApproval) {
    total += 1;
    rows.push(progressItem(`Approval needed: ${data.proposal.summary || "review proposal"}`, "active"));
  }

  if (awaitingCriteria) {
    total += 1;
    rows.push(progressItem("Criteria needed: approve, modify, or reject", "active"));
  }

  if (expected.length && !awaitingCriteria) {
    total += expected.length;
    for (const agent of expected) {
      const canonical = canonicalAgent(agent);
      const isDone = completed.has(canonical);
      if (isDone) {
        done += 1;
      }
      const state = isDone ? "done" : canonical === nextAgent || (data.command_running && !nextAgent) ? "active" : "pending";
      rows.push(progressItem(`${agentDisplayName(agent)} ${isDone ? "responded" : state === "active" ? "working" : "pending"}`, state));
    }
  } else if (data.command_running && !awaitingApproval) {
    total += 1;
    rows.push(progressItem("Routing command to an agent", "active"));
  }

  if (!rows.length) {
    rows.push(progressItem("Idle. No active task.", "pending"));
  }

  els.progressList.innerHTML = "";
  for (const row of rows) {
    els.progressList.appendChild(row);
  }

  if (awaitingApproval) {
    els.progressCount.textContent = "approval needed";
    els.progressPercent.textContent = "hold";
    return;
  }
  if (awaitingCriteria) {
    els.progressCount.textContent = "criteria needed";
    els.progressPercent.textContent = "hold";
    return;
  }
  if (!total) {
    els.progressCount.textContent = "idle";
    els.progressPercent.textContent = "-";
    return;
  }
  const percent = Math.round((done * 100) / total);
  els.progressCount.textContent = `${done} / ${total} complete`;
  els.progressPercent.textContent = `${percent}%`;
}

function traceSignalLabel(item) {
  const signal = String(item.signal || "UNKNOWN").replace("_", " ");
  const target = item.target ? ` -> ${agentDisplayName(String(item.target))}` : "";
  return `${signal}${target}`;
}

function renderTraceList(container, items, emptyText, rowBuilder, limit = TRACE_ROW_LIMIT) {
  container.innerHTML = "";
  if (!items.length || limit <= 0) {
    const empty = document.createElement("p");
    empty.className = "trace-empty";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  for (const item of items.slice(-limit)) {
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
  const limit = state.traceVisible ? TRACE_ROW_LIMIT : 0;
  els.traceAgentCount.textContent = String(agents.length);
  els.tracePacketCount.textContent = String(packets.length);
  renderTraceList(els.traceAgentList, agents, state.traceVisible ? "No handoffs or terminal signals yet." : "Open Trace to view handoffs and terminal signals.", (row, item) => {
    appendTraceText(row, "trace-kicker", agentDisplayName(String(item.agent || "unknown")));
    appendTraceText(row, "trace-title", traceSignalLabel(item));
    appendTraceText(row, "trace-summary", item.summary || `message #${item.message_id ?? "-"}`);
  }, limit);
  renderTraceList(els.tracePacketList, packets, state.traceVisible ? "No thought packets captured yet." : "Open Trace to view packet trace.", (row, item) => {
    appendTraceText(row, "trace-kicker", `${agentDisplayName(String(item.agent || "unknown"))} ${item.stance || ""}`.trim());
    appendTraceText(row, "trace-title", String(item.signal || "UNKNOWN").replace("_", " "));
    appendTraceText(
      row,
      "trace-summary",
      `${item.observed_count || 0} observed / ${item.risk_count || 0} risks${item.next_action ? ` - ${item.next_action}` : ""}`,
    );
  }, limit);
}

/* ---------- session apply ---------- */

function selectedSkillItems() {
  return state.skills.filter((skill) => state.selectedSkills.includes(skill.id));
}

function skillAgentLabel(skill) {
  const agents = Array.isArray(skill.agents) ? skill.agents : [];
  if (agents.includes("claude") && agents.includes("codex")) return "Claude + Codex";
  if (agents.includes("claude")) return "Claude only";
  if (agents.includes("codex")) return "Codex only";
  return "Check support";
}

function renderSkills() {
  const selected = selectedSkillItems();
  els.selectedSkills.replaceChildren();
  els.selectedSkills.classList.toggle("hidden", !selected.length);
  for (const skill of selected) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "skill-chip";
    chip.textContent = `${skill.name} ×`;
    chip.title = `Remove ${skill.name}`;
    chip.addEventListener("click", () => {
      state.selectedSkills = state.selectedSkills.filter((id) => id !== skill.id);
      renderSkills();
    });
    els.selectedSkills.appendChild(chip);
  }
  els.skillsFilters.replaceChildren();
  const categories = ["All", ...new Set(state.skills.map((skill) => skill.category))];
  for (const category of categories) {
    const filter = document.createElement("button");
    filter.type = "button";
    filter.className = "skill-filter";
    filter.textContent = category;
    filter.setAttribute("aria-pressed", String(state.skillsFilter === category));
    filter.addEventListener("click", () => { state.skillsFilter = category; renderSkills(); });
    els.skillsFilters.appendChild(filter);
  }
  const query = els.skillsSearch.value.trim().toLowerCase();
  const visible = state.skills.filter((skill) => {
    const matchesFilter = state.skillsFilter === "All" || skill.category === state.skillsFilter;
    const text = `${skill.name} ${skill.summary} ${skill.source} ${skillAgentLabel(skill)}`.toLowerCase();
    return matchesFilter && (!query || text.includes(query));
  });
  els.skillsList.replaceChildren();
  for (const skill of visible) {
    const row = document.createElement("button");
    row.type = "button";
    const active = state.selectedSkills.includes(skill.id);
    row.className = `skill-row${active ? " active" : ""}`;
    const copy = document.createElement("span");
    const name = document.createElement("strong");
    const summary = document.createElement("small");
    const meta = document.createElement("small");
    const action = document.createElement("em");
    const agentLabel = skillAgentLabel(skill);
    name.textContent = skill.name;
    summary.textContent = `${skill.source} · ${skill.summary}`;
    meta.className = agentLabel.includes("only") || agentLabel === "Check support" ? "skill-compat warning" : "skill-compat";
    meta.textContent = agentLabel;
    action.textContent = active ? "Selected" : "Add";
    copy.append(name, summary, meta);
    row.append(copy, action);
    row.addEventListener("click", () => {
      if (active) state.selectedSkills = state.selectedSkills.filter((id) => id !== skill.id);
      else if (state.selectedSkills.length < 4) state.selectedSkills = [...state.selectedSkills, skill.id];
      else showError("Choose up to four skills for one prompt.");
      renderSkills();
      scheduleWorkbenchUiSave();
    });
    els.skillsList.appendChild(row);
  }
}

function setSkillsPanel(open) {
  els.skillsPanel.classList.toggle("hidden", !open);
  els.skillsButton.setAttribute("aria-expanded", String(open));
  if (open) els.skillsSearch.focus();
}

function mergeTranscript(existing, incoming) {
  const merged = new Map();
  for (const message of [...(existing || []), ...(incoming || [])]) {
    const key = message.id === undefined || message.id === null
      ? `${canonicalAgent(message.sender)}:${String(message.text || "")}`
      : String(message.id);
    merged.set(key, message);
  }
  return [...merged.values()].sort((left, right) => Number(left.id || 0) - Number(right.id || 0));
}

function applySession(data) {
  const incomingSessionId = String(data.session || "");
  if (state.sessionId && incomingSessionId && state.sessionId !== incomingSessionId) {
    resetSessionState();
  }
  state.sessionId = incomingSessionId;
  const shouldRestoreUi = Boolean(incomingSessionId) && state.uiRestoredSession !== incomingSessionId;
  const savedUi = shouldRestoreUi && data.workbench_ui && typeof data.workbench_ui === "object"
    ? data.workbench_ui
    : null;
  if (savedUi) {
    setTheme(savedUi.theme || state.theme);
    state.historyQuery = String(savedUi.history_query || "");
    els.historySearch.value = state.historyQuery;
    state.selectedSkills = Array.isArray(savedUi.selected_skills) ? savedUi.selected_skills : [];
    els.workbenchPrompt.value = String(savedUi.composer_draft || "");
    setFocusMode(Boolean(savedUi.focus_mode));
    setComposerExpanded(Boolean(savedUi.composer_expanded), { focus: false });
  }
  state.latestSession = data;
  state.transcript = mergeTranscript(state.transcript, data.transcript || []);
  state.historyLoaded = state.historyLoaded || Boolean(data.transcript_complete);
  state.projectCatalog = Array.isArray(data.project_catalog) ? data.project_catalog : [];
  state.modelSelection = data.model_selection || {};
  state.skills = Array.isArray(data.skills) ? data.skills : state.skills;
  state.selectedSkills = state.selectedSkills.filter((id) => state.skills.some((skill) => skill.id === id));
  renderSkills();
  els.topbarProject.textContent = data.project || "-";
  els.topbarSession.textContent = data.session || "-";
  const awaitingApproval = data.status === "awaiting_approval";
  const statusText = data.command_running ? "Working" : awaitingApproval ? "Approval needed" : data.status || "unknown";
  els.topbarStatus.textContent = statusText;
  els.topbarStatus.classList.toggle("muted-pill", Boolean(data.command_running) === false && !awaitingApproval && data.status !== "idle" && data.status !== "active");
  els.sessionButton.textContent = awaitingApproval ? "Approval" : data.command_running ? "Working" : "Session";

  state.commandRunning = Boolean(data.command_running);
  els.stopButton.classList.toggle("hidden", !state.commandRunning);
  state.agents = deriveLaneAgents(data);
  state.directAgents = uniqueAgents(data.direct_agents || []);
  els.roleCallButton.classList.toggle("hidden", !state.directAgents.includes("coordinator"));

  ensureLanes(state.agents);
  if (savedUi?.lanes) {
    for (const [agent, lane] of Object.entries(state.lanes)) {
      const savedLane = savedUi.lanes[agent];
      if (savedLane) lane.historyLimit = Number(savedLane.history_limit || LANE_MESSAGE_LIMIT);
    }
  }
  renderModelSelectors(state.modelSelection);
  renderProjects(data.projects || [], data.project || "");
  renderTokenBalances(data.token_usage, data.session_budget);

  const events = (data.events || []).filter((event) => Number(event.id || 0) > state.eventCursor);
  if (events.length) {
    state.eventCursor = events[events.length - 1].id;
    ingestEvents(events);
  }

  const transcript = state.transcript;
  renderActivePrompt(activePromptFromSession(data, transcript));
  renderLanes(laneTranscriptForSession(data, transcript));
  if (savedUi?.lanes) {
    window.requestAnimationFrame(() => {
      for (const [agent, lane] of Object.entries(state.lanes)) {
        const savedLane = savedUi.lanes[agent];
        if (!savedLane) continue;
        const scrollRange = Math.max(0, lane.stream.scrollHeight - lane.stream.clientHeight);
        lane.stream.scrollTop = savedLane.at_bottom ? lane.stream.scrollHeight : scrollRange * Number(savedLane.scroll_ratio || 0);
        updateLaneScrollState(agent);
      }
    });
  }
  if (shouldRestoreUi) state.uiRestoredSession = incomingSessionId;
  updatePreviewButton({ ...data, transcript });
  updateLaneActivity(data);
  renderCoordinator(data);
  renderApproval(data);
  renderAttention(data);
  renderResumePrompt(data);
  els.workArea.classList.toggle(
    "is-decision-docked",
    !els.approvalPanel.classList.contains("hidden")
      || !els.attentionPanel.classList.contains("hidden")
      || !els.resumePanel.classList.contains("hidden"),
  );
  renderProgress(data);
  state.trace = data.trace || {};
  renderTrace(state.trace);

  els.statRound.textContent = data.round === null || data.round === undefined ? "-" : String(data.round);
  els.statMode.textContent = data.collaboration_mode || "-";
  els.statNext.textContent = data.next_agent ? agentDisplayName(data.next_agent) : "-";
  els.statStatus.textContent = statusText;
  els.statStatus.classList.toggle("muted-pill", statusText !== "idle" && !data.command_running && !awaitingApproval);

  if (state.commandRunning) {
    setSendState(true, "Agents working...");
  } else if (awaitingApproval) {
    setSendState(false, "Proposal awaiting approval.");
  } else if (els.sendButton.disabled) {
    setSendState(false, "Latest response shown.");
  }
}

/* ---------- command completion ---------- */

function commandCompletionVisible() {
  return !els.commandCompletionPalette.classList.contains("hidden") && state.completionOptions.length > 0;
}

function hideCommandCompletions() {
  window.clearTimeout(state.completionTimer);
  state.completionTimer = null;
  state.completionOptions = [];
  state.completionIndex = 0;
  els.commandCompletionPalette.replaceChildren();
  els.commandCompletionPalette.classList.add("hidden");
  els.workbenchPrompt.setAttribute("aria-expanded", "false");
  els.workbenchPrompt.removeAttribute("aria-activedescendant");
}

function renderCommandCompletions(options) {
  state.completionOptions = Array.isArray(options) ? options : [];
  if (!state.completionOptions.length) {
    hideCommandCompletions();
    return;
  }
  state.completionIndex = Math.min(state.completionIndex, state.completionOptions.length - 1);
  els.commandCompletionPalette.replaceChildren();
  state.completionOptions.forEach((option, index) => {
    const button = document.createElement("button");
    const replacement = document.createElement("code");
    const label = document.createElement("span");
    button.type = "button";
    button.id = `command-completion-${index}`;
    button.className = `command-completion-option${index === state.completionIndex ? " is-selected" : ""}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(index === state.completionIndex));
    replacement.textContent = String(option.replacement || "");
    label.textContent = String(option.label || "");
    button.append(replacement, label);
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => selectCommandCompletion(index));
    els.commandCompletionPalette.appendChild(button);
  });
  els.commandCompletionPalette.classList.remove("hidden");
  els.workbenchPrompt.setAttribute("aria-expanded", "true");
  els.workbenchPrompt.setAttribute("aria-activedescendant", `command-completion-${state.completionIndex}`);
}

function moveCommandCompletion(delta) {
  if (!commandCompletionVisible()) return;
  const count = state.completionOptions.length;
  state.completionIndex = (state.completionIndex + delta + count) % count;
  renderCommandCompletions(state.completionOptions);
  document.getElementById(`command-completion-${state.completionIndex}`)?.scrollIntoView({ block: "nearest" });
}

function selectCommandCompletion(index = state.completionIndex) {
  const option = state.completionOptions[index];
  if (!option?.replacement) return false;
  els.workbenchPrompt.value = option.replacement;
  els.workbenchPrompt.setSelectionRange(els.workbenchPrompt.value.length, els.workbenchPrompt.value.length);
  hideCommandCompletions();
  scheduleWorkbenchUiSave();
  els.workbenchPrompt.focus();
  return true;
}

async function updateCommandCompletions() {
  const value = els.workbenchPrompt.value;
  const stripped = value.trimStart();
  const relevant = stripped.startsWith("/") || stripped.startsWith("@") || /^APPROVE(?:\s|$)/i.test(stripped);
  const request = ++state.completionRequest;
  if (!relevant || !state.connected) {
    hideCommandCompletions();
    return;
  }
  try {
    const data = await apiFetch(`/api/completions?q=${encodeURIComponent(value)}`);
    if (request !== state.completionRequest || value !== els.workbenchPrompt.value) return;
    state.completionIndex = 0;
    renderCommandCompletions(data.options || []);
  } catch {
    if (request === state.completionRequest) hideCommandCompletions();
  }
}

function scheduleCommandCompletions() {
  state.completionRequest += 1;
  window.clearTimeout(state.completionTimer);
  state.completionTimer = window.setTimeout(updateCommandCompletions, 80);
}

/* ---------- composer ---------- */

function setSendState(sending, message) {
  els.sendButton.disabled = sending;
  els.sendButton.textContent = sending ? "Working" : "Send";
  if (message !== undefined) {
    els.sendStatus.textContent = message;
  }
}

function setComposerExpanded(expanded, { focus = true } = {}) {
  state.composerExpanded = Boolean(expanded);
  els.composerCard.classList.toggle("is-expanded", state.composerExpanded);
  els.composerExpandButton.setAttribute("aria-expanded", String(state.composerExpanded));
  els.composerExpandButton.setAttribute(
    "aria-label",
    state.composerExpanded ? "Collapse prompt composer" : "Expand prompt composer",
  );
  els.composerExpandButton.title = state.composerExpanded ? "Collapse prompt composer" : "Expand prompt composer";
  els.composerExpandButton.querySelector("span").textContent = state.composerExpanded ? "v" : "^";
  if (focus) els.workbenchPrompt.focus();
  scheduleWorkbenchUiSave();
}

function flashSendStatus() {
  els.sendStatus.classList.remove("status-flash");
  void els.sendStatus.offsetWidth;
  els.sendStatus.classList.add("status-flash");
}

function currentTimeLabel() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

async function stopActiveCommand() {
  els.stopButton.disabled = true;
  els.stopButton.textContent = "Stopping";
  try {
    const data = await apiFetch("/api/command/stop", { method: "POST", body: "{}" });
    applySession(data);
    scheduleSessionPoll();
  } catch (error) {
    showError(friendlyFetchError(error));
  } finally {
    els.stopButton.disabled = false;
    els.stopButton.textContent = "Stop";
  }
}

async function resolveRecovery(action) {
  try {
    const data = await apiFetch("/api/session/recovery", {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    applySession(data);
    scheduleSessionPoll();
  } catch (error) {
    showError(friendlyFetchError(error));
  }
}

async function startNewTask() {
  els.newTaskButton.disabled = true;
  setSendState(false, "Starting new task...");
  flashSendStatus();
  try {
    const data = await apiFetch("/api/session/new-task", { method: "POST", body: "{}" });
    applySession(data);
    state.newTaskClicks += 1;
    setSendState(false, `New task ready · ${currentTimeLabel()} · ${state.newTaskClicks}`);
      flashSendStatus();
      showError("");
      els.workbenchPrompt.value = "";
      scheduleWorkbenchUiSave();
      renderActivePrompt("");
      els.workbenchPrompt.focus();
  } catch (error) {
    showError(friendlyFetchError(error));
  } finally {
    els.newTaskButton.disabled = false;
  }
}

async function sendPrompt(text) {
  const cleaned = text.trim();
  if (!cleaned || els.sendButton.disabled) {
    return false;
  }
  hideCommandCompletions();
  setSendState(true, "Sending to ChatBoks...");
  renderActivePrompt(cleaned);
  try {
    const data = await apiFetch("/api/command", {
      method: "POST",
      body: JSON.stringify({ text: cleaned, skills: state.selectedSkills }),
    });
    els.workbenchPrompt.value = "";
    applySession(data);
    scheduleWorkbenchUiSave();
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
    setApprovalStatus("No active decision is waiting for approval.", "error");
    return;
  }
  const note = els.approvalModification.value.trim();
  if (action === "MODIFY" && !note) {
    setApprovalStatus("Add a modification note before sending MODIFY.", "warning");
    els.approvalModification.focus();
    return;
  }
  const command = approvalCommandFor(action);
  const selectedBuilder = action.match(/^APPROVE\s+(.+)$/i)?.[1];
  const label = selectedBuilder
    ? `Build with ${agentDisplayName(selectedBuilder)}`
    : action === "APPROVE"
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

for (const swatch of document.querySelectorAll(".swatch")) {
  swatch.addEventListener("click", () => setTheme(swatch.dataset.setTheme));
}

els.focusButton.addEventListener("click", () => setFocusMode(!state.focusMode));
els.historySearch.addEventListener("input", () => {
  state.historyQuery = els.historySearch.value;
  for (const lane of Object.values(state.lanes)) {
    lane.historyLimit = LANE_MESSAGE_LIMIT;
  }
  renderLanes(state.transcript);
  scheduleWorkbenchUiSave();
});
els.workbenchPrompt.addEventListener("input", () => {
  scheduleWorkbenchUiSave();
  scheduleCommandCompletions();
});

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
els.composerExpandButton.addEventListener("click", () => setComposerExpanded(!state.composerExpanded));
els.skillsButton.addEventListener("click", () => setSkillsPanel(els.skillsPanel.classList.contains("hidden")));
els.skillsCloseButton.addEventListener("click", () => setSkillsPanel(false));
els.skillsSearch.addEventListener("input", renderSkills);
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
  if (commandCompletionVisible()) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      moveCommandCompletion(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey)) {
      event.preventDefault();
      selectCommandCompletion();
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      hideCommandCompletions();
      return;
    }
  }
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendPrompt(els.workbenchPrompt.value);
  }
});
els.workbenchPrompt.addEventListener("blur", () => {
  window.setTimeout(() => {
    if (!els.commandCompletionPalette.contains(document.activeElement)) hideCommandCompletions();
  }, 120);
});

els.newTaskButton.addEventListener("click", () => startNewTask());

els.projectButton.addEventListener("click", openProjectPicker);
els.railProjectsButton.addEventListener("click", openProjectPicker);
els.stopButton.addEventListener("click", stopActiveCommand);
els.resumeButton.addEventListener("click", () => resolveRecovery("continue"));
els.endTaskButton.addEventListener("click", () => resolveRecovery("end"));
els.projectDialogClose.addEventListener("click", closeProjectPicker);
els.projectDialogBackdrop.addEventListener("click", closeProjectPicker);
els.projectSearch.addEventListener("input", () => renderProjectPicker(els.projectSearch.value));
els.projectBrowseButton.addEventListener("click", () => browseProjectFolder().catch((error) => showError(friendlyFetchError(error))));
els.projectAddButton.addEventListener("click", addProject);
els.projectPath.addEventListener("keydown", (event) => {
  if (event.key === "Enter") addProject();
});
els.systemDrawerButton.addEventListener("click", () => {
  state.systemDrawerOpen = !state.systemDrawerOpen;
  syncSystemPanels();
});
els.claudeUpdateButton.addEventListener("click", updateClaude);
document.addEventListener("keydown", (event) => {
  // Escape unwinds one layer at a time, outermost first, so leaving focus
  // mode never also closes the picker or the drawer in the same keypress.
  if (event.key === "Escape") {
    if (state.composerExpanded) {
      setComposerExpanded(false);
    } else if (!els.projectDialog.classList.contains("hidden")) {
      closeProjectPicker();
    } else if (state.systemDrawerOpen) {
      state.systemDrawerOpen = false;
      syncSystemPanels();
    } else if (state.focusMode) {
      setFocusMode(false);
    }
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "p") {
    event.preventDefault();
    openProjectPicker();
  }
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
  renderTrace(state.trace);
});
els.systemDetailsButton.addEventListener("click", () => {
  state.systemDetailsVisible = !state.systemDetailsVisible;
  syncSystemPanels();
});
els.traceButton.addEventListener("click", () => {
  state.traceVisible = !state.traceVisible;
  syncSystemPanels();
  renderTrace(state.trace);
});

els.liveButton.addEventListener("click", () => {
  refreshSession().catch(() => {});
  refreshWorkbench().catch(() => {});
});

els.previewButton.addEventListener("click", async () => {
  if (!state.previewTarget) return;
  try {
    await window.pywebview.api.open_preview(state.previewTarget);
    setSendState(false, "Preview opened.");
  } catch (error) {
    showError(error?.message || "Could not open the preview.");
  }
});

/* ---------- boot ---------- */

let workbenchStarted = false;
const desktopMode = new URLSearchParams(window.location.search).has("desktop");

function syncSystemPanels() {
  els.systemDrawer.classList.toggle("hidden", !state.systemDrawerOpen);
  els.systemDrawerButton.setAttribute("aria-expanded", String(state.systemDrawerOpen));
  els.systemDrawerButton.classList.toggle("is-active", state.systemDrawerOpen);
  els.systemDetails.classList.toggle("hidden", !state.systemDetailsVisible);
  els.tracePanel.classList.toggle("hidden", !state.traceVisible);
  els.systemDetailsButton.setAttribute("aria-expanded", String(state.systemDetailsVisible));
  els.traceButton.setAttribute("aria-expanded", String(state.traceVisible));
  els.systemDetailsButton.textContent = state.systemDetailsVisible ? "Details" : "Show details";
  els.traceButton.textContent = state.traceVisible ? "Hide trace" : "Trace";
}

async function startWorkbench() {
  if (workbenchStarted) return;
  workbenchStarted = true;
  document.documentElement.dir = "ltr";
  loadSettings();
  try {
    const bootstrap = await window.pywebview?.api?.bootstrap?.();
    if (bootstrap?.bridgeUrl && bootstrap?.sessionToken) {
      state.bridgeUrl = bootstrap.bridgeUrl;
      state.token = bootstrap.sessionToken;
      els.bridgeUrl.value = state.bridgeUrl;
      els.token.value = state.token;
      saveSettings();
    } else if (desktopMode) {
      throw new Error("Desktop session was not supplied by the native app.");
    }
  } catch (error) {
    if (desktopMode) {
      renderOfflineWorkbench();
      setConnectionPanel(true);
      setConnectionState("Desktop session could not start.", "error");
      showError(error.message || "Desktop session could not start.");
      return;
    }
    // Browser and mobile clients continue through the explicit pairing flow.
  }
  setTheme(state.theme);
  setFocusMode(state.focusMode);
  if (state.token) {
    setConnectionState("Connecting to local Workbench...", "muted");
    connect().catch(() => setConnectionPanel(true));
  } else {
    renderOfflineWorkbench();
    setConnectionPanel(false);
    setConnectionState("No session token saved. Pair with a fresh desktop code.", "muted");
  }
}

async function updateClaude() {
  setConnectionBusy(els.claudeUpdateButton, true, "Updating...");
  try {
    await apiFetch("/api/claude/update", { method: "POST", body: "{}" });
    setSendState(false, "Claude update started. It will finish in the background.");
    showError("");
  } catch (error) {
    showError(friendlyFetchError(error));
  } finally {
    setConnectionBusy(els.claudeUpdateButton, false, "Updating...");
  }
}

async function startClaudeLogin() {
  try {
    await apiFetch("/api/claude/login", { method: "POST", body: "{}" });
    setSendState(false, "Claude sign-in opened in your browser. Finish there, then send a new task.");
    showError("");
  } catch (error) {
    showError(friendlyFetchError(error));
  }
}

async function updateCodex() {
  const laneButton = state.lanes.codex?.pane.querySelector(".claude-auth-button");
  if (laneButton) setConnectionBusy(laneButton, true, "Updating...");
  try {
    await apiFetch("/api/codex/update", { method: "POST", body: "{}" });
    setSendState(false, "Codex update started. It will finish in the background.");
    showError("");
  } catch (error) {
    showError(friendlyFetchError(error));
  } finally {
    if (laneButton) setConnectionBusy(laneButton, false, "Updating...");
  }
}

syncSystemPanels();
if (desktopMode) {
  window.addEventListener("pywebviewready", startWorkbench, { once: true });
  window.setTimeout(() => {
    if (!workbenchStarted) {
      renderOfflineWorkbench();
      setConnectionPanel(true);
      setConnectionState("Waiting for the desktop session timed out.", "error");
      showError("ChatBoks could not connect its desktop session. Close and reopen the app.");
    }
  }, 3000);
} else {
  window.setTimeout(startWorkbench, 0);
}
