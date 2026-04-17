const state = {
  apiBaseUrl: sessionStorage.getItem("inventoryDemo.apiBaseUrl") || "http://localhost:4893",
  apiKey: sessionStorage.getItem("inventoryDemo.apiKey") || "",
  sampleData: null,
  lastTraceId: null,
  busy: false
};

const elements = {
  apiBaseUrl: document.querySelector("#apiBaseUrl"),
  apiKey: document.querySelector("#apiKey"),
  connectionDot: document.querySelector("#connectionDot"),
  connectionLabel: document.querySelector("#connectionLabel"),
  connectionDetail: document.querySelector("#connectionDetail"),
  saveSettingsButton: document.querySelector("#saveSettingsButton"),
  checkStatusButton: document.querySelector("#checkStatusButton"),
  syncCatalogButton: document.querySelector("#syncCatalogButton"),
  productCount: document.querySelector("#productCount"),
  productList: document.querySelector("#productList"),
  productTemplate: document.querySelector("#productTemplate"),
  assistantMode: document.querySelector("#assistantMode"),
  replyStyle: document.querySelector("#replyStyle"),
  endpointMode: document.querySelector("#endpointMode"),
  messages: document.querySelector("#messages"),
  chatForm: document.querySelector("#chatForm"),
  questionInput: document.querySelector("#questionInput"),
  lastTraceId: document.querySelector("#lastTraceId"),
  runTestsButton: document.querySelector("#runTestsButton"),
  testResults: document.querySelector("#testResults"),
  loadTraceButton: document.querySelector("#loadTraceButton"),
  traceOutput: document.querySelector("#traceOutput")
};

boot();

async function boot() {
  wireEvents();
  await loadLocalConfig();
  applySettingsToInputs();
  await loadSampleData();
  renderProducts();
  addMessage("bot", "Load the sample JSON into the RAG API, then ask me about watches, headphones, bundles, stockout risk, or margins.");
}

function wireEvents() {
  elements.saveSettingsButton.addEventListener("click", saveSettings);
  elements.checkStatusButton.addEventListener("click", checkStatus);
  elements.syncCatalogButton.addEventListener("click", syncSampleData);
  elements.chatForm.addEventListener("submit", askFromForm);
  elements.runTestsButton.addEventListener("click", runQualityTests);
  elements.loadTraceButton.addEventListener("click", () => loadTrace(state.lastTraceId));
}

async function loadSampleData() {
  const response = await fetch("./data/products.json");
  if (!response.ok) {
    throw new Error("Could not load frontend/data/products.json");
  }
  state.sampleData = await response.json();
}

