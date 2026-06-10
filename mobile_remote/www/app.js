const storageKey = "chatboks-mobile-remote";
const defaultBridgeUrl = "http://warhammer.tail169679.ts.net:8765";
const state = {
  eventCursor: 0,
  pollTimer: null,
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
    return `Failed to fetch ${currentBaseUrl()}. Check that Tailscale is connected on the phone and the bridge URL is exactly ${defaultBridgeUrl}.`;
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
    throw new Error(body.error || `Request failed (${response.status})`);
  }
  return body;
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
  return items.filter((item) => !isTokenUsageMessage(item));
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
  const group = latestResponseGroup(items);
  if (!group.length) {
    els.latestResponse.textContent = "-";
    return;
  }
  els.latestResponse.textContent = group
    .map((item) => `${(item.sender || "unknown").toUpperCase()}\n${item.text || ""}`.trim())
    .join("\n\n");
}

function renderProjects(projects = [], currentProject = "") {
  const selected = currentProject || els.project.value;
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
  if (data.status) {
    setConnectionCollapsed(true);
    setSessionCollapsed(true);
  }
  renderProjects(data.projects || [], data.project || "");
  els.nextAgent.textContent = data.next_agent || "-";
  els.task.textContent = data.active_task || "-";
  els.tokenLine.textContent = data.token_line || "";
  const transcript = data.transcript || [];
  renderLatestResponse(transcript);
  renderList(els.transcript, transcript);
  const events = data.events || [];
  if (events.length) {
    state.eventCursor = events[events.length - 1].id;
  }
  renderList(els.events, visibleEvents(events));
  if (scrollLatest) {
    window.requestAnimationFrame(scrollLatestResponseIntoView);
  }
  if (data.command_running) {
    setSendState(false, "Waiting for agents...");
    scheduleRefreshPoll();
  } else {
    stopPolling();
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
    await refreshSession({ scrollLatest: true });
  }, 3000);
}

async function switchProject(project) {
  if (!project) {
    return;
  }
  setSendState(true, `Switching to ${project}...`);
  try {
    state.eventCursor = 0;
    const data = await apiFetch("/api/project", {
      method: "POST",
      body: JSON.stringify({ project }),
    });
    applySession(data, { scrollLatest: true });
    setSendState(false, `Project switched to ${project}.`);
    clearSendStatusSoon();
  } catch (error) {
    setSendState(false, "Project switch failed.");
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
  }
}

async function sendPrompt(text) {
  const cleaned = text.trim();
  if (!cleaned || els.send.disabled) {
    return;
  }
  setSendState(true, "Sending to ChatBoks...");
  try {
    const data = await apiFetch("/api/command", {
      method: "POST",
      body: JSON.stringify({ text: cleaned }),
    });
    els.prompt.value = "";
    applySession(data, { scrollLatest: true });
    if (data.command_running) {
      setSendState(false, "Sent. Waiting for agents...");
    } else {
      setSendState(false, "Sent. Latest response shown.");
      clearSendStatusSoon();
    }
  } catch (error) {
    setSendState(false, "Send failed.");
    showError(describeNetworkError(error));
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
