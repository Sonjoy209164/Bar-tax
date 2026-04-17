const state = {
  apiBaseUrl: sessionStorage.getItem("inventoryDemo.apiBaseUrl") || "http://localhost:4893",
  apiKey: sessionStorage.getItem("inventoryDemo.apiKey") || "",
  sampleData: null,
  lastTraceId: null,
  recentHits: [],
  conversationHistory: [],
  focusedProductIds: [],
  activeFilters: null,
  lastAnswerPlan: null,
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
  answerEngine: document.querySelector("#answerEngine"),
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
      optionalApiGet("/inventory/business/status"),
      optionalApiGet("/inventory/production/status")
    ]);
    const businessDetail = businessStatus.unavailable
      ? "business endpoints unavailable"
      : `${businessStatus.total_signals || 0} business signals`;
    const productionDetail = productionStatus.unavailable
      ? "production status unavailable"
      : `production ${productionStatus.production_ready ? "ready" : "not ready"}`;
    setConnection(
      "good",
      "RAG API reachable",
      `${inventoryStatus.total_items || 0} mirrored products, ${businessDetail}, vector ${inventoryStatus.vector_backend}, ${productionDetail}.`
    );
    elements.traceOutput.textContent = JSON.stringify({ inventoryStatus, businessStatus, productionStatus }, null, 2);
  }, "Status check failed");
}

