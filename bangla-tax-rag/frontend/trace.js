const state = {
  apiBaseUrl: window.location.origin,
  apiKey: "5230ff9faefe885d22345444e006cab576acdae5ea75d499",
  conversation: [],
  focusedProductIds: [],
  lastAnswerPlan: null,
  busy: false,
};

const el = {
  connectionDot: document.querySelector("#connectionDot"),
  connectionText: document.querySelector("#connectionText"),
  queryInput: document.querySelector("#queryInput"),
  answerEngine: document.querySelector("#answerEngine"),
  replyStyle: document.querySelector("#replyStyle"),
  assistantMode: document.querySelector("#assistantMode"),
  topK: document.querySelector("#topK"),
  runButton: document.querySelector("#runButton"),
  clearButton: document.querySelector("#clearButton"),
  examples: document.querySelector(".examples"),
  traceId: document.querySelector("#traceId"),
  executionPath: document.querySelector("#executionPath"),
  intent: document.querySelector("#intent"),
  latency: document.querySelector("#latency"),
  answerEngineLabel: document.querySelector("#answerEngineLabel"),
  finalAnswer: document.querySelector("#finalAnswer"),
  statusBadges: document.querySelector("#statusBadges"),
  whySummary: document.querySelector("#whySummary"),
  payloadView: document.querySelector("#payloadView"),
  routeView: document.querySelector("#routeView"),
  memoryView: document.querySelector("#memoryView"),
  imageSearchPanel: document.querySelector("#imageSearchPanel"),
  imageSearchView: document.querySelector("#imageSearchView"),
  imageSearchHits: document.querySelector("#imageSearchHits"),
  retrievalCounts: document.querySelector("#retrievalCounts"),
  retrievedIds: document.querySelector("#retrievedIds"),
  rerankedIds: document.querySelector("#rerankedIds"),
  recommendedIds: document.querySelector("#recommendedIds"),
  crossSellIds: document.querySelector("#crossSellIds"),
  catalogEvidence: document.querySelector("#catalogEvidence"),
  rejectedCandidates: document.querySelector("#rejectedCandidates"),
  answerPlanView: document.querySelector("#answerPlanView"),
  evidenceView: document.querySelector("#evidenceView"),
  verificationView: document.querySelector("#verificationView"),
  notesView: document.querySelector("#notesView"),
  rawResponse: document.querySelector("#rawResponse"),
  rawTrace: document.querySelector("#rawTrace"),
};

init();

async function init() {
  await loadLocalConfig();
  await loadRuntimeConfig();
  bindEvents();
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

async function loadRuntimeConfig() {
  try {
    const resp = await fetch("./runtime-config.json", { cache: "no-store" });
    if (!resp.ok) return;
    const config = await resp.json();
    if (config.apiBaseUrl) state.apiBaseUrl = String(config.apiBaseUrl).replace(/\/+$/, "");
  } catch (_) {}
}

function bindEvents() {
  el.runButton.addEventListener("click", () => void runQuery());
  el.clearButton.addEventListener("click", clearOutputs);
  el.queryInput.addEventListener("keydown", event => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void runQuery();
    }
  });
  el.examples.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;
    el.queryInput.value = button.dataset.query || button.textContent.trim();
    el.queryInput.focus();
  });
}

async function checkHealth() {
  try {
    const health = await apiGet("/health", { includeApiKey: false });
    const status = health.status || "ready";
    setConnection(true, `Connected: ${status}`);
  } catch (error) {
    setConnection(false, `Offline: ${error.message}`);
  }
}

