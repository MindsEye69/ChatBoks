const storageKey = "chatboks-mobile-remote";
const state = {
  eventCursor: 0,
};

const els = {
  baseUrl: document.getElementById("baseUrl"),
  pairCode: document.getElementById("pairCode"),
  token: document.getElementById("token"),
  errorBox: document.getElementById("errorBox"),
  status: document.getElementById("statusValue"),
  nextAgent: document.getElementById("nextAgentValue"),
  task: document.getElementById("taskValue"),
  tokenLine: document.getElementById("tokenLine"),
  prompt: document.getElementById("promptInput"),
  transcript: document.getElementById("transcriptList"),
  events: document.getElementById("eventsList"),
  refresh: document.getElementById("refreshButton"),
  save: document.getElementById("saveButton"),
  pair: document.getElementById("pairButton"),
  connect: document.getElementById("connectButton"),
  send: document.getElementById("sendButton"),
};

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{}");
    els.baseUrl.value = saved.baseUrl || "";
    els.token.value = saved.token || "";
  } catch {
    // ignore malformed local data
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

async function refreshSession() {
  try {
    const data = await apiFetch(`/api/session?cursor=${state.eventCursor}`);
    els.status.textContent = data.status || "-";
    els.nextAgent.textContent = data.next_agent || "-";
    els.task.textContent = data.active_task || "-";
    els.tokenLine.textContent = data.token_line || "";
    renderList(els.transcript, data.transcript || []);
    const events = data.events || [];
    if (events.length) {
      state.eventCursor = events[events.length - 1].id;
    }
    renderList(els.events, events);
    showError("");
  } catch (error) {
    showError(error.message || String(error));
  }
}

async function sendPrompt(text) {
  if (!text.trim()) {
    return;
  }
  try {
    await apiFetch("/api/command", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    els.prompt.value = "";
    await refreshSession();
  } catch (error) {
    showError(error.message || String(error));
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
  } catch (error) {
    showError(error.message || String(error));
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
  } catch (error) {
    showError(error.message || String(error));
  }
});

els.refresh.addEventListener("click", refreshSession);

els.send.addEventListener("click", () => {
  saveSettings();
  sendPrompt(els.prompt.value);
});

for (const button of document.querySelectorAll(".quick-action")) {
  button.addEventListener("click", () => {
    saveSettings();
    sendPrompt(button.dataset.command || "");
  });
}

loadSettings();
