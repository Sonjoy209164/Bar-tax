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
  cart: [],                 // [{product_id, name, unit_price, quantity}]
  micRecording: false,
  recognition: null,
};

const el = {
  messages:        document.querySelector("#messages"),
  form:            document.querySelector("#chatForm"),
  input:           document.querySelector("#chatInput"),
  send:            document.querySelector("#sendButton"),
  statusPill:      document.querySelector("#statusPill"),
  statusText:      document.querySelector("#statusText"),
  chips:           document.querySelector("#chips"),
  imageInput:      document.querySelector("#imageInput"),
  imagePreview:    document.querySelector("#imagePreview"),
  clearImageBtn:   document.querySelector("#clearImageBtn"),
  imageLabel:      document.querySelector("#imageLabel"),
  orderStatusBar:  document.querySelector("#orderStatusBar"),
  orderConfirmBar: document.querySelector("#orderConfirmBar"),
  confirmOrderBtn: document.querySelector("#confirmOrderBtn"),
  cancelOrderBtn:  document.querySelector("#cancelOrderBtn"),
  cartPanel:       document.querySelector("#cartPanel"),
  cartToggle:      document.querySelector("#cartToggle"),
  cartItems:       document.querySelector("#cartItems"),
  cartCount:       document.querySelector("#cartCount"),
  cartChevron:     document.querySelector("#cartChevron"),
  cartTotalRow:    document.querySelector("#cartTotalRow"),
  cartSubtotal:    document.querySelector("#cartSubtotal"),
  micBtn:          document.querySelector("#micBtn"),
  trackBar:        document.querySelector("#trackBar"),
  trackInput:      document.querySelector("#trackInput"),
  trackBtn:        document.querySelector("#trackBtn"),
  trackClose:      document.querySelector("#trackClose"),
  trackOrderToggle:document.querySelector("#trackOrderToggle"),
};

init();

async function init() {
  await loadLocalConfig();
  bindEvents();
  initVoiceInput();
  addMessage(
    "assistant",
    "Ready. Ask in Bangla, Banglish, or English — products, styling, delivery, orders, comparisons. Upload a photo to find similar items, or tap 🎤 to speak."
  );
  await checkHealth();
}

async function loadLocalConfig() {
  try {
    const resp = await fetch("./config.local.json", { cache: "no-store" });
    if (!resp.ok) return;
    const config = await resp.json();
    if (config.apiBaseUrl) state.apiBaseUrl = String(config.apiBaseUrl).replace(/\/+$/, "");
    if (typeof config.apiKey === "string") state.apiKey = config.apiKey.trim();
  } catch (_) {}
}

function bindEvents() {
  el.form.addEventListener("submit", e => { e.preventDefault(); void handleSubmit(); });
  el.input.addEventListener("input", resizeInput);
  el.input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void handleSubmit(); }
  });
  el.chips.addEventListener("click", e => {
    const btn = e.target.closest("button");
    if (!btn) return;
    el.input.value = btn.textContent.trim();
    resizeInput();
    el.input.focus();
  });
  el.imageInput.addEventListener("change", handleImageSelect);
  el.clearImageBtn.addEventListener("click", clearImage);
  el.confirmOrderBtn.addEventListener("click", () => void sendMessage("yes"));
  el.cancelOrderBtn.addEventListener("click", () => void cancelOrder());
  el.cartToggle.addEventListener("click", toggleCart);
  el.micBtn.addEventListener("click", toggleMic);
  el.trackOrderToggle.addEventListener("click", () => el.trackBar.classList.toggle("active"));
  el.trackClose.addEventListener("click", () => el.trackBar.classList.remove("active"));
  el.trackBtn.addEventListener("click", () => void trackOrder());
}

// ── Voice Input ────────────────────────────────────────────────────────────────

function initVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    el.micBtn.title = "Voice input not supported in this browser";
    el.micBtn.style.opacity = "0.4";
    el.micBtn.style.pointerEvents = "none";
    return;
  }
  const r = new SpeechRecognition();
  r.continuous = false;
  r.interimResults = true;
  r.maxAlternatives = 1;
  r.lang = detectBrowserLang();

  r.onresult = e => {
    const transcript = Array.from(e.results).map(r => r[0].transcript).join("");
    el.input.value = transcript;
    resizeInput();
    if (e.results[e.results.length - 1].isFinal) stopMic();
  };
  r.onerror = () => stopMic();
  r.onend = () => stopMic();
  state.recognition = r;
}

function detectBrowserLang() {
  const nav = navigator.language || "en-US";
  if (nav.startsWith("bn")) return "bn-BD";
  return nav;
}

function toggleMic() {
  if (!state.recognition) return;
  if (state.micRecording) {
    stopMic();
  } else {
    state.micRecording = true;
    el.micBtn.classList.add("recording");
    el.micBtn.title = "Listening… tap to stop";
    // cycle language: if current is bn-BD switch to en-US and vice versa
    state.recognition.lang = state.recognition.lang === "bn-BD" ? "en-US" : "bn-BD";
    state.recognition.start();
  }
}

function stopMic() {
  state.micRecording = false;
  el.micBtn.classList.remove("recording");
  el.micBtn.title = "Voice input (Bangla/English)";
  try { state.recognition.stop(); } catch (_) {}
}

// ── Cart ───────────────────────────────────────────────────────────────────────

function toggleCart() {
  el.cartPanel.classList.toggle("open");
  el.cartChevron.textContent = el.cartPanel.classList.contains("open") ? "▲" : "▼";
}

function addToCart(productId, name, unitPrice, quantity = 1) {
  const existing = state.cart.find(i => i.product_id === productId);
  if (existing) { existing.quantity += quantity; }
  else { state.cart.push({ product_id: productId, name, unit_price: unitPrice, quantity }); }
  renderCart();
  // also POST to server
  apiPost("/orders/cart/quantity", { session_id: state.sessionId, product_id: productId, quantity: existing ? existing.quantity : quantity }).catch(() => {});
}

function renderCart() {
  const count = state.cart.reduce((s, i) => s + i.quantity, 0);
  el.cartCount.textContent = `(${count} item${count !== 1 ? "s" : ""})`;
  el.cartItems.innerHTML = "";
  let subtotal = 0;
  state.cart.forEach(item => {
    subtotal += item.unit_price * item.quantity;
    const row = document.createElement("div");
    row.className = "cart-item-row";
    row.innerHTML = `
      <span class="cart-item-name" title="${item.name}">${item.name.slice(0, 35)}</span>
      <div class="cart-item-controls">
        <button class="cart-qty-btn" data-pid="${item.product_id}" data-delta="-1">−</button>
        <span style="min-width:22px;text-align:center;">${item.quantity}</span>
        <button class="cart-qty-btn" data-pid="${item.product_id}" data-delta="1">+</button>
        <span style="min-width:70px;text-align:right;">BDT ${(item.unit_price * item.quantity).toLocaleString()}</span>
        <button class="cart-remove-btn" data-pid="${item.product_id}" title="Remove">✕</button>
      </div>`;
    el.cartItems.appendChild(row);
  });
  el.cartTotalRow.style.display = state.cart.length ? "flex" : "none";
  el.cartSubtotal.textContent = `BDT ${subtotal.toLocaleString()}`;

  // wire buttons
  el.cartItems.querySelectorAll(".cart-qty-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const pid = btn.dataset.pid;
      const delta = parseInt(btn.dataset.delta);
      const item = state.cart.find(i => i.product_id === pid);
      if (!item) return;
      item.quantity = Math.max(1, item.quantity + delta);
      apiPost("/orders/cart/quantity", { session_id: state.sessionId, product_id: pid, quantity: item.quantity }).catch(() => {});
      renderCart();
    });
  });
  el.cartItems.querySelectorAll(".cart-remove-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const pid = btn.dataset.pid;
      state.cart = state.cart.filter(i => i.product_id !== pid);
      apiPost("/orders/cart/remove", { session_id: state.sessionId, product_id: pid }).catch(() => {});
      renderCart();
    });
  });

  if (count > 0 && !el.cartPanel.classList.contains("open")) {
    el.cartPanel.classList.add("open");
    el.cartChevron.textContent = "▲";
  }
}

