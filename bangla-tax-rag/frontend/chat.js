const state = {
  apiBaseUrl: "http://127.0.0.1:4849",
  apiKey: "",
  conversation: [],
  focusedProductIds: [],
  lastAnswerPlan: null,
  busy: false
};

const el = {
  messages: document.querySelector("#messages"),
  form: document.querySelector("#chatForm"),
  input: document.querySelector("#chatInput"),
  send: document.querySelector("#sendButton"),
  statusPill: document.querySelector("#statusPill"),
  statusText: document.querySelector("#statusText"),
  chips: document.querySelector("#chips")
};

init();

async function init() {
  await loadLocalConfig();
  bindEvents();
  addMessage(
    "assistant",
    "Ready. Ask about color variants, size availability, budget, stock, or matching accessories."
  );
  await checkHealth();
}

async function loadLocalConfig() {
  try {
    const response = await fetch("./config.local.json", { cache: "no-store" });
    if (!response.ok) return;
    const config = await response.json();
    if (config.apiBaseUrl) state.apiBaseUrl = String(config.apiBaseUrl).replace(/\/+$/, "");
    if (typeof config.apiKey === "string") state.apiKey = config.apiKey.trim();
  } catch (_error) {
    // Local config is optional.
  }
}

function bindEvents() {
  el.form.addEventListener("submit", event => {
    event.preventDefault();
    void sendMessage(el.input.value);
  });
  el.input.addEventListener("input", resizeInput);
  el.input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage(el.input.value);
    }
  });
  el.chips.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;
    el.input.value = button.textContent.trim();
    resizeInput();
    el.input.focus();
  });
}

async function checkHealth() {
  try {
    const response = await fetch(`${state.apiBaseUrl}/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    setStatus("ready", "Connected");
  } catch (error) {
    setStatus("error", "Offline");
    addMessage("assistant", `Backend connection failed: ${error.message}`);
  }
}

async function sendMessage(rawText) {
  const text = rawText.trim();
  if (!text || state.busy) return;
  state.busy = true;
  el.send.disabled = true;
  el.input.value = "";
  resizeInput();
  addMessage("user", text);

  const thinking = addMessage("assistant", "...");
  try {
    const payload = {
      question: text,
      top_k: 5,
      assistant_mode: "support",
      reply_style: "short",
      answer_engine: "deterministic",
      conversation_history: state.conversation.slice(-8),
      focused_product_ids: state.focusedProductIds,
      last_answer_plan: state.lastAnswerPlan
    };
    const response = await apiPost("/inventory/ask", payload);
    thinking.querySelector(".body").textContent = response.answer || "No answer returned.";
    renderMeta(thinking, response);

    state.conversation.push({ role: "user", content: text });
    state.conversation.push({ role: "assistant", content: response.answer || "" });
    state.lastAnswerPlan = response.answer_plan || null;
    const nextFocus = [
      ...(response.recommended_product_ids || []),
      ...(response.cross_sell_product_ids || [])
    ];
    state.focusedProductIds = Array.from(new Set(nextFocus)).slice(0, 8);
  } catch (error) {
    thinking.querySelector(".body").textContent = `Request failed: ${error.message}`;
  } finally {
    state.busy = false;
    el.send.disabled = false;
    el.input.focus();
  }
}

async function apiPost(path, payload) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload)
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const message = data?.detail?.message || data?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

function buildHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (state.apiKey) headers["X-API-Key"] = state.apiKey;
  return headers;
}

function addMessage(role, text) {
  const node = document.createElement("article");
  node.className = `message ${role}`;
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = text;
  node.appendChild(body);
  el.messages.appendChild(node);
  el.messages.scrollTop = el.messages.scrollHeight;
  return node;
}

function renderMeta(node, response) {
  const meta = document.createElement("div");
  meta.className = "meta";
  const intent = response?.answer_plan?.intent || "inventory";
  const language = response?.answer_plan?.preferences?.language;
  const ids = [
    ...(response?.recommended_product_ids || []),
    ...(response?.cross_sell_product_ids || [])
  ];
  const parts = [`intent: ${intent}`];
  if (language) parts.push(`language: ${language}`);
  if (ids.length) parts.push(`items: ${ids.slice(0, 3).join(", ")}`);
  meta.textContent = parts.join(" · ");
  node.appendChild(meta);
}

function setStatus(kind, text) {
  el.statusPill.classList.remove("ready", "error");
  if (kind) el.statusPill.classList.add(kind);
  el.statusText.textContent = text;
}

function resizeInput() {
  el.input.style.height = "auto";
  el.input.style.height = `${Math.min(el.input.scrollHeight, 160)}px`;
}
