const state = {
  apiBaseUrl: "http://127.0.0.1:4849",
  apiKey: "",
  conversation: [],
  focusedProductIds: [],
  lastAnswerPlan: null,
  busy: false,
  sessionId: "session-" + Math.random().toString(36).slice(2, 10),
  orderActive: false,
  awaitingOrderConfirm: false,
  pendingImageB64: null,
  pendingImageName: null,
};

const el = {
  messages: document.querySelector("#messages"),
  form: document.querySelector("#chatForm"),
  input: document.querySelector("#chatInput"),
  send: document.querySelector("#sendButton"),
  statusPill: document.querySelector("#statusPill"),
  statusText: document.querySelector("#statusText"),
  chips: document.querySelector("#chips"),
  imageInput: document.querySelector("#imageInput"),
  imagePreview: document.querySelector("#imagePreview"),
  clearImageBtn: document.querySelector("#clearImageBtn"),
  imageLabel: document.querySelector("#imageLabel"),
  orderStatusBar: document.querySelector("#orderStatusBar"),
  orderConfirmBar: document.querySelector("#orderConfirmBar"),
  confirmOrderBtn: document.querySelector("#confirmOrderBtn"),
  cancelOrderBtn: document.querySelector("#cancelOrderBtn"),
};

init();

async function init() {
  await loadLocalConfig();
  bindEvents();
  addMessage(
    "assistant",
    "Ready. Ask in Bangla, Banglish, or English about sarees, cosmetics, beauty products, bags, watches, shoes, panjabi, shirts, pants, perfumes, stock, size, budget, color variants, or matching items. You can also upload a product image to find similar items."
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
    void handleSubmit();
  });
  el.input.addEventListener("input", resizeInput);
  el.input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  });
  el.chips.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;
    el.input.value = button.textContent.trim();
    resizeInput();
    el.input.focus();
  });
  el.imageInput.addEventListener("change", handleImageSelect);
  el.clearImageBtn.addEventListener("click", clearImage);
  el.confirmOrderBtn.addEventListener("click", () => void sendMessage("yes"));
  el.cancelOrderBtn.addEventListener("click", () => void cancelOrder());
}

async function handleSubmit() {
  const text = el.input.value.trim();
  if (state.pendingImageB64) {
    await sendImageSearch(text);
  } else {
    await sendMessage(text);
  }
}

function handleImageSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const dataUrl = e.target.result;
    const b64 = dataUrl.split(",")[1];
    state.pendingImageB64 = b64;
    state.pendingImageName = file.name;
    el.imagePreview.src = dataUrl;
    el.imagePreview.style.display = "block";
    el.clearImageBtn.style.display = "inline";
    el.imageLabel.textContent = file.name.slice(0, 24) + (file.name.length > 24 ? "…" : "");
  };
  reader.readAsDataURL(file);
}

function clearImage() {
  state.pendingImageB64 = null;
  state.pendingImageName = null;
  el.imageInput.value = "";
  el.imagePreview.style.display = "none";
  el.imagePreview.src = "";
  el.clearImageBtn.style.display = "none";
  el.imageLabel.textContent = "";
}

async function sendImageSearch(queryText) {
  if (state.busy) return;
  state.busy = true;
  el.send.disabled = true;

  const displayText = queryText || "🖼 Image search";
  addMessage("user", displayText + (state.pendingImageName ? ` [${state.pendingImageName}]` : ""));
  const thinking = addMessage("assistant", "Searching by image...");

  try {
    const payload = {
      query_text: queryText || "",
      image_b64: state.pendingImageB64,
      top_k: 5,
    };
    const response = await apiPost("/inventory/image-search", payload);
    thinking.querySelector(".body").textContent = response.answer || "No similar items found.";
    renderImageMeta(thinking, response);
  } catch (error) {
    thinking.querySelector(".body").textContent = `Image search failed: ${error.message}`;
  } finally {
    clearImage();
    state.busy = false;
    el.send.disabled = false;
    el.input.value = "";
    resizeInput();
    el.input.focus();
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
    const answer = response.answer || "No answer returned.";
    thinking.querySelector(".body").textContent = answer;
    renderMeta(thinking, response);

    state.conversation.push({ role: "user", content: text });
    state.conversation.push({ role: "assistant", content: answer });
    state.lastAnswerPlan = response.answer_plan || null;
    const nextFocus = [
      ...(response.recommended_product_ids || []),
      ...(response.cross_sell_product_ids || [])
    ];
    state.focusedProductIds = Array.from(new Set(nextFocus)).slice(0, 8);

    detectOrderState(text, answer);
  } catch (error) {
    thinking.querySelector(".body").textContent = `Request failed: ${error.message}`;
  } finally {
    state.busy = false;
    el.send.disabled = false;
    el.input.focus();
  }
}

function detectOrderState(userText, botAnswer) {
  const orderKeywords = ["order korte", "order dite", "book kore", "eta nibo", "cart e add", "checkout", "order confirm", "place order", "kinbo", "i want to order"];
  const confirmKeywords = ["should i confirm", "confirm this order", "confirm?"];
  const cancelKeywords = ["order cancelled", "no active order", "order cancel"];
  const confirmedKeywords = ["order confirmed", "your order id is"];

  const lowerUser = userText.toLowerCase();
  const lowerBot = botAnswer.toLowerCase();

  if (orderKeywords.some(k => lowerUser.includes(k))) {
    state.orderActive = true;
    el.orderStatusBar.classList.add("active");
  }
  if (confirmKeywords.some(k => lowerBot.includes(k))) {
    state.awaitingOrderConfirm = true;
    el.orderConfirmBar.classList.add("active");
  }
  if (cancelKeywords.some(k => lowerBot.includes(k)) || confirmedKeywords.some(k => lowerBot.includes(k))) {
    state.orderActive = false;
    state.awaitingOrderConfirm = false;
    el.orderStatusBar.classList.remove("active");
    el.orderConfirmBar.classList.remove("active");
  }
}

async function cancelOrder() {
  state.orderActive = false;
  state.awaitingOrderConfirm = false;
  el.orderStatusBar.classList.remove("active");
  el.orderConfirmBar.classList.remove("active");
  addMessage("user", "Cancel my order");
  const thinking = addMessage("assistant", "...");
  try {
    await fetch(`${state.apiBaseUrl}/orders/cancel/${state.sessionId}`, {
      method: "DELETE",
      headers: buildHeaders(),
    });
    thinking.querySelector(".body").textContent = "Order cancelled. Let me know if you want to browse more products.";
  } catch (_e) {
    thinking.querySelector(".body").textContent = "Order cancelled.";
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
  if (language) parts.push(`lang: ${language}`);
  if (ids.length) parts.push(`items: ${ids.slice(0, 3).join(", ")}`);
  meta.textContent = parts.join(" · ");
  node.appendChild(meta);
}

function renderImageMeta(node, response) {
  const meta = document.createElement("div");
  meta.className = "meta";
  const total = response?.total || 0;
  meta.textContent = `image-search · ${total} result(s)`;
  node.appendChild(meta);
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

function setStatus(kind, text) {
  el.statusPill.classList.remove("ready", "error");
  if (kind) el.statusPill.classList.add(kind);
  el.statusText.textContent = text;
}

function resizeInput() {
  el.input.style.height = "auto";
  el.input.style.height = `${Math.min(el.input.scrollHeight, 160)}px`;
}