async function loadLocalConfig() {
  try {
    const response = await fetch("./config.local.json", { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const config = await response.json();
    if (config.apiBaseUrl) {
      state.apiBaseUrl = normalizeBaseUrl(config.apiBaseUrl);
    }
    if (typeof config.apiKey === "string") {
      state.apiKey = config.apiKey.trim();
    }
    setConnection("neutral", "Local config loaded", "Using frontend/config.local.json for this browser-only test.");
  } catch (error) {
    console.warn("Could not load frontend/config.local.json", error);
  }
}

function applySettingsToInputs() {
  elements.apiBaseUrl.value = state.apiBaseUrl;
  elements.apiKey.value = state.apiKey;
}

function saveSettings() {
  state.apiBaseUrl = normalizeBaseUrl(elements.apiBaseUrl.value);
  state.apiKey = elements.apiKey.value.trim();
  elements.apiBaseUrl.value = state.apiBaseUrl;
  sessionStorage.setItem("inventoryDemo.apiBaseUrl", state.apiBaseUrl);
  if (state.apiKey) {
    sessionStorage.setItem("inventoryDemo.apiKey", state.apiKey);
  } else {
    sessionStorage.removeItem("inventoryDemo.apiKey");
  }
  setConnection("neutral", "Settings saved", "API settings are stored in this browser tab session.");
}

async function checkStatus() {
  saveSettings();
  await withBusy(async () => {
    const [inventoryStatus, businessStatus, productionStatus] = await Promise.all([
      apiGet("/inventory/status"),
      apiGet("/inventory/business/status"),
      apiGet("/inventory/production/status")
    ]);
    setConnection(
      "good",
      "RAG API reachable",
      `${inventoryStatus.total_items || 0} mirrored products, ${businessStatus.total_signals || 0} business signals, vector ${inventoryStatus.vector_backend}.`
    );
    elements.traceOutput.textContent = JSON.stringify({ inventoryStatus, businessStatus, productionStatus }, null, 2);
  }, "Status check failed");
}

async function syncSampleData() {
  saveSettings();
  await withBusy(async () => {
    const upsertCatalog = await apiPost("/inventory/items/upsert", { items: state.sampleData.items });
    const upsertBusiness = await apiPost("/inventory/business/signals/upsert", {
      signals: state.sampleData.business_signals || []
    });
    const syncStatus = await apiGet("/inventory/sync/status");
    setConnection(
      "good",
      "Sample JSON synced",
      `${upsertCatalog.upserted_count} products and ${upsertBusiness.upserted_count} business signals sent to RAG.`
    );
    elements.traceOutput.textContent = JSON.stringify({ upsertCatalog, upsertBusiness, syncStatus }, null, 2);
  }, "Sync failed");
}

async function askFromForm(event) {
  event.preventDefault();
  const question = elements.questionInput.value.trim();
  if (!question) {
    return;
  }
  elements.questionInput.value = "";
  addMessage("user", question);
  await askQuestion({
    question,
    endpoint: elements.endpointMode.value,
    assistant_mode: elements.assistantMode.value,
    reply_style: elements.replyStyle.value,
    render: true
  });
}

async function askQuestion({ question, endpoint, assistant_mode, reply_style, render }) {
  saveSettings();
  const path = endpoint === "agentic" ? "/inventory/agentic/ask" : "/inventory/ask";
  const payload = {
    question,
    assistant_mode,
    reply_style,
    top_k: 6,
    answer_engine: "auto"
  };
  if (endpoint === "agentic") {
    payload.max_reasoning_steps = 4;
    payload.available_data_domains = [
      "catalog",
      "sales",
      "orders",
      "inventory_snapshots",
      "suppliers",
      "margins",
      "returns",
      "customers"
    ];
  }

  const response = await withBusy(async () => {
    const response = await apiPost(path, payload);
    state.lastTraceId = response.trace_id || null;
    elements.lastTraceId.textContent = state.lastTraceId ? `Trace ${shortId(state.lastTraceId)}` : "No trace";
    if (render) {
      addMessage("bot", response.answer, response);
    }
    return response;
  }, "Chat request failed");
  if (render && response?.trace_id) {
    await loadTrace(response.trace_id, { quiet: true });
  }
  return response;
}

async function runQualityTests() {
  saveSettings();
  elements.testResults.innerHTML = "";
  for (const testCase of state.sampleData.test_questions || []) {
    const response = await askQuestion({
      question: testCase.question,
      endpoint: testCase.endpoint || "ask",
      assistant_mode: testCase.assistant_mode || "support",
      reply_style: testCase.reply_style || "short",
      render: false
    });
    if (response) {
      renderTestResult(testCase, response);
    }
  }
}

async function loadTrace(traceId, options = {}) {
  if (!traceId) {
    if (!options.quiet) {
      elements.traceOutput.textContent = "No trace ID yet. Ask a question first.";
    }
    return;
  }
  await withBusy(async () => {
    const trace = await apiGet(`/inventory/chat/trace/${encodeURIComponent(traceId)}`);
    elements.traceOutput.textContent = JSON.stringify(trace, null, 2);
  }, "Trace load failed", options);
}

function renderProducts() {
  const items = state.sampleData?.items || [];
  elements.productCount.textContent = `${items.length} products`;
  elements.productList.innerHTML = "";
  for (const item of items) {
    const node = elements.productTemplate.content.cloneNode(true);
    node.querySelector("[data-name]").textContent = item.name;
    node.querySelector("[data-meta]").textContent = `${item.category || "Uncategorized"} · ${item.sku} · stock ${item.stock}`;
    node.querySelector("[data-price]").textContent = `${item.currency || "USD"} ${Number(item.price || 0).toFixed(2)}`;
    elements.productList.appendChild(node);
  }
}

function renderTestResult(testCase, response) {
  const productIds = new Set([
    ...(response.recommended_product_ids || []),
    ...(response.cross_sell_product_ids || []),
    ...(response.hits || []).map((hit) => hit.product_id)
  ]);
  const expectedIds = testCase.expected_product_ids || [];
  const forbiddenIds = testCase.forbidden_product_ids || [];
  const expectedFound = expectedIds.length === 0 || expectedIds.some((id) => productIds.has(id));
  const forbiddenFound = forbiddenIds.some((id) => productIds.has(id));
  const noHitsOk = !testCase.expected_no_hits || (response.total_hits === 0 && (response.hits || []).length === 0);
  const textOk = (testCase.must_include_text || []).every((snippet) => (response.answer || "").includes(snippet));
  const passed = expectedFound && !forbiddenFound && noHitsOk && textOk;

  const card = document.createElement("article");
  card.className = `test-card ${passed ? "pass" : "fail"}`;
  card.innerHTML = `
    <strong>${passed ? "PASS" : "CHECK"} · ${escapeHtml(testCase.label)}</strong>
    <span>${escapeHtml(testCase.question)}</span>
    <small>Trace: ${response.trace_id ? shortId(response.trace_id) : "none"} · Engine: ${escapeHtml(response.answer_engine || "unknown")} · Hits: ${response.total_hits ?? 0}</small>
    <small>Products: ${escapeHtml(Array.from(productIds).join(", ") || "none")}</small>
  `;
  elements.testResults.appendChild(card);
}

function addMessage(role, text, response = null) {
  const message = document.createElement("article");
  message.className = `message ${role}`;
  const body = document.createElement("div");
  body.textContent = text;
  message.appendChild(body);

  if (response) {
    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.innerHTML = `
      <span class="pill">${escapeHtml(response.answer_engine || "unknown")}</span>
      <span class="pill">confidence ${Math.round((response.confidence_score || 0) * 100)}%</span>
      ${response.trace_id ? `<span class="pill">trace ${shortId(response.trace_id)}</span>` : ""}
    `;
    message.appendChild(meta);
    if ((response.hits || []).length) {
      const hits = document.createElement("div");
      hits.className = "hits";
      hits.append(...response.hits.slice(0, 4).map(renderHit));
      message.appendChild(hits);
    }
  }

  elements.messages.appendChild(message);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function renderHit(hit) {
  const card = document.createElement("article");
  card.className = "hit-card";
  card.innerHTML = `
    <strong>${escapeHtml(hit.name)}</strong>
    <small>${escapeHtml(hit.sku)} · ${escapeHtml(hit.category || "No category")} · stock ${hit.stock ?? "?"}</small>
    <small>${escapeHtml(hit.currency || "USD")} ${Number(hit.price || 0).toFixed(2)} · match ${Math.round((hit.score || 0) * 100)}%</small>
  `;
  return card;
}

async function apiGet(path) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    headers: buildHeaders()
  });
  return parseApiResponse(response);
}

