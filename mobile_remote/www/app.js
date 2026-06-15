const storageKey = "chatboks-mobile-remote";
const defaultBridgeUrl = "";
const state = {
  eventCursor: 0,
  pollTimer: null,
  eventItems: [],
  systemItems: [],
  commandEvents: [],
  commandActive: false,
  currentProject: "",
  eventStreams: {},
  commandStreams: {},
  connectionFailures: 0,
  authBlocked: false,
  approvalActive: false,
  approvalProposalId: "",
  approvalSubmitting: false,
};

const els = {
  baseUrl: document.getElementById("baseUrl"),
  pairCode: document.getElementById("pairCode"),
  token: document.getElementById("token"),
  errorBox: document.getElementById("errorBox"),
  connectionState: document.getElementById("connectionState"),
  connectionPanel: document.getElementById("connectionPanel"),
  connectionToggle: document.getElementById("connectionToggleButton"),
  connectionCollapse: document.getElementById("connectionCollapseButton"),
  sessionPanel: document.getElementById("sessionPanel"),
  sessionToggle: document.getElementById("sessionToggleButton"),
  sessionCollapse: document.getElementById("sessionCollapseButton"),
  tokenPanel: document.getElementById("tokenPanel"),
  tokenToggle: document.getElementById("tokenToggleButton"),
  traceAgentCount: document.getElementById("traceAgentCount"),
  traceAgentList: document.getElementById("traceAgentList"),
  tracePacketCount: document.getElementById("tracePacketCount"),
  tracePacketList: document.getElementById("tracePacketList"),
  project: document.getElementById("projectSelect"),
  status: document.getElementById("statusValue"),
  nextAgent: document.getElementById("nextAgentValue"),
  task: document.getElementById("taskValue"),
  tokenLine: document.getElementById("tokenLine"),
  flowChain: document.getElementById("flowChain"),
  latestResponse: document.getElementById("latestResponse"),
  approvalPanel: document.getElementById("approvalPanel"),
  approvalMeta: document.getElementById("approvalMeta"),
  approvalSummary: document.getElementById("approvalSummary"),
  approvalEstimate: document.getElementById("approvalEstimate"),
  approvalRaw: document.getElementById("approvalRaw"),
  approvalModification: document.getElementById("approvalModification"),
  approvalStatus: document.getElementById("approvalStatus"),
  approve: document.getElementById("approveButton"),
  modify: document.getElementById("modifyButton"),
  reject: document.getElementById("rejectButton"),
  prompt: document.getElementById("promptInput"),
  transcript: document.getElementById("transcriptList"),
  transcriptPanel: document.getElementById("transcriptPanel"),
  systemFeed: document.getElementById("systemList"),
  systemPanel: document.getElementById("systemPanel"),
  systemCollapse: document.getElementById("systemCollapseButton"),
  systemToast: document.getElementById("systemToast"),
  eventsPanel: document.getElementById("eventsPanel"),
  eventsCollapse: document.getElementById("eventsCollapseButton"),
  events: document.getElementById("eventsList"),
  sendStatus: document.getElementById("sendStatus"),
  systemFeedButton: document.getElementById("systemFeedButton"),
  bridgeEventsButton: document.getElementById("bridgeEventsButton"),
  fullTranscript: document.getElementById("fullTranscriptButton"),
  copyLatest: document.getElementById("copyLatestButton"),
  refresh: document.getElementById("refreshButton"),
  save: document.getElementById("saveButton"),
  pair: document.getElementById("pairButton"),
  connect: document.getElementById("connectButton"),
  forget: document.getElementById("forgetButton"),
  send: document.getElementById("sendButton"),
};

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{}");
    els.baseUrl.value = saved.baseUrl || defaultBridgeUrl;
    els.token.value = saved.token || "";
  } catch {
    els.baseUrl.value = defaultBridgeUrl;
  }
}

function saveSettings() {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      baseUrl: els.baseUrl.value.trim(),
      token: els.token.value.trim(),
    }),
  );
}

function showError(message, tone = "error") {
  els.errorBox.textContent = message || "";
  els.errorBox.classList.toggle("hidden", !message);
  els.errorBox.classList.toggle("success", Boolean(message) && tone === "success");
}

