import { readFile } from "node:fs/promises";

const DEFAULT_DATA_DOMAINS = [
  "catalog",
  "sales",
  "orders",
  "inventory_snapshots",
  "suppliers",
  "margins",
  "returns",
  "customers"
];

const config = await readJson(new URL("./config.local.json", import.meta.url));
const sample = await readJson(new URL("./data/products.json", import.meta.url));

const apiBaseUrl = normalizeBaseUrl(process.env.RAG_BASE_URL || config.apiBaseUrl);
const apiKey = process.env.RAG_API_KEY || config.apiKey;

if (!apiBaseUrl || !apiKey) {
  throw new Error(
    "Set frontend/config.local.json or RAG_BASE_URL and RAG_API_KEY before running this smoke test."
  );
}

console.log(`Testing RAG API at ${apiBaseUrl}`);

const health = await apiGet("/health", { includeApiKey: false });
console.log(`Health: ${health.status}, service=${health.service}`);

const configResponse = await optionalApiGet("/config");
if (configResponse.unavailable) {
  console.log("Config: skipped");
} else {
  console.log(
    `Config: retrieval=${configResponse.retrieval_mode}, generator=${configResponse.generator_model_name}`
  );
}

const inventoryStatus = await apiGet("/inventory/status");
console.log(
  `Status: ${inventoryStatus.status}, products=${inventoryStatus.total_items}, vector=${inventoryStatus.vector_backend}`
);

const upsertCatalog = await apiPost("/inventory/items/upsert", { items: sample.items });
console.log(`Catalog sync: upserted=${upsertCatalog.upserted_count}, total=${upsertCatalog.total_items}`);

const upsertSignals = await optionalApiPost("/inventory/business/signals/upsert", {
  signals: sample.business_signals || []
});
if (upsertSignals.unavailable) {
  console.log("Business sync: skipped because this server does not expose business-signal endpoints");
} else {
  console.log(`Business sync: upserted=${upsertSignals.upserted_count}, total=${upsertSignals.total_signals}`);
}

const rebuild = await optionalApiPost("/inventory/sync/rebuild");
if (rebuild.unavailable) {
  console.log("Sync rebuild: skipped because this server does not expose sync rebuild");
} else {
  console.log(
    `Sync rebuild: rebuilt=${rebuild.rebuilt_count}, deleted=${rebuild.deleted_vector_count}, ready=${rebuild.ready}`
  );
}

const syncStatus = await optionalApiGet("/inventory/sync/status");
if (syncStatus.unavailable) {
  console.log("Sync status: skipped because this server does not expose sync-status endpoint");
} else {
  console.log(
    `Sync status: ready=${syncStatus.ready}, catalog=${syncStatus.catalog_count}, vector=${syncStatus.vector_record_count}`
  );
}

const businessStatus = await optionalApiGet("/inventory/business/status");
if (businessStatus.unavailable) {
  console.log("Business status: skipped");
} else {
  console.log(
    `Business status: ready=${businessStatus.ready}, signals=${businessStatus.total_signals}, domains=${(businessStatus.domains_available || []).join(", ")}`
  );
}

const routeDecision = await apiPost("/inventory/route", {
  question: "which products should I restock first and why?",
  assistant_mode: "support",
  reply_style: "detailed",
  audience: "manager",
  prefer_fast_response: true,
  allow_agentic: true,
  available_data_domains: [...DEFAULT_DATA_DOMAINS]
});
console.log(
  `Route: recommended=${routeDecision.recommended_path}, fallback=${routeDecision.fallback_path}, confidence=${Math.round(
    (routeDecision.decision_confidence || 0) * 100
  )}%`
);

const normalStream = await apiStream("/inventory/ask/stream", {
  question: "show me smart watches under 250",
  assistant_mode: "sales",
  reply_style: "short",
  top_k: 6,
  answer_engine: "auto"
});
printAnswer("Normal stream", normalStream);

const scopedComparison = await apiPost("/inventory/ask", {
  question: "Between these two ErgoMesh Pro Chair records, which one should I buy?",
  assistant_mode: "sales",
  reply_style: "detailed",
  top_k: 6,
  answer_engine: "auto",
  filters: {
    product_ids: ["seed-office-004", "chair-ergomesh-pro"]
  },
  focused_product_ids: ["seed-office-004", "chair-ergomesh-pro"]
});
printAnswer("Scoped comparison", scopedComparison);
await printTraceProbe("Scoped trace", scopedComparison.trace_id, "inventory_ask");

const agenticResponse =
  routeDecision.recommended_path === "agentic"
    ? await apiStream("/inventory/agentic/ask/stream", {
        question: "which products should I restock first and why?",
        assistant_mode: "support",
        reply_style: "detailed",
        top_k: 6,
        answer_engine: "auto",
        max_reasoning_steps: 4,
        audience: "manager",
        available_data_domains: [...DEFAULT_DATA_DOMAINS]
      })
    : await apiPost("/inventory/agentic/ask", {
        question: "which products should I restock first and why?",
        assistant_mode: "support",
        reply_style: "detailed",
        top_k: 6,
        answer_engine: "auto",
        max_reasoning_steps: 4,
        audience: "manager",
        available_data_domains: [...DEFAULT_DATA_DOMAINS]
      });
