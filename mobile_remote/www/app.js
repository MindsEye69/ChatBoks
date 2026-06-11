const storageKey = "chatboks-mobile-remote";
const defaultBridgeUrl = "";
const state = {
  eventCursor: 0,
  pollTimer: null,
  eventItems: [],
  commandEvents: [],
  commandActive: false,
  currentProject: "",
  eventStreams: {},
  commandStreams: {},
};

const els = {
  baseUrl: document.getElementById("baseUrl"),
  pairCode: document.getElementById("pairCode"),
  token: document.getElementById("token"),
  errorBox: document.getElementById("errorBox"),
  connectionPanel: document.getElementById("connectionPanel"),
  connectionToggle: document.getElementById("connectionToggleButton"),
  connectionCollapse: document.getElementById("connectionCollapseButton"),
  sessionPanel: document.getElementById("sessionPanel"),
  sessionToggle: document.getElementById("sessionToggleButton"),
  sessionCollapse: document.getElementById("sessionCollapseButton"),
  tokenPanel: document.getElementById("tokenPanel"),
  tokenToggle: document.getElementById("tokenToggleButton"),
  project: document.getElementById("projectSelect"),
  status: document.getElementById("statusValue"),
  nextAgent: document.getElementById("nextAgentValue"),
  task: document.getElementById("taskValue"),
  tokenLine: document.getElementById("tokenLine"),
  flowChain: document.getElementById("flowChain"),
  latestResponse: document.getElementById("latestResponse"),
  prompt: document.getElementById("promptInput"),
  transcript: document.getElementById("transcriptList"),
  transcriptPanel: document.getElementById("transcriptPanel"),
  events: document.getElementById("eventsList"),
  sendStatus: document.getElementById("sendStatus"),
  fullTranscript: document.getElementById("fullTranscriptButton"),
  copyLatest: document.getElementById("copyLatestButton"),
  refresh: document.getElementById("refreshButton"),
  save: document.getElementById("saveButton"),
  pair: document.getElementById("pairButton"),
  connect: document.getElementById("connectButton"),
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

function showError(message) {
  els.errorBox.textContent = message || "";
  els.errorBox.classList.toggle("hidden", !message);
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

function setSendState(isSending, message = "") {
  els.send.disabled = isSending;
  els.send.textContent = isSending ? "Sending" : "Send";
  els.sendStatus.textContent = message;
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

function updateKeyboardOffset() {
  if (!window.visualViewport) {
    document.documentElement.style.setProperty("--keyboard-offset", "0px");
    return;
  }
  const hiddenByKeyboard = Math.max(
    0,
    window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop,
  );
  document.documentElement.style.setProperty("--keyboard-offset", `${Math.round(hiddenByKeyboard)}px`);
}

function describeNetworkError(error) {
  const message = error && error.message ? error.message : String(error);
  if (message === "Failed to fetch" || error instanceof TypeError) {
    const url = els.baseUrl.value.trim() || "the bridge URL";
    return `Failed to fetch ${url}. Check that Tailscale is connected on the phone and the bridge URL is correct.`;
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
  saveSettings();
  return body;
}

function renderList(container, items) {
  container.innerHTML = "";
  for (const item of items) {
    const root = document.createElement("div");
    root.className = "item";
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

function isTokenUsageMessage(item) {
  return (item.sender || "").toLowerCase() === "system" && (item.text || "").trim().startsWith("session tokens:");
}

function visibleEvents(items) {
  return items.filter((item) => {
    if (isTokenUsageMessage(item)) {
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
  return visibleEvents(items).filter((item) => !isCommandProgressEvent(item));
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

function latestResponseGroup(items) {
  const lastUserIndex = items.reduce((latest, item, index) => {
    return (item.sender || "").toLowerCase() === "you" ? index : latest;
  }, -1);
  const candidates = lastUserIndex >= 0 ? items.slice(lastUserIndex + 1) : items;
  const group = candidates.filter((item) => item.sender && !isTokenUsageMessage(item));
  if (group.length) {
    return group;
  }
  return [...items]
    .reverse()
    .filter((item) => item.sender && (item.sender || "").toLowerCase() !== "you" && !isTokenUsageMessage(item))
    .slice(0, 1)
    .reverse();
}

function renderLatestResponse(items) {
  const commandEvents = visibleCommandEvents(state.commandEvents);
  const group = commandEvents.length ? commandEvents : latestResponseGroup(items);
  if (!group.length) {
    els.latestResponse.textContent = "-";
    return;
  }
  els.latestResponse.textContent = group
    .map((item) => `${(item.sender || "unknown").toUpperCase()}\n${item.text || ""}`.trim())
    .join("\n\n");
  els.latestResponse.scrollTop = els.latestResponse.scrollHeight;
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
  const blocked = ["blocked", "question", "proposal"].includes(status);
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
  const transcript = data.transcript || [];
  renderLatestResponse(transcript);
  renderList(els.transcript, transcript);
  const events = (data.events || []).filter((item) => Number(item.id || 0) > state.eventCursor);
  if (events.length) {
    state.eventCursor = events[events.length - 1].id;
    ingestEvents(events, state.eventItems, state.eventStreams, 80);
    if (state.commandActive || data.command_running) {
      ingestEvents(events, state.commandEvents, state.commandStreams, 40);
    }
  }
  renderList(els.events, visibleEvents(state.eventItems));
  renderLatestResponse(transcript);
  if (scrollLatest) {
    window.requestAnimationFrame(scrollLatestResponseIntoView);
  }
  if (data.command_running) {
    setSendState(false, "Waiting for agents...");
    scheduleRefreshPoll();
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
  if (state.pollTimer) {
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
    showError(describeNetworkError(error));
  }
}

async function refreshSession(options = {}) {
  try {
    const data = await apiFetch(`/api/session?cursor=${state.eventCursor}`);
    applySession(data, options);
    showError("");
  } catch (error) {
    showError(error.message || String(error));
    if (state.commandActive) {
      scheduleRefreshPoll();
    }
  }
}

async function sendPrompt(text) {
  const cleaned = text.trim();
  if (!cleaned || els.send.disabled) {
    return;
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
  } catch (error) {
    const detail = describeNetworkError(error);
    setSendState(false, `Send failed: ${detail}`);
    showError(detail);
    if (isAuthError(error)) {
      setConnectionCollapsed(false);
    }
  }
}

els.save.addEventListener("click", () => {
  saveSettings();
  showError("");
});

els.pair.addEventListener("click", async () => {
  try {
    saveSettings();
    const data = await pairDevice();
    showError(`Paired successfully. Session token valid for ${data.ttl_seconds || "a limited time"} seconds.`);
    setConnectionCollapsed(true);
  } catch (error) {
    showError(describeNetworkError(error));
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
    state.commandEvents = [];
    state.commandStreams = {};
    state.commandActive = false;
    await refreshSession();
    setConnectionCollapsed(true);
  } catch (error) {
    showError(describeNetworkError(error));
  }
});

els.refresh.addEventListener("click", refreshSession);
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

els.send.addEventListener("click", () => {
  saveSettings();
  sendPrompt(els.prompt.value);
});

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", updateKeyboardOffset);
  window.visualViewport.addEventListener("scroll", updateKeyboardOffset);
}
window.addEventListener("resize", updateKeyboardOffset);
updateKeyboardOffset();

loadSettings();