function setConnectionState(message, tone = "muted") {
  els.connectionState.textContent = message;
  els.connectionState.classList.toggle("muted", tone === "muted");
  els.connectionState.classList.toggle("success", tone === "success");
  els.connectionState.classList.toggle("warning", tone === "warning");
  els.connectionState.classList.toggle("error-state", tone === "error");
}

function setConnectionCollapsed(collapsed) {
  els.connectionPanel.classList.toggle("hidden", collapsed);
  els.connectionToggle.classList.toggle("active", !collapsed);
}

function setSessionCollapsed(collapsed) {
  els.sessionPanel.classList.toggle("hidden", collapsed);
  els.sessionToggle.classList.toggle("active", !collapsed);
}

function setTokenCollapsed(collapsed) {
  els.tokenPanel.classList.toggle("hidden", collapsed);
  els.tokenToggle.classList.toggle("active", !collapsed);
}

function setSystemPanelCollapsed(collapsed) {
  els.systemPanel.classList.toggle("hidden", collapsed);
  els.systemFeedButton.classList.toggle("active", !collapsed);
  renderSystemControls();
  renderSystemToast();
}

function setEventsPanelCollapsed(collapsed) {
  els.eventsPanel.classList.toggle("hidden", collapsed);
  els.bridgeEventsButton.classList.toggle("active", !collapsed);
  renderEventsControls();
}

function setSendState(isSending, message = "") {
  els.send.disabled = isSending;
  els.send.textContent = isSending ? "Sending" : "Send";
  els.sendStatus.textContent = message;
}

function setRefreshState(isRefreshing, label = "") {
  els.refresh.disabled = isRefreshing;
  els.refresh.setAttribute("aria-busy", isRefreshing ? "true" : "false");
  els.refresh.textContent = label || (isRefreshing ? "Refreshing" : "Refresh");
  if (!isRefreshing && label) {
    window.setTimeout(() => {
      if (!els.refresh.disabled && els.refresh.textContent === label) {
        els.refresh.textContent = "Refresh";
      }
    }, 1500);
  }
}