async function runQuery() {
  const question = el.queryInput.value.trim();
  if (!question || state.busy) return;

  state.busy = true;
  el.runButton.disabled = true;
  el.runButton.textContent = "Running...";
  setConnection(true, "Running query");
  clearOutputs({ keepPayload: true });

  const payload = {
    question,
    top_k: Number(el.topK.value || 5),
    assistant_mode: el.assistantMode.value,
    reply_style: el.replyStyle.value,
    answer_engine: el.answerEngine.value,
    debug_retrieval_probe: true,
    conversation_history: state.conversation.slice(-8),
    focused_product_ids: state.focusedProductIds,
    last_answer_plan: state.lastAnswerPlan,
  };

  el.payloadView.textContent = pretty(payload);

  try {
    const started = performance.now();
    const response = await apiPost("/inventory/ask", payload);
    const requestMs = Math.round(performance.now() - started);
    const trace = await fetchTrace(response.trace_id);

    state.conversation.push({ role: "user", content: question });
    state.conversation.push({ role: "assistant", content: response.answer || "" });
    state.lastAnswerPlan = response.answer_plan || null;
    state.focusedProductIds = unique([
      ...(response.recommended_product_ids || []),
      ...(response.cross_sell_product_ids || []),
    ]).slice(0, 8);

    renderResponseAndTrace(response, trace, requestMs);
    setConnection(true, "Trace loaded");
  } catch (error) {
    setConnection(false, `Request failed: ${error.message}`);
    el.finalAnswer.textContent = `Request failed: ${error.message}`;
    el.finalAnswer.classList.add("error");
  } finally {
    state.busy = false;
    el.runButton.disabled = false;
    el.runButton.textContent = "Run Query";
  }
}

async function fetchTrace(traceId) {
  if (!traceId) return null;
  try {
    return await apiGet(`/inventory/chat/trace/${encodeURIComponent(traceId)}`);
  } catch (error) {
    return {
      trace_id: traceId,
      trace_fetch_error: error.message,
    };
  }
}

function renderResponseAndTrace(response, trace, requestMs) {
  const merged = trace && !trace.trace_fetch_error ? trace : {};
  const answerPlan = response.answer_plan || merged.answer_plan || {};
  const evidence = answerPlan.evidence_contract || {};
  const verification = response.verification || merged.verification || {};
  const productMap = buildProductMap(response.hits || []);
  const rejectedCandidates = collectRejectedCandidates(merged, answerPlan);

  el.traceId.textContent = response.trace_id || merged.trace_id || "-";
  el.executionPath.textContent = merged.execution_path || "response-only";
  el.intent.textContent = merged.intent || answerPlan.intent || "-";
  el.latency.textContent = merged.latency_ms ? `${merged.latency_ms} ms` : `${requestMs} ms`;
  el.answerEngineLabel.textContent = response.answer_engine || "-";
  el.finalAnswer.textContent = response.answer || merged.final_answer || "No answer returned.";
  el.finalAnswer.classList.remove("muted", "error");
  renderBadges(response, merged, verification);
  renderWhySummary(response, merged, answerPlan, verification, rejectedCandidates);

  renderKv(el.routeView, {
    execution_path: merged.execution_path,
    route_decision: merged.route_decision,
    answer_engine: response.answer_engine,
    fallback_reason: merged.fallback_reason,
    confidence_score: response.confidence_score,
    total_hits: response.total_hits,
    abstained: response.abstained,
    abstention_reason: response.abstention_reason,
  });

  renderKv(el.memoryView, {
    memory_resolution: response.memory_resolution || merged.memory_resolution,
    applied_filters: response.applied_filters || merged.applied_filters,
    preferences: merged.preferences || answerPlan.preferences,
  });

  renderImageSearch(merged.image_search);
  renderCounts(merged.retrieval_stage_counts || {});
  renderList(el.retrievedIds, merged.retrieved_product_ids || []);
  renderList(el.rerankedIds, merged.reranked_product_ids || []);
  renderList(el.recommendedIds, response.recommended_product_ids || merged.recommended_product_ids || []);
  renderList(el.crossSellIds, response.cross_sell_product_ids || merged.cross_sell_product_ids || []);
  renderCatalogEvidence(response.hits || [], answerPlan, productMap);
  renderRejectedCandidates(rejectedCandidates, productMap);

  renderKv(el.answerPlanView, summarizeAnswerPlan(answerPlan));
  renderKv(el.evidenceView, summarizeEvidence(evidence));
  renderKv(el.verificationView, verification);
  renderNotes(merged, trace);

  el.rawResponse.textContent = pretty(response);
  el.rawTrace.textContent = pretty(trace || {});
}