// ── Order Tracking ─────────────────────────────────────────────────────────────

async function trackOrder() {
  const val = el.trackInput.value.trim();
  if (!val) return;
  try {
    let url;
    if (val.startsWith("ORD-") || val.match(/^ORD/i)) {
      url = `${state.apiBaseUrl}/orders/${encodeURIComponent(val)}`;
    } else {
      url = `${state.apiBaseUrl}/orders/track/${encodeURIComponent(val)}`;
    }
    const resp = await fetch(url, { headers: buildHeaders() });
    const data = await resp.json();
    if (Array.isArray(data)) {
      if (data.length === 0) {
        addMessage("assistant", `No orders found for ${val}.`);
      } else {
        const lines = data.map(o =>
          `Order **${o.order_id}** — Status: ${o.tracking_status} | Total: BDT ${o.grand_total?.toLocaleString() || "?"} | ${o.created_at?.slice(0, 10) || ""}`
        );
        addMessage("assistant", lines.join("\n"));
      }
    } else {
      addMessage("assistant",
        `Order **${data.order_id}** — Status: ${data.order_status || data.status} | Tracking: ${data.tracking_status || "pending"}\nTotal: BDT ${data.grand_total?.toLocaleString() || "?"}`
      );
    }
  } catch (e) {
    addMessage("assistant", `Tracking failed: ${e.message}`);
  }
  el.trackBar.classList.remove("active");
  el.trackInput.value = "";
}

// ── Feedback ───────────────────────────────────────────────────────────────────

function addFeedbackRow(msgNode, question, answer, intent) {
  const row = document.createElement("div");
  row.className = "feedback-row";
  const label = document.createElement("span");
  label.className = "feedback-label";
  label.textContent = "Helpful?";
  const up = document.createElement("button");
  up.className = "feedback-btn";
  up.textContent = "👍";
  up.title = "This helped";
  const down = document.createElement("button");
  down.className = "feedback-btn";
  down.textContent = "👎";
  down.title = "This didn't help";

  const vote = async (rating) => {
    up.classList.add("voted");
    down.classList.add("voted");
    label.textContent = rating === "up" ? "Thanks!" : "Sorry!";
    await apiPost("/feedback", {
      session_id: state.sessionId,
      question,
      answer: answer.slice(0, 400),
      rating,
      intent: intent || null,
      product_ids: state.focusedProductIds.slice(0, 4),
    }).catch(() => {});
  };
  up.addEventListener("click", () => vote("up"));
  down.addEventListener("click", () => vote("down"));
  row.appendChild(label);
  row.appendChild(up);
  row.appendChild(down);
  msgNode.appendChild(row);
}

// ── Image Upload ───────────────────────────────────────────────────────────────

function handleImageSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const dataUrl = e.target.result;
    state.pendingImageB64 = dataUrl.split(",")[1];
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

// ── Send ───────────────────────────────────────────────────────────────────────

async function handleSubmit() {
  const text = el.input.value.trim();
  if (state.pendingImageB64) { await sendImageSearch(text); }
  else { await sendMessage(text); }
}