async function syncSampleData() {
  saveSettings();
  await withBusy(async () => {
    const upsertCatalog = await apiPost("/inventory/items/upsert", { items: state.sampleData.items });
    const upsertBusiness = await optionalApiPost("/inventory/business/signals/upsert", {
      signals: state.sampleData.business_signals || []
    });
    const syncStatus = await optionalApiGet("/inventory/sync/status");
    const businessDetail = upsertBusiness.unavailable
      ? "business signal endpoint unavailable on this server"
      : `${upsertBusiness.upserted_count} business signals`;
    const syncDetail = syncStatus.unavailable ? "sync-status endpoint unavailable" : "sync status checked";
    setConnection(
      "good",
      "Sample JSON synced",
      `${upsertCatalog.upserted_count} products synced; ${businessDetail}; ${syncDetail}.`
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
  const localReply = buildLocalConversationReply(
    question,
    elements.assistantMode.value,
    elements.replyStyle.value
  );
  if (localReply) {
    const response = buildLocalConversationResponse(question, localReply);
    addMessage("bot", response.answer, response);
    rememberConversation(question, response, { focusedProductIds: [], filters: null });
    return;
  }
  await askQuestion({
    question,
    endpoint: elements.endpointMode.value,
    assistant_mode: elements.assistantMode.value,
    reply_style: elements.replyStyle.value,
    answer_engine: elements.answerEngine.value,
    render: true
  });
}

async function askQuestion({ question, endpoint, assistant_mode, reply_style, answer_engine, render }) {
  saveSettings();
  const path = endpoint === "agentic" ? "/inventory/agentic/ask" : "/inventory/ask";
  const requestContext = buildRequestContext(question);
  const payload = {
    question,
    assistant_mode,
    reply_style,
    top_k: 6,
    answer_engine: answer_engine || "auto",
    conversation_history: state.conversationHistory.slice(-8),
    focused_product_ids: requestContext.focusedProductIds,
    active_filters: state.activeFilters,
    last_answer_plan: state.lastAnswerPlan
  };
  if (requestContext.filters) {
    payload.filters = requestContext.filters;
  }
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
    response.demo_scope = requestContext;
    state.lastTraceId = response.trace_id || null;
    elements.lastTraceId.textContent = state.lastTraceId ? `Trace ${shortId(state.lastTraceId)}` : "No trace";
    if (render) {
      addMessage("bot", response.answer, response);
      rememberConversation(question, response, requestContext);
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
      answer_engine: testCase.answer_engine || "auto",
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
      ${response.demo_scope?.focusedProductIds?.length ? `<span class="pill">scoped ${response.demo_scope.focusedProductIds.length} products</span>` : ""}
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

function buildRequestContext(question) {
  const focusedProductIds = extractFocusedProductIds(question);
  return {
    focusedProductIds,
    filters: focusedProductIds.length ? { product_ids: focusedProductIds } : null
  };
}

function extractFocusedProductIds(question) {
  const normalizedQuestion = normalizeSearchText(question);
  const matches = [];
  for (const candidate of buildCandidateIndex()) {
    if (candidateMatchesQuestion(candidate, normalizedQuestion)) {
      matches.push(candidate.product_id);
    }
  }
  if (!matches.length && looksLikeChoiceFollowUp(question)) {
    matches.push(...state.focusedProductIds);
  }
  return dedupe(matches).slice(0, 12);
}

function buildCandidateIndex() {
  const byId = new Map();
  for (const item of state.sampleData?.items || []) {
    byId.set(item.product_id, normalizeCandidate(item));
  }
  for (const hit of state.recentHits) {
    byId.set(hit.product_id, normalizeCandidate(hit));
  }
  return Array.from(byId.values()).filter((candidate) => candidate.product_id);
}

function normalizeCandidate(item) {
  return {
    product_id: item.product_id,
    sku: item.sku || "",
    name: item.name || "",
    category: item.category || "",
    brand: item.brand || ""
  };
}

function candidateMatchesQuestion(candidate, normalizedQuestion) {
  const referenceValues = [candidate.product_id, candidate.sku, candidate.name]
    .map(normalizeSearchText)
    .filter(Boolean);
  return referenceValues.some((value) => normalizedQuestion.includes(value));
}

function looksLikeChoiceFollowUp(question) {
  const normalized = normalizeSearchText(question);
  return [
    "which one",
    "which should i buy",
    "which one should i buy",
    "which is better",
    "which should i choose",
    "compare them",
    "between these",
    "tell me about this"
  ].some((phrase) => normalized.includes(phrase));
}

function rememberConversation(question, response, requestContext) {
  state.conversationHistory.push({ role: "user", content: question });
  state.conversationHistory.push({ role: "assistant", content: response.answer || "" });
  state.conversationHistory = state.conversationHistory.slice(-8);
  state.lastAnswerPlan = response.answer_plan || null;
  state.activeFilters = response.applied_filters || requestContext.filters || null;
  state.recentHits = mergeRecentHits(state.recentHits, response.hits || []);

  const responseProductIds = [
    ...(response.recommended_product_ids || []),
    ...(response.hits || []).map((hit) => hit.product_id)
  ];
  state.focusedProductIds = dedupe(responseProductIds.length ? responseProductIds : requestContext.focusedProductIds).slice(0, 12);
}

function mergeRecentHits(existingHits, newHits) {
  const byId = new Map();
  for (const hit of [...existingHits, ...newHits]) {
    if (hit?.product_id) {
      byId.set(hit.product_id, hit);
    }
  }
  return Array.from(byId.values()).slice(-30);
}

function buildLocalConversationReply(question, assistantMode, replyStyle) {
  const normalized = normalizeSearchText(question);
  if (!normalized || looksLikeInventoryAsk(normalized)) {
    return null;
  }

  const detailed = replyStyle === "detailed";
  const salesMode = assistantMode === "sales";

  if (hasAnyPhrase(normalized, ["how are you", "how are you doing", "how is it going", "hows it going"])) {
    return {
      answer: salesMode
        ? "I’m good, and ready to help you sell smarter. Tell me what the customer is looking for, their budget, or the product they are comparing."
        : "I’m good, and ready to help with product questions, stock, prices, comparisons, and restocking.",
      follow_up_question: detailed ? "What are we helping with first: product search, comparison, stock, or restock planning?" : null
    };
  }

  if (hasAnyPhrase(normalized, ["thanks", "thank you", "appreciate it"])) {
    return {
      answer: "Anytime. Send me a product, customer need, budget, or stock question and I’ll keep it grounded in the catalog.",
      follow_up_question: null
    };
  }

  if (hasAnyPhrase(normalized, ["who are you", "what are you", "what do you do"])) {
    return {
      answer: "I’m your inventory sales/support assistant. I can search the mirrored catalog, compare products, explain tradeoffs, suggest alternatives, and help with restock-style questions.",
      follow_up_question: detailed ? "Give me a product name or customer need and I’ll recommend the best next move." : null
    };
  }

  if (hasAnyPhrase(normalized, ["help", "what can you do", "how can you help"])) {
    return {
      answer: "I can help with product discovery, comparisons, stock checks, price-sensitive alternatives, bundles, and restock questions.",
      follow_up_question: detailed ? "Try: “show me watches under 250”, “compare these two chairs”, or “what should I restock first?”" : null
    };
  }

  if (hasAnyPhrase(normalized, ["bye", "goodbye", "see you"])) {
    return {
      answer: "See you. When you come back, give me a product or customer scenario and I’ll pick up from there.",
      follow_up_question: null
    };
  }

  if (hasAnyPhrase(normalized, ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"])) {
    return {
      answer: salesMode
        ? "Hey. I’m here. Tell me what the customer wants, their budget, or which products they’re choosing between, and I’ll help you sell the right option."
        : "Hey. I’m here. Ask me about a product, stock, price, comparison, bundle, or restock question.",
      follow_up_question: detailed ? "What is the customer looking for today?" : null
    };
  }

  return null;
}

function buildLocalConversationResponse(question, reply) {
  return {
    status: "success",
    question,
    answer: reply.answer,
    assistant_mode: elements.assistantMode.value,
    reply_style: elements.replyStyle.value,
    answer_engine: "local-conversation",
    confidence_score: 1,
    trace_id: null,
    abstained: false,
    abstention_reason: null,
    total_hits: 0,
    applied_filters: null,
    hits: [],
    recommended_product_ids: [],
    cross_sell_product_ids: [],
    follow_up_question: reply.follow_up_question,
    answer_plan: {
      intent: "small_talk",
      detected_intent: "small_talk",
      strategy: "conversation",
      next_best_question: reply.follow_up_question
    },
    verification: {
      passed: true,
      checked_final_answer: true,
      final_answer_issues: []
    },
    memory_resolution: {
      used_memory: false,
      reason: "Small talk handled locally so retrieval is skipped."
    },
    demo_scope: {
      localConversation: true,
      focusedProductIds: []
    }
  };
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

async function optionalApiGet(path) {
  try {
    return await apiGet(path);
  } catch (error) {
    if (error.status === 404) {
      return { status: "unavailable", unavailable: true, endpoint: path, message: error.message };
    }
    throw error;
  }
}

async function optionalApiPost(path, body) {
  try {
    return await apiPost(path, body);
  } catch (error) {
    if (error.status === 404) {
      return { status: "unavailable", unavailable: true, endpoint: path, message: error.message };
    }
    throw error;
  }
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
    const error = new Error(`${response.status} ${message}`);
    error.status = response.status;
    throw error;
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

function dedupe(values) {
  const output = [];
  const seen = new Set();
  for (const value of values) {
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    output.push(value);
  }
  return output;
}

function normalizeSearchText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function hasAnyPhrase(text, phrases) {
  return phrases.some((phrase) => text.includes(phrase));
}

function looksLikeInventoryAsk(normalized) {
  return hasAnyPhrase(normalized, [
    "stock",
    "price",
    "buy",
    "sell",
    "recommend",
    "suggest",
    "show",
    "find",
    "compare",
    "bundle",
    "restock",
    "margin",
    "product",
    "sku",
    "watch",
    "watches",
    "headphone",
    "headphones",
    "earbud",
    "microphone",
    "laptop",
    "dock",
    "chair",
    "office",
    "audio",
    "computing",
    "wearable"
  ]);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