function renderImageSearch(imageSearch) {
  if (!el.imageSearchPanel) return;
  if (!imageSearch || !Object.keys(imageSearch).length) {
    el.imageSearchPanel.style.display = "none";
    el.imageSearchView.innerHTML = "";
    el.imageSearchHits.innerHTML = "";
    return;
  }
  el.imageSearchPanel.style.display = "";
  renderKv(el.imageSearchView, {
    retrieval_engine: imageSearch.retrieval_engine,
    decision_label: imageSearch.decision_label,
    primary_product_id: imageSearch.primary_product_id,
    query_image_id: imageSearch.query_image_id,
    requested_color: imageSearch.requested_color,
    available_colors: imageSearch.available_colors,
    same_design_variant_ids: imageSearch.same_design_variant_ids,
    similar_product_ids: imageSearch.similar_product_ids,
    retrieved_product_ids: imageSearch.retrieved_product_ids,
    score_breakdown: imageSearch.score_breakdown,
  });
  const hits = Array.isArray(imageSearch.hits) ? imageSearch.hits : [];
  if (!hits.length) {
    el.imageSearchHits.innerHTML = `<p class="muted-text">No image hits recorded.</p>`;
    return;
  }
  el.imageSearchHits.innerHTML = hits.map(hit => {
    const reasons = Array.isArray(hit.reasons) ? hit.reasons.join(", ") : "";
    const refFlag = hit.is_reference ? " · reference image" : "";
    return `
      <div class="evidence-card">
        <h3>${escapeHtml(String(hit.name || hit.product_id || "-"))}</h3>
        <p><strong>${escapeHtml(String(hit.decision_label || hit.match_type || "-"))}</strong>
           · score ${escapeHtml(String(hit.score ?? "-"))}
           · ${escapeHtml(String(hit.image_kind || "unknown"))}${escapeHtml(refFlag)}</p>
        <p>variant_group: ${escapeHtml(String(hit.variant_group_id || "-"))}
           · color: ${escapeHtml(String(hit.color || "-"))}
           · stock: ${escapeHtml(String(hit.stock ?? "-"))}</p>
        ${reasons ? `<p class="muted-text">${escapeHtml(reasons)}</p>` : ""}
      </div>
    `;
  }).join("");
}

function renderBadges(response, trace, verification) {
  const counts = trace.retrieval_stage_counts || {};
  const retrievalHitCount = Number(response.total_hits || trace.total_hits || 0);
  const memory = response.memory_resolution || trace.memory_resolution || {};
  const elasticTouched = Boolean(
    counts.elasticsearch_probe_requests ||
    counts.elastic_lexical_raw_matches ||
    counts.elastic_hybrid_pool_candidates
  );
  const badges = [
    {
      label: `Memory ${memory.used_memory ? "used" : "not used"}`,
      tone: memory.used_memory ? "info" : "neutral",
    },
    {
      label: `Retrieval ${retrievalHitCount > 0 ? "found hits" : "no hits"}`,
      tone: retrievalHitCount > 0 ? "ok" : "warn",
    },
    {
      label: `Verification ${verification.passed ? "passed" : "flagged"}`,
      tone: verification.passed ? "ok" : "bad",
    },
    {
      label: `Abstained ${response.abstained ? "yes" : "no"}`,
      tone: response.abstained ? "warn" : "ok",
    },
    {
      label: `Path ${trace.execution_path || "response-only"}`,
      tone: "info",
    },
  ];
  if (elasticTouched) {
    badges.push({ label: "Elasticsearch touched", tone: "ok" });
  }
  if (Object.keys(counts).length) {
    badges.push({ label: `${Object.keys(counts).length} retrieval counters`, tone: "neutral" });
  }
  el.statusBadges.innerHTML = badges.map(badge => (
    `<span class="status-badge ${badge.tone}">${escapeHtml(badge.label)}</span>`
  )).join("");
}