async function apiPost(path, body) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(body)
  });
  return parseApiResponse(response);
}

function buildHeaders() {
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json"
  };
  if (state.apiKey) {
    headers["X-API-Key"] = state.apiKey;
  }
  return headers;
}

async function parseApiResponse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const message = data?.detail?.message || data?.detail?.error || data?.message || response.statusText;
    throw new Error(`${response.status} ${message}`);
  }
  return data;
}

async function withBusy(task, errorPrefix, options = {}) {
  if (state.busy) {
    return null;
  }
  state.busy = true;
  setButtonsDisabled(true);
  try {
    return await task();
  } catch (error) {
    setConnection("bad", errorPrefix, error.message);
    if (!options.quiet) {
      elements.traceOutput.textContent = `${errorPrefix}: ${error.message}`;
    }
    return null;
  } finally {
    state.busy = false;
    setButtonsDisabled(false);
  }
}

function setButtonsDisabled(disabled) {
  for (const button of document.querySelectorAll("button")) {
    button.disabled = disabled;
  }
}

function setConnection(kind, label, detail) {
  elements.connectionDot.classList.toggle("good", kind === "good");
  elements.connectionDot.classList.toggle("bad", kind === "bad");
  elements.connectionLabel.textContent = label;
  elements.connectionDetail.textContent = detail;
}

function normalizeBaseUrl(value) {
  return (value || "http://localhost:4893").trim().replace(/\/+$/, "");
}

function shortId(value) {
  return String(value).slice(0, 8);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