printAnswer("Agentic chat", agenticResponse);
await printTraceProbe("Agentic trace", agenticResponse.trace_id, "inventory_agentic");

async function readJson(url) {
  return JSON.parse(await readFile(url, "utf-8"));
}

async function apiGet(path, options = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: buildHeaders(options)
  });
  return parseApiResponse(response);
}

async function apiPost(path, body) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  return parseApiResponse(response);
}

async function apiStream(path, body) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders({ accept: "text/event-stream" }),
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    throw await buildApiError(response);
  }
  if (!response.body) {
    throw new Error(`Streaming body missing for ${path}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundaryIndex = buffer.indexOf("\n\n");
    while (boundaryIndex >= 0) {
      const frame = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + 2);
      const parsed = parseSseFrame(frame);
      if (parsed.event === "final") {
        finalPayload = parsed.payload;
      }
      if (parsed.event === "error") {
        throw new Error(parsed.payload?.message || `Streaming request failed for ${path}`);
      }
      boundaryIndex = buffer.indexOf("\n\n");
    }

    if (done) {
      const trimmed = buffer.trim();
      if (trimmed) {
        const parsed = parseSseFrame(trimmed);
        if (parsed.event === "final") {
          finalPayload = parsed.payload;
        }
      }
      break;
    }
  }

  if (!finalPayload) {
    throw new Error(`No final SSE payload received for ${path}`);
  }
  return finalPayload;
}

function parseSseFrame(frame) {
  let event = "message";
  const dataLines = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  return {
    event,
    payload: dataLines.length ? JSON.parse(dataLines.join("\n")) : undefined
  };
}

async function optionalApiGet(path) {
  try {
    return await apiGet(path);
  } catch (error) {
    if (error.status === 404) {
      return { unavailable: true, endpoint: path, message: error.message };
    }
    throw error;
  }
}

async function optionalApiPost(path, body) {
  try {
    return await apiPost(path, body);
  } catch (error) {
    if (error.status === 404) {
      return { unavailable: true, endpoint: path, message: error.message };
    }
    throw error;
  }
}

async function buildApiError(response) {
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text || response.statusText };
  }
  const message = data?.detail?.message || data?.detail?.error || data?.message || response.statusText;
  const error = new Error(`${response.status} ${message}`);
  error.status = response.status;
  throw error;
}

async function printTraceProbe(label, traceId, traceHint) {
  if (!traceId) {
    console.log(`${label}: no trace id returned`);
    return;
  }
  const result = await apiGetFirstAvailableTrace(traceId, traceHint);
  if (result.unavailable) {
    console.log(`${label}: unavailable`);
    return;
  }
  console.log(`${label}: loaded from ${result.endpoint}`);
}

async function apiGetFirstAvailableTrace(traceId, traceHint) {
  const candidateEndpoints = buildTraceEndpointCandidates(traceId, traceHint);
  let lastUnavailable = null;
  for (const endpoint of candidateEndpoints) {
    const payload = await optionalApiGet(endpoint);
    if (!payload.unavailable) {
      return { endpoint, payload, unavailable: false };
    }
    lastUnavailable = payload;
  }
  return {
    unavailable: true,
    message: lastUnavailable?.message || "no trace endpoint available"
  };
}

function buildTraceEndpointCandidates(traceId, traceHint) {
  const encodedTraceId = encodeURIComponent(traceId);
  const preferAgentic =
    String(traceHint || "").includes("inventory_agentic") ||
    String(traceHint || "").includes("agentic") ||
    traceHint === "agentic";
  return preferAgentic
    ? [`/inventory/agentic/trace/${encodedTraceId}`, `/inventory/chat/trace/${encodedTraceId}`]
    : [`/inventory/chat/trace/${encodedTraceId}`, `/inventory/agentic/trace/${encodedTraceId}`];
}

function buildHeaders(options = {}) {
  const headers = {
    Accept: options.accept || "application/json"
  };
  if (options.includeContentType !== false) {
    headers["Content-Type"] = "application/json";
  }
  if (options.includeApiKey !== false) {
    headers["X-API-Key"] = apiKey;
  }
  return headers;
}

async function parseApiResponse(response) {
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = text ? { message: text } : {};
  }
  if (!response.ok) {
    const message = data?.detail?.message || data?.detail?.error || data?.message || response.statusText;
    const error = new Error(`${response.status} ${message}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function normalizeBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function printAnswer(label, response) {
  const productIds = [
    ...(response.recommended_product_ids || []),
    ...(response.cross_sell_product_ids || []),
    ...(response.hits || []).map((hit) => hit.product_id)
  ];
  console.log(
    `${label}: hits=${response.total_hits ?? 0}, engine=${response.answer_engine || "unknown"}, confidence=${Math.round(
      (response.confidence_score || 0) * 100
    )}%, trace=${response.trace_id || "none"}`
  );
  console.log(`Products: ${Array.from(new Set(productIds)).slice(0, 6).join(", ") || "none"}`);
  console.log(`Answer: ${String(response.answer || "").slice(0, 260)}`);
}