function renderWhySummary(response, trace, answerPlan, verification, rejectedCandidates) {
  const path = trace.execution_path || "response-only";
  const intent = trace.intent || answerPlan.intent || "unknown";
  const totalHits = response.total_hits ?? trace.total_hits ?? 0;
  const primary = answerPlan.primary_product_id || "no primary product";
  const engine = response.answer_engine || trace.answer_engine || "unknown";
  const verifyText = verification.passed
    ? "Verification passed."
    : `Verification flagged ${verification.issues?.length || verification.hard_constraint_issues?.length || 0} issue(s).`;
  const rejectedText = rejectedCandidates.length
    ? `${rejectedCandidates.length} rejected candidate(s) were recorded.`
    : "No rejected candidates were recorded for this path.";
  const fallbackText = trace.fallback_reason
    ? `Fallback reason: ${trace.fallback_reason}.`
    : "No fallback reason was recorded.";
  el.whySummary.innerHTML = `
    <p>This query used <strong>${escapeHtml(path)}</strong> with intent <strong>${escapeHtml(intent)}</strong>.</p>
    <p>It returned <strong>${escapeHtml(String(totalHits))}</strong> catalog hit(s), selected <strong>${escapeHtml(primary)}</strong>, and used the <strong>${escapeHtml(engine)}</strong> answer writer.</p>
    <p>${escapeHtml(verifyText)} ${escapeHtml(rejectedText)} ${escapeHtml(fallbackText)}</p>
  `;
  el.whySummary.classList.remove("muted");
}

function summarizeAnswerPlan(plan) {
  if (!plan || !Object.keys(plan).length) return {};
  return {
    intent: plan.intent,
    detected_intent: plan.detected_intent,
    strategy: plan.strategy,
    product_type: plan.product_type,
    product_family: plan.product_family,
    primary_product_id: plan.primary_product_id,
    alternative_product_ids: plan.alternative_product_ids,
    cross_sell_product_ids: plan.cross_sell_product_ids,
    excluded_product_ids: plan.excluded_product_ids,
    primary_reason: plan.primary_reason,
    alternative_reason: plan.alternative_reason,
    cross_sell_reason: plan.cross_sell_reason,
    risk_notes: plan.risk_notes,
    tradeoffs: plan.tradeoffs,
    next_best_question: plan.next_best_question,
    abstain: plan.abstain,
    abstention_reason: plan.abstention_reason,
    reasoning_steps: plan.reasoning_steps,
  };
}

function summarizeEvidence(evidence) {
  if (!evidence || !Object.keys(evidence).length) {
    return { status: "No evidence contract was attached to this response." };
  }
  return {
    primary_product_id: evidence.primary_product_id,
    allowed_product_ids: evidence.allowed_product_ids,
    rejected_product_ids: evidence.rejected_product_ids,
    missing_facts: evidence.missing_facts,
    contradictions: evidence.contradictions,
    risk_notes: evidence.risk_notes,
    follow_up_question_rules: evidence.follow_up_question_rules,
    facts_by_product: evidence.facts_by_product,
  };
}

function buildProductMap(hits) {
  const map = new Map();
  for (const hit of hits || []) {
    if (hit?.product_id) map.set(hit.product_id, hit);
  }
  return map;
}

function renderCatalogEvidence(hits, answerPlan, productMap) {
  const orderedIds = unique([
    answerPlan.primary_product_id,
    ...(answerPlan.alternative_product_ids || []),
    ...(answerPlan.cross_sell_product_ids || []),
    ...(hits || []).map(hit => hit.product_id),
  ]);
  if (!orderedIds.length) {
    el.catalogEvidence.innerHTML = `<p class="muted-text">No catalog evidence returned for this query.</p>`;
    return;
  }
  el.catalogEvidence.innerHTML = orderedIds.map(productId => {
    const hit = productMap.get(productId);
    if (!hit) {
      return `
        <article class="evidence-card missing">
          <div class="evidence-card-head">
            <h3>${escapeHtml(productId)}</h3>
            <span class="mini-pill warn">ID only</span>
          </div>
          <p class="muted-text">This product ID appears in the plan but was not included in response.hits.</p>
        </article>
      `;
    }
    const attrs = hit.attributes || {};
    const role = productRole(productId, answerPlan);
    return `
      <article class="evidence-card">
        <div class="evidence-card-head">
          <h3>${escapeHtml(hit.name || productId)}</h3>
          <span class="mini-pill">${escapeHtml(role)}</span>
        </div>
        <div class="evidence-facts">
          ${fact("Product ID", productId)}
          ${fact("Category", hit.category)}
          ${fact("Price", formatPrice(hit))}
          ${fact("Stock", hit.stock === undefined ? null : `${hit.stock} ${hit.status || ""}`.trim())}
          ${fact("Score", hit.score)}
          ${fact("Color", attrs.color || attrs.color_family)}
          ${fact("Fabric", attrs.fabric)}
          ${fact("Size", attrs.size || attrs.available_sizes)}
          ${fact("Occasion", attrs.occasion)}
          ${fact("Design ID", attrs.design_id)}
        </div>
        ${hit.snippet ? `<p class="snippet">${escapeHtml(hit.snippet)}</p>` : ""}
      </article>
    `;
  }).join("");
}