async function sendImageSearch(queryText) {
  if (state.busy) return;
  state.busy = true;
  el.send.disabled = true;
  const displayText = queryText || "Image search";
  addMessage("user", displayText + (state.pendingImageName ? ` [${state.pendingImageName}]` : ""));
  const thinking = addMessage("assistant", "Searching by image…");
  try {
    const response = await apiPost("/inventory/image-search", {
      query_text: queryText || "",
      image_b64: state.pendingImageB64,
      top_k: 5,
    });
    thinking.querySelector(".body").textContent = response.answer || "No similar items found.";
    renderImageMeta(thinking, response);
    addFeedbackRow(thinking, displayText, response.answer || "", "image_search");
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
  const thinking = addMessage("assistant", "…");

  try {
    const payload = {
      question: text,
      top_k: 5,
      assistant_mode: "support",
      reply_style: "short",
      answer_engine: "deterministic",
      conversation_history: state.conversation.slice(-8),
      focused_product_ids: state.focusedProductIds,
      last_answer_plan: state.lastAnswerPlan,
    };
    const response = await apiPost("/inventory/ask", payload);
    const answer = response.answer || "No answer returned.";
    thinking.querySelector(".body").textContent = answer;
    renderMeta(thinking, response);

    const intent = response?.answer_plan?.intent;
    addFeedbackRow(thinking, text, answer, intent);

    state.conversation.push({ role: "user", content: text });
    state.conversation.push({ role: "assistant", content: answer });
    state.lastAnswerPlan = response.answer_plan || null;
    const nextFocus = [
      ...(response.recommended_product_ids || []),
      ...(response.cross_sell_product_ids || []),
    ];
    state.focusedProductIds = Array.from(new Set(nextFocus)).slice(0, 8);

    detectOrderState(text, answer);
    detectProactiveCart(response);
  } catch (error) {
    thinking.querySelector(".body").textContent = `Request failed: ${error.message}`;
  } finally {
    state.busy = false;
    el.send.disabled = false;
    el.input.focus();
  }
}

// ── Order State Machine ────────────────────────────────────────────────────────

function detectOrderState(userText, botAnswer) {
  const orderKw    = ["order korte", "order dite", "book kore", "eta nibo", "cart e add", "checkout", "order confirm", "place order", "kinbo", "i want to order"];
  const confirmKw  = ["should i confirm", "confirm this order", "confirm?", "shall i confirm"];
  const cancelKw   = ["order cancelled", "no active order"];
  const confirmedKw = ["order confirmed", "your order id is"];

  const u = userText.toLowerCase();
  const b = botAnswer.toLowerCase();

  if (orderKw.some(k => u.includes(k))) {
    state.orderActive = true;
    el.orderStatusBar.classList.add("active");
  }
  if (confirmKw.some(k => b.includes(k))) {
    state.awaitingOrderConfirm = true;
    el.orderConfirmBar.classList.add("active");
  }
  if (cancelKw.some(k => b.includes(k)) || confirmedKw.some(k => b.includes(k))) {
    state.orderActive = false;
    state.awaitingOrderConfirm = false;
    el.orderStatusBar.classList.remove("active");
    el.orderConfirmBar.classList.remove("active");
    if (confirmedKw.some(k => b.includes(k))) state.cart = [];
    renderCart();
  }
}

function detectProactiveCart(response) {
  // If bot returned product IDs and user was ordering, add to local cart state
  const pids = response.recommended_product_ids || [];
  if (state.orderActive && pids.length && response.answer_plan) {
    const plan = response.answer_plan;
    // Only auto-add if the plan has a product name + price (draft was started)
  }
}

async function cancelOrder() {
  state.orderActive = false;
  state.awaitingOrderConfirm = false;
  el.orderStatusBar.classList.remove("active");
  el.orderConfirmBar.classList.remove("active");
  addMessage("user", "Cancel my order");
  const thinking = addMessage("assistant", "…");
  try {
    await fetch(`${state.apiBaseUrl}/orders/cancel/${state.sessionId}`, {
      method: "DELETE",
      headers: buildHeaders(),
    });
    thinking.querySelector(".body").textContent = "Order cancelled. Let me know if you want to browse more products.";
    state.cart = [];
    renderCart();
  } catch (_) {
    thinking.querySelector(".body").textContent = "Order cancelled.";
  }
}

// ── Proactive low-stock notice ─────────────────────────────────────────────────

function maybeLowStockNotice(msgNode, response) {
  // In future: check if any recommended product has stock <= 2, add inline notice
  // Requires product detail in response — placeholder hook
}

// ── API helpers ────────────────────────────────────────────────────────────────

async function apiPost(path, payload) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
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
  const h = { "Content-Type": "application/json" };
  if (state.apiKey) h["X-API-Key"] = state.apiKey;
  return h;
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
    ...(response?.cross_sell_product_ids || []),
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
  meta.textContent = `image-search · ${response?.total || 0} result(s)`;
  node.appendChild(meta);
}

async function checkHealth() {
  try {
    const resp = await fetch(`${state.apiBaseUrl}/health`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
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