function clearSendStatusSoon() {
  window.setTimeout(() => {
    if (!els.send.disabled) {
      els.sendStatus.textContent = "";
    }
  }, 3000);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function isTextInputFocused() {
  const active = document.activeElement;
  if (!active) {
    return false;
  }
  const tag = active.tagName ? active.tagName.toLowerCase() : "";
  return tag === "input" || tag === "textarea" || active.isContentEditable;
}

function updateKeyboardOffset() {
  if (!window.visualViewport) {
    document.documentElement.style.setProperty("--keyboard-offset", "0px");
    updateComposerReservedHeight();
    return;
  }
  const hiddenByKeyboard = isTextInputFocused()
    ? Math.max(
        0,
        window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop,
      )
    : 0;
  document.documentElement.style.setProperty("--keyboard-offset", `${Math.round(hiddenByKeyboard)}px`);
  updateComposerReservedHeight();
}

function updateComposerReservedHeight() {
  const composer = document.querySelector(".composer");
  if (!composer) {
    return;
  }
  const height = Math.ceil(composer.getBoundingClientRect().height);
  document.documentElement.style.setProperty("--composer-reserved-height", `${height}px`);
}

function describeNetworkError(error) {
  const message = error && error.message ? error.message : String(error);
  if (isAuthError(error)) {
    return "Session token was rejected or expired. Use Forget token, then pair with a fresh desktop code.";
  }
  if (message.includes("Expecting value: line 1 column 1")) {
    return "The bridge returned an empty or non-JSON response. Refreshing the session usually shows whether the command completed.";
  }
  if (message === "Failed to fetch" || error instanceof TypeError) {
    const url = els.baseUrl.value.trim() || "the bridge URL";
    return `Could not reach the bridge at ${url}. Confirm the bridge is running, Tailscale is connected, and the URL matches the desktop bridge console.`;
  }
  return message;
}

function currentBaseUrl() {
  const value = els.baseUrl.value.trim().replace(/\/+$/, "");
  if (!value) {
    throw new Error("Enter the private bridge URL first.");
  }
  return value;
}

function currentToken() {
  const value = els.token.value.trim();
  if (!value) {
    throw new Error("Pair with the desktop bridge first, or enter a saved session token.");
  }
  return value;
}

function currentPairCode() {
  const value = els.pairCode.value.trim().toUpperCase();
  if (!value) {
    throw new Error("Enter the one-time pairing code from the desktop bridge.");
  }
  return value;
}

async function apiFetch(path, options = {}) {
  const baseUrl = currentBaseUrl();
  const token = currentToken();
  const response = await fetch(baseUrl + path, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
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

function isAuthError(error) {
  const message = error && error.message ? error.message : "";
  return error && (error.status === 401 || error.status === 403 || message.toLowerCase().includes("token"));
}

async function pairDevice() {
  const baseUrl = currentBaseUrl();
  const pairCode = currentPairCode();
  setConnectionState("Pairing with desktop bridge...", "warning");
  const response = await fetch(baseUrl + "/api/pair", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ pair_code: pairCode }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `Pairing failed (${response.status})`);
  }
  els.token.value = body.session_token || "";
  els.pairCode.value = "";
  state.connectionFailures = 0;
  state.authBlocked = false;
  setConnectionState("Paired. Connecting to session...", "success");
  saveSettings();
  return body;
}

function forgetSessionToken() {
  els.token.value = "";
  els.pairCode.value = "";
  saveSettings();
  stopPolling();
  state.eventCursor = 0;
  state.eventItems = [];
  state.eventStreams = {};
  state.systemItems = [];
  state.commandEvents = [];
  state.commandStreams = {};
  state.commandActive = false;
  state.connectionFailures = 0;
  state.authBlocked = false;
  els.status.textContent = "offline";
  els.nextAgent.textContent = "-";
  els.task.textContent = "-";
  els.tokenLine.textContent = "";
  els.project.innerHTML = "";
  renderApproval({ status: "idle", proposal: null });
  renderTrace({});
  renderLatestResponse([]);
  renderList(els.transcript, []);
  renderList(els.systemFeed, []);
  renderList(els.events, []);
  renderSystemControls();
  renderSystemToast();
  setSendState(false, "Session token forgotten.");
  setConnectionCollapsed(false);
  setConnectionState("No session token saved. Pair with a fresh desktop code.", "muted");
  showError("Session token forgotten. Pair again with a fresh desktop code before reconnecting.", "success");
}

function renderList(container, items) {
  container.innerHTML = "";
  for (const item of items) {
    const root = document.createElement("div");
    root.className = `item ${senderClass(item.sender)}`.trim();
    const sender = document.createElement("div");
    sender.className = "item-sender";
    sender.textContent = item.sender || "unknown";
    const text = document.createElement("div");
    text.className = "item-text";
    text.textContent = item.text || "";
    root.appendChild(sender);
    root.appendChild(text);
    container.appendChild(root);
  }
}

function senderClass(sender) {
  const normalized = (sender || "unknown").toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
  return `sender-${normalized}`;
}

function isTokenUsageMessage(item) {
  return (item.sender || "").toLowerCase() === "system" && (item.text || "").trim().startsWith("session tokens:");
}

function isSystemMessage(item) {
  return (item.sender || "").toLowerCase() === "system";
}

function isVisibleTranscriptMessage(item) {
  return item.sender && !isTokenUsageMessage(item) && !isSystemMessage(item);
}

function isSystemFeedMessage(item) {
  const kind = item.kind || "";
  return isSystemMessage(item) && !isTokenUsageMessage(item) && !kind.startsWith("message_");
}

function visibleTranscript(items) {
  return items.filter(isVisibleTranscriptMessage);
}

function visibleEvents(items) {
  return items.filter((item) => {
    if (isTokenUsageMessage(item)) {
      return false;
    }
    if (isSystemMessage(item)) {
      return false;
    }
    if ((item.kind || "") === "message_stream" && !(item.text || "")) {
      return false;
    }
    return !["message_stream_start", "message_delta", "message_stream_finish"].includes(item.kind || "");
  });
}

function isCommandProgressEvent(item) {
  const sender = (item.sender || "").toLowerCase();
  const text = (item.text || "").trim();
  return sender === "system" && (text === "Command accepted. Waiting for agents." || text.startsWith("session tokens:"));
}

function visibleCommandEvents(items) {
  return visibleEvents(items).filter((item) => !isCommandProgressEvent(item) && isAgentResponseEvent(item));
}

function isAgentResponseEvent(item) {
  const kind = item.kind || "";
  if (!item.sender || isSystemMessage(item) || isTokenUsageMessage(item)) {
    return false;
  }
  if ((item.sender || "").toLowerCase() === "you") {
    return false;
  }
  if (kind === "message_stream") {
    return Boolean((item.text || "").trim());
  }
  return kind === "message";
}

function streamKey(item) {
  return (item.sender || "unknown").toLowerCase();
}

function appendStreamText(target, event, activeStreams) {
  const key = streamKey(event);
  let active = activeStreams[key];
  if (!active) {
    active = {
      id: event.id,
      kind: "message_stream",
      sender: event.sender || "unknown",
      text: "",
      streaming: true,
    };
    target.push(active);
    activeStreams[key] = active;
  }
  active.id = event.id;
  active.text += event.text || "";
}

function applyEventToList(target, event, activeStreams) {
  const kind = event.kind || "";
  const key = streamKey(event);
  if (kind === "message_stream_start") {
    activeStreams[key] = {
      id: event.id,
      kind: "message_stream",
      sender: event.sender || "unknown",
      text: "",
      streaming: true,
    };
    target.push(activeStreams[key]);
    return;
  }
  if (kind === "message_delta") {
    appendStreamText(target, event, activeStreams);
    return;
  }
  if (kind === "message_stream_finish") {
    if (activeStreams[key]) {
      activeStreams[key].id = event.id;
      activeStreams[key].streaming = false;
      delete activeStreams[key];
    }
    return;
  }
  target.push(event);
}

function ingestEvents(events, target, activeStreams, limit) {
  for (const event of events) {
    applyEventToList(target, event, activeStreams);
  }
  if (target.length > limit) {
    target.splice(0, target.length - limit);
  }
}

function ingestSystemEvents(events) {
  for (const event of events) {
    if (isSystemFeedMessage(event)) {
      state.systemItems.push(event);
    }
  }
  if (state.systemItems.length > 80) {
    state.systemItems.splice(0, state.systemItems.length - 80);
  }
}

function latestResponseGroup(items) {
  const lastUserIndex = items.reduce((latest, item, index) => {
    return (item.sender || "").toLowerCase() === "you" ? index : latest;
  }, -1);
  const candidates = lastUserIndex >= 0 ? items.slice(lastUserIndex + 1) : items;
  const group = candidates.filter((item) => item.sender && !isTokenUsageMessage(item) && !isSystemMessage(item));
  if (group.length) {
    return group;
  }
  return [...items]
    .reverse()
    .filter(
      (item) =>
        item.sender &&
        (item.sender || "").toLowerCase() !== "you" &&
        !isTokenUsageMessage(item) &&
        !isSystemMessage(item),
    )
    .slice(0, 1)
    .reverse();
}

function renderSystemToast() {
  const latest = state.systemItems[state.systemItems.length - 1];
  const systemVisible = !els.systemPanel.classList.contains("hidden");
  els.systemToast.innerHTML = "";
  els.systemToast.classList.toggle("hidden", !latest || !systemVisible);
  if (!latest || !systemVisible) {
    updateComposerReservedHeight();
    return;
  }
  const meta = document.createElement("div");
  meta.className = "system-toast-meta";
  meta.textContent = latest.timestamp ? `System ${latest.timestamp}` : "System";
  const text = document.createElement("div");
  text.className = "system-toast-text";
  text.textContent = latest.text || "";
  els.systemToast.appendChild(meta);
  els.systemToast.appendChild(text);
  updateComposerReservedHeight();
}

function renderSystemControls() {
  const systemVisible = !els.systemPanel.classList.contains("hidden");
  els.systemFeedButton.classList.toggle("active", systemVisible);
  if (systemVisible) {
    els.systemFeedButton.textContent = "Hide system";
    return;
  }
  els.systemFeedButton.textContent = state.systemItems.length
    ? `System (${state.systemItems.length})`
    : "System";
}

function renderEventsControls() {
  const eventsVisible = !els.eventsPanel.classList.contains("hidden");
  const count = visibleEvents(state.eventItems).length;
  els.bridgeEventsButton.classList.toggle("active", eventsVisible);
  if (eventsVisible) {
    els.bridgeEventsButton.textContent = "Hide bridge";
    return;
  }
  els.bridgeEventsButton.textContent = count ? `Bridge (${count})` : "Bridge";
}

function renderLatestResponse(items) {
  const commandEvents = visibleCommandEvents(state.commandEvents);
  const group = commandEvents.length
    ? commandEvents
    : state.commandActive && state.commandEvents.length
      ? [{ sender: "status", text: "Waiting for agent response..." }]
      : latestResponseGroup(items);
  els.latestResponse.innerHTML = "";
  if (!group.length) {
    els.latestResponse.textContent = "-";
    return;
  }
  for (const item of group) {
    const root = document.createElement("div");
    root.className = `response-block ${senderClass(item.sender)}`.trim();
    const sender = document.createElement("div");
    sender.className = "response-sender";
    sender.textContent = item.sender || "unknown";
    const text = document.createElement("div");
    text.className = "response-text";
    text.textContent = item.text || "";
    root.appendChild(sender);
    root.appendChild(text);
    els.latestResponse.appendChild(root);
  }
  els.latestResponse.scrollTop = els.latestResponse.scrollHeight;
}

function criteriaGateResponseItems(data) {
  if (data.status !== "awaiting_criteria" || !data.criteria_gate) {
    return [];
  }
  const gate = data.criteria_gate;
  const reasons = Array.isArray(gate.reasons) && gate.reasons.length
    ? gate.reasons.join(", ")
    : "criteria review";
  const agents = Array.isArray(gate.agents) && gate.agents.length
    ? gate.agents.map(agentDisplayName).join(", ")
    : agentDisplayName(data.next_agent || "agent");
  const mode = gate.mode || data.collaboration_mode || "default";
  return [{
    sender: "approval",
    text: [
      "Acceptance criteria approval needed before agents run.",
      "",
      `Triggers: ${reasons}`,
      `Mode: ${mode}`,
      `Agents: ${agents}`,
      "",
      "Type APPROVE to run, MODIFY <criteria> to add detail, or REJECT to cancel.",
    ].join("\n"),
  }];
}

function renderProjects(projects = [], currentProject = "") {
  const selected = currentProject || els.project.value;
  state.currentProject = selected;
  els.project.innerHTML = "";
  for (const project of projects) {
    const option = document.createElement("option");
    option.value = project;
    option.textContent = project;
    option.selected = project === selected;
    els.project.appendChild(option);
  }
  if (!projects.length && selected) {
    const option = document.createElement("option");
    option.value = selected;
    option.textContent = selected;
    option.selected = true;
    els.project.appendChild(option);
  }
}

function flowSteps(data) {
  const status = data.status || "unknown";
  const nextAgent = data.next_agent || "you";
  const activeTask = data.active_task || "";
  const mode = data.collaboration_mode || data.mode || "default";
  const commandRunning = Boolean(data.command_running);
  const idle = ["idle", "awaiting_input"].includes(status);
  const blocked = ["blocked", "question", "proposal", "awaiting_approval", "awaiting_input"].includes(status);
  return [
    { label: "input", value: activeTask ? "prompt" : "ready", state: activeTask ? "done" : "active" },
    { label: "router", value: mode, state: activeTask ? "done" : "" },
    { label: "agent", value: nextAgent, state: commandRunning ? "active" : idle ? "" : "active" },
    { label: "signal", value: blocked ? status : commandRunning ? "working" : idle ? "complete" : status, state: blocked ? "blocked" : idle ? "done" : "active" },
    { label: "output", value: idle ? "shown" : "pending", state: idle ? "done" : "" },
  ];
}

function renderFlow(data) {
  els.flowChain.innerHTML = "";
  for (const step of flowSteps(data)) {
    const root = document.createElement("div");
    root.className = `flow-step ${step.state || ""}`.trim();
    const label = document.createElement("div");
    label.className = "flow-label";
    label.textContent = step.label;
    const value = document.createElement("div");
    value.className = "flow-value";
    value.textContent = step.value || "-";
    root.appendChild(label);
    root.appendChild(value);
    els.flowChain.appendChild(root);
  }
}

function traceSignalLabel(item) {
  const signal = String(item.signal || "UNKNOWN").replace("_", " ");
  const target = item.target ? ` -> ${agentDisplayName(String(item.target))}` : "";
  return `${signal}${target}`;
}

function agentDisplayName(agent) {
  const canonical = canonicalAgent(agent);
  if (canonical === "coordinator") {
    return "Coordinator";
  }
  if (canonical === "codex_spark") {
    return "Codex Spark";
  }
  return canonical
    .split(/[_-]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || "Agent";
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

function appendTraceText(row, className, text) {
  const node = document.createElement("div");
  node.className = className;
  node.textContent = text || "-";
  row.appendChild(node);
}

function renderTraceList(container, items, emptyText, rowBuilder) {
  container.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "trace-empty";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  for (const item of items.slice(-5)) {
    const row = document.createElement("div");
    row.className = "trace-row";
    rowBuilder(row, item);
    container.appendChild(row);
  }
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

function formatExecutionEstimate(estimate) {
  if (!estimate || typeof estimate !== "object") {
    return "Execution estimate unavailable.";
  }
  const parts = [];
  if (estimate.agent) {
    parts.push(`via ${agentDisplayName(estimate.agent)}`);
  }
  if (estimate.input_tokens !== undefined || estimate.output_tokens !== undefined) {
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
  els.approve.disabled = disabled;
  els.modify.disabled = disabled;
  els.reject.disabled = disabled;
  els.approvalModification.disabled = disabled;
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
    return;
  }
  const proposalId = String(proposal.id || `${proposal.proposed_by || "agent"}:${proposal.summary || ""}`);
  if (state.approvalProposalId !== proposalId) {
    els.approvalModification.value = "";
    setApprovalStatus("Choose an approval action.");
  }
  state.approvalActive = true;
  state.approvalProposalId = proposalId;
  els.approvalMeta.textContent = `${agentDisplayName(proposal.proposed_by)} proposal`;
  els.approvalSummary.textContent = proposal.summary || "Review proposal";
  els.approvalEstimate.textContent = formatExecutionEstimate(proposal.execution_estimate);
  els.approvalRaw.textContent = proposalRawText(proposal);
  setApprovalControls(false);
}

function scrollLatestResponseIntoView() {
  els.latestResponse.scrollIntoView({ behavior: "smooth", block: "start" });
}

function scrollTranscriptToLatest() {
  const latest = els.transcript.lastElementChild;
  if (latest) {
    latest.scrollIntoView({ behavior: "smooth", block: "end" });
  }
}

async function copyLatestResponse() {
  const text = els.latestResponse.textContent.trim();
  if (!text || text === "-") {
    setSendState(false, "No latest response to copy.");
    clearSendStatusSoon();
    return;
  }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.setAttribute("readonly", "");
      helper.className = "clipboard-helper";
      document.body.appendChild(helper);
      helper.select();
      document.execCommand("copy");
      document.body.removeChild(helper);
    }
    setSendState(false, "Latest response copied.");
  } catch (error) {
    showError(`Copy failed: ${error.message || error}`);
  }
  clearSendStatusSoon();
}

function applySession(data, { scrollLatest = false } = {}) {
  els.status.textContent = data.status || "-";
  renderProjects(data.projects || [], data.project || "");
  els.nextAgent.textContent = data.next_agent || "-";
  els.task.textContent = data.active_task || "-";
  els.tokenLine.textContent = data.token_line || "";
  renderFlow(data);
  renderApproval(data);
  renderTrace(data.trace || {});
  const transcript = data.transcript || [];
  const responseItems = criteriaGateResponseItems(data);
  renderLatestResponse(responseItems.length ? responseItems : transcript);
  renderList(els.transcript, visibleTranscript(transcript));
  const events = (data.events || []).filter((item) => Number(item.id || 0) > state.eventCursor);
  if (events.length) {
    state.eventCursor = events[events.length - 1].id;
    ingestEvents(events, state.eventItems, state.eventStreams, 80);
    ingestSystemEvents(events);
    if (state.commandActive || data.command_running) {
      ingestEvents(events, state.commandEvents, state.commandStreams, 40);
    }
  }
  renderList(els.events, visibleEvents(state.eventItems));
  renderList(els.systemFeed, state.systemItems);
  renderSystemControls();
  renderEventsControls();
  renderSystemToast();
  renderLatestResponse(responseItems.length ? responseItems : transcript);
  if (scrollLatest) {
    window.requestAnimationFrame(scrollLatestResponseIntoView);
  }
  if (data.command_running) {
    setSendState(false, "Waiting for agents...");
    scheduleRefreshPoll();
  } else if (data.status === "awaiting_approval") {
    setSendState(false, "Proposal awaiting approval.");
  } else {
    stopPolling();
    state.commandActive = false;
    if (els.sendStatus.textContent.includes("Waiting")) {
      setSendState(false, "Latest response shown.");
      clearSendStatusSoon();
    }
  }
}

function scheduleRefreshPoll() {
  if (state.pollTimer || state.authBlocked) {
    return;
  }
  state.pollTimer = window.setTimeout(async () => {
    state.pollTimer = null;
    await refreshSession({ scrollLatest: false });
  }, 3000);
}

async function switchProject(project) {
  if (!project) {
    return;
  }
  const previousProject = state.currentProject || els.project.value;
  setSendState(true, `Switching to ${project}...`);
  try {
    state.eventCursor = 0;
    state.commandEvents = [];
    state.commandStreams = {};
    state.commandActive = false;
    state.eventItems = [];
    state.eventStreams = {};
    state.systemItems = [];
    const data = await apiFetch("/api/project", {
      method: "POST",
      body: JSON.stringify({ project }),
    });
    applySession(data, { scrollLatest: true });
    setSendState(false, `Project switched to ${project}.`);
    clearSendStatusSoon();
  } catch (error) {
    setSendState(false, "Project switch failed.");
    renderProjects(Array.from(els.project.options).map((option) => option.value), previousProject);
    const detail = describeNetworkError(error);
    setConnectionState(detail, isAuthError(error) ? "error" : "warning");
    showError(detail);
  }
}

async function refreshSession(options = {}) {
  const showFeedback = options.feedback === true;
  if (showFeedback) {
    setRefreshState(true);
    setSendState(false, "Refreshing session...");
  }
  try {
    const data = await apiFetch(`/api/session?cursor=${state.eventCursor}`);
    state.connectionFailures = 0;
    state.authBlocked = false;
    applySession(data, options);
    setConnectionState("Connected to bridge.", "success");
    showError("");
    if (showFeedback) {
      setRefreshState(false, "Refreshed");
      setSendState(false, data.command_running ? "Refreshed. Agents still running..." : "Session refreshed.");
      if (!data.command_running) {
        clearSendStatusSoon();
      }
    }
    return true;
  } catch (error) {
    state.connectionFailures += 1;
    const detail = describeNetworkError(error);
    showError(detail);
    if (showFeedback) {
      setRefreshState(false, "Refresh failed");
      setSendState(false, `Refresh failed: ${detail}`);
    }
    if (isAuthError(error)) {
      state.authBlocked = true;
      stopPolling();
      setConnectionCollapsed(false);
      setConnectionState("Session token rejected. Pair again with a fresh code.", "error");
      return false;
    }
    setConnectionState(`Bridge unreachable. Retrying (${state.connectionFailures})...`, "warning");
    if (state.commandActive || els.token.value.trim()) {
      scheduleRefreshPoll();
    }
    return false;
  }
}

async function sendPrompt(text) {
  const cleaned = text.trim();
  if (!cleaned || els.send.disabled) {
    return false;
  }
  setSendState(true, "Sending to ChatBoks...");
  state.commandEvents = [];
  state.commandStreams = {};
  state.commandActive = true;
  try {
    const data = await apiFetch("/api/command", {
      method: "POST",
      body: JSON.stringify({ text: cleaned }),
    });
    els.prompt.value = "";
    applySession(data, { scrollLatest: false });
    if (data.command_running) {
      setSendState(false, "Sent. Waiting for agents...");
    } else {
      setSendState(false, "Sent. Latest response updated.");
      clearSendStatusSoon();
    }
    return true;
  } catch (error) {
    const detail = describeNetworkError(error);
    if (!isAuthError(error) && await refreshSession({ scrollLatest: false })) {
      setSendState(false, "Bridge response was unclear. Session refreshed.");
      clearSendStatusSoon();
      return false;
    }
    setSendState(false, `Send failed: ${detail}`);
    setConnectionState(detail, isAuthError(error) ? "error" : "warning");
    showError(detail);
    if (isAuthError(error)) {
      setConnectionCollapsed(false);
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
  const command = action === "MODIFY" ? `MODIFY ${note}` : action;
  const label = action === "APPROVE" ? "Approval" : action === "REJECT" ? "Rejection" : "Modification";
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

els.save.addEventListener("click", () => {
  saveSettings();
  setConnectionState(
    els.token.value.trim() ? "Saved. Tap Connect to verify the session." : "Bridge URL saved. Pair with a fresh desktop code.",
    "muted",
  );
  showError("");
});

els.pair.addEventListener("click", async () => {
  try {
    saveSettings();
    const data = await pairDevice();
    showError(`Paired successfully. Session token valid for ${data.ttl_seconds || "a limited time"} seconds.`, "success");
    if (await refreshSession()) {
      setConnectionCollapsed(true);
    }
  } catch (error) {
    const detail = describeNetworkError(error);
    setConnectionState(detail, "error");
    showError(detail);
  }
});

els.connect.addEventListener("click", async () => {
  try {
    saveSettings();
    if (!els.token.value.trim()) {
      await pairDevice();
    }
    state.eventCursor = 0;
    state.eventItems = [];
    state.eventStreams = {};
    state.systemItems = [];
    state.commandEvents = [];
    state.commandStreams = {};
    state.commandActive = false;
    state.connectionFailures = 0;
    state.authBlocked = false;
    setConnectionState("Connecting to bridge...", "warning");
    if (await refreshSession()) {
      setConnectionCollapsed(true);
    }
  } catch (error) {
    const detail = describeNetworkError(error);
    setConnectionState(detail, "error");
    showError(detail);
  }
});

els.forget.addEventListener("click", forgetSessionToken);

els.refresh.addEventListener("click", () => refreshSession({ feedback: true }));
els.connectionToggle.addEventListener("click", () => {
  setConnectionCollapsed(!els.connectionPanel.classList.contains("hidden"));
});
els.connectionCollapse.addEventListener("click", () => {
  setConnectionCollapsed(true);
});
els.sessionToggle.addEventListener("click", () => {
  setSessionCollapsed(!els.sessionPanel.classList.contains("hidden"));
});
els.sessionCollapse.addEventListener("click", () => {
  setSessionCollapsed(true);
});
els.tokenToggle.addEventListener("click", () => {
  setTokenCollapsed(!els.tokenPanel.classList.contains("hidden"));
});
els.systemFeedButton.addEventListener("click", () => {
  setSystemPanelCollapsed(!els.systemPanel.classList.contains("hidden"));
});
els.systemCollapse.addEventListener("click", () => {
  setSystemPanelCollapsed(true);
});
els.bridgeEventsButton.addEventListener("click", () => {
  setEventsPanelCollapsed(!els.eventsPanel.classList.contains("hidden"));
});
els.eventsCollapse.addEventListener("click", () => {
  setEventsPanelCollapsed(true);
});
els.copyLatest.addEventListener("click", copyLatestResponse);
els.fullTranscript.addEventListener("click", () => {
  const hidden = els.transcriptPanel.classList.toggle("hidden");
  els.fullTranscript.textContent = hidden ? "Full transcript" : "Hide transcript";
  if (!hidden) {
    window.requestAnimationFrame(scrollTranscriptToLatest);
  }
});
els.project.addEventListener("change", () => {
  switchProject(els.project.value);
});

for (const textField of [els.prompt, els.approvalModification]) {
  textField.addEventListener("focus", updateKeyboardOffset);
  textField.addEventListener("blur", () => window.setTimeout(updateKeyboardOffset, 0));
}

els.send.addEventListener("click", () => {
  saveSettings();
  sendPrompt(els.prompt.value);
});

els.approve.addEventListener("click", () => {
  submitApproval("APPROVE");
});

els.reject.addEventListener("click", () => {
  submitApproval("REJECT");
});

els.modify.addEventListener("click", () => {
  submitApproval("MODIFY");
});

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", updateKeyboardOffset);
  window.visualViewport.addEventListener("scroll", updateKeyboardOffset);
}
window.addEventListener("resize", updateKeyboardOffset);
if ("ResizeObserver" in window) {
  const composerObserver = new ResizeObserver(updateComposerReservedHeight);
  const composer = document.querySelector(".composer");
  if (composer) {
    composerObserver.observe(composer);
  }
}
updateKeyboardOffset();

loadSettings();
if (els.token.value.trim()) {
  setConnectionState("Saved session token found. Tap Connect to verify it.", "muted");
} else {
  setConnectionState("No session token saved. Pair with a fresh desktop code.", "muted");
}