function productRole(productId, answerPlan) {
  if (answerPlan.primary_product_id === productId) return "primary";
  if ((answerPlan.alternative_product_ids || []).includes(productId)) return "alternative";
  if ((answerPlan.cross_sell_product_ids || []).includes(productId)) return "cross-sell";
  if ((answerPlan.excluded_product_ids || []).includes(productId)) return "excluded";
  return "candidate";
}

function fact(label, value) {
  if (value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length)) return "";
  return `
    <div class="evidence-fact">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(Array.isArray(value) ? value.join(", ") : String(value))}</strong>
    </div>
  `;
}

function formatPrice(hit) {
  if (hit.price === undefined || hit.price === null) return null;
  const currency = hit.currency || "BDT";
  const amount = Number(hit.price);
  if (!Number.isFinite(amount)) return `${currency} ${hit.price}`;
  return `${currency} ${amount.toLocaleString()}`;
}

function collectRejectedCandidates(trace, answerPlan) {
  const byId = new Map();
  for (const step of trace.retrieval_steps || []) {
    for (const candidate of step.rejected_candidates || []) {
      const id = candidate.product_id || candidate.record_id || candidate.name || `rejected-${byId.size + 1}`;
      const existing = byId.get(id) || { ...candidate, rejection_reasons: [] };
      const reasons = [
        ...(existing.rejection_reasons || []),
        ...(candidate.rejection_reasons || []),
      ];
      byId.set(id, {
        ...existing,
        ...candidate,
        rejection_reasons: unique(reasons),
      });
    }
  }
  for (const productId of answerPlan.excluded_product_ids || []) {
    if (!byId.has(productId)) {
      byId.set(productId, {
        product_id: productId,
        name: productId,
        rejection_reasons: ["Excluded by answer plan."],
      });
    }
  }
  const evidence = answerPlan.evidence_contract || {};
  for (const productId of evidence.rejected_product_ids || []) {
    if (!byId.has(productId)) {
      byId.set(productId, {
        product_id: productId,
        name: productId,
        rejection_reasons: ["Rejected by evidence contract."],
      });
    }
  }
  return Array.from(byId.values());
}

function renderRejectedCandidates(candidates, productMap) {
  if (!candidates.length) {
    el.rejectedCandidates.innerHTML = `<p class="muted-text">No rejected candidates were recorded for this query path.</p>`;
    return;
  }
  el.rejectedCandidates.innerHTML = candidates.map(candidate => {
    const productId = candidate.product_id || candidate.record_id || "";
    const hit = productMap.get(productId);
    const title = candidate.name || hit?.name || productId || "Rejected candidate";
    const reasons = candidate.rejection_reasons || candidate.reasons || ["Rejected by filtering, ranking, or planning."];
    return `
      <article class="rejected-card">
        <div class="evidence-card-head">
          <h3>${escapeHtml(title)}</h3>
          ${productId ? `<span class="mini-pill warn">${escapeHtml(productId)}</span>` : ""}
        </div>
        <ul>
          ${reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join("")}
        </ul>
        ${candidate.score_breakdown ? `<pre>${escapeHtml(pretty(candidate.score_breakdown))}</pre>` : ""}
      </article>
    `;
  }).join("");
}

function renderNotes(trace, rawTrace) {
  const notes = [];
  if (trace.reasoning_summary?.length) {
    notes.push(["Reasoning summary", trace.reasoning_summary]);
  }
  if (trace.missing_facts?.length) {
    notes.push(["Missing facts", trace.missing_facts]);
  }
  if (trace.retrieval_steps?.length) {
    notes.push(["Retrieval steps", trace.retrieval_steps]);
  }
  if (rawTrace?.trace_fetch_error) {
    notes.push(["Trace fetch error", rawTrace.trace_fetch_error]);
  }
  if (!notes.length) {
    el.notesView.innerHTML = `<p class="muted-text">No extra notes recorded for this path.</p>`;
    return;
  }
  el.notesView.innerHTML = notes.map(([title, value]) => `
    <section class="note-block">
      <h3>${escapeHtml(title)}</h3>
      <pre>${escapeHtml(pretty(value))}</pre>
    </section>
  `).join("");
}

function renderCounts(counts) {
  const entries = Object.entries(counts);
  if (!entries.length) {
    el.retrievalCounts.innerHTML = `<p class="muted-text">No retrieval counts recorded for this path.</p>`;
    return;
  }
  el.retrievalCounts.innerHTML = entries.map(([key, value]) => `
    <div class="count-item">
      <span>${escapeHtml(key)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `).join("");
}

function renderKv(container, data) {
  const entries = Object.entries(data || {}).filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!entries.length) {
    container.innerHTML = `<p class="muted-text">No data recorded.</p>`;
    return;
  }
  container.innerHTML = entries.map(([key, value]) => `
    <div class="kv-row">
      <span class="kv-key">${escapeHtml(key)}</span>
      <pre class="kv-value">${escapeHtml(formatValue(value))}</pre>
    </div>
  `).join("");
}

function renderList(container, items) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) {
    container.innerHTML = `<li class="muted-text">None</li>`;
    return;
  }
  container.innerHTML = list.map(item => `<li>${escapeHtml(String(item))}</li>`).join("");
}

function clearOutputs(options = {}) {
  if (!options.keepPayload) el.payloadView.textContent = "-";
  el.traceId.textContent = "-";
  el.executionPath.textContent = "-";
  el.intent.textContent = "-";
  el.latency.textContent = "-";
  el.answerEngineLabel.textContent = "-";
  el.finalAnswer.textContent = "Run a query to see the generated answer.";
  el.finalAnswer.className = "answer-box muted";
  [
    el.routeView,
    el.memoryView,
    el.imageSearchView,
    el.imageSearchHits,
    el.retrievalCounts,
    el.catalogEvidence,
    el.rejectedCandidates,
    el.answerPlanView,
    el.evidenceView,
    el.verificationView,
    el.notesView,
  ].forEach(node => { if (node) node.innerHTML = ""; });
  if (el.imageSearchPanel) el.imageSearchPanel.style.display = "none";
  el.statusBadges.innerHTML = "";
  el.whySummary.textContent = "Run a query to see the short diagnosis.";
  el.whySummary.className = "why-box muted";
  [el.retrievedIds, el.rerankedIds, el.recommendedIds, el.crossSellIds].forEach(node => { node.innerHTML = ""; });
  el.rawResponse.textContent = "-";
  el.rawTrace.textContent = "-";
}

async function apiPost(path, payload) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

async function apiGet(path, options = {}) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    headers: options.includeApiKey === false ? {} : buildHeaders(),
  });
  return parseResponse(response);
}

async function parseResponse(response) {
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

function setConnection(ok, text) {
  el.connectionDot.classList.toggle("ok", Boolean(ok));
  el.connectionDot.classList.toggle("bad", !ok);
  el.connectionText.textContent = text;
}

function formatValue(value) {
  if (typeof value === "string") return value;
  return pretty(value);
}

function pretty(value) {
  return JSON.stringify(value ?? null, null, 2);
}

function unique(values) {
  return Array.from(new Set(values.filter(Boolean)));
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
