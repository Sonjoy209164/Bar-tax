import { readFile } from "node:fs/promises";

const config = await readJson(new URL("./config.local.json", import.meta.url));
const sample = await readJson(new URL("./data/products.json", import.meta.url));

const apiBaseUrl = normalizeBaseUrl(process.env.RAG_BASE_URL || config.apiBaseUrl);
const apiKey = process.env.RAG_API_KEY || config.apiKey;

if (!apiBaseUrl || !apiKey) {
  throw new Error("Set frontend/config.local.json or RAG_BASE_URL and RAG_API_KEY before running this smoke test.");
}

console.log(`Testing RAG API at ${apiBaseUrl}`);

const inventoryStatus = await apiGet("/inventory/status");
console.log(`Status: ${inventoryStatus.status}, products=${inventoryStatus.total_items}, vector=${inventoryStatus.vector_backend}`);

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

const syncStatus = await optionalApiGet("/inventory/sync/status");
if (syncStatus.unavailable) {
  console.log("Sync status: skipped because this server does not expose sync-status endpoint");
} else {
  console.log(`Sync status: catalog=${syncStatus.catalog_count}, vector=${syncStatus.vector_record_count}`);
}

const normalAnswer = await apiPost("/inventory/ask", {
  question: "show me smart watches under 250",
  assistant_mode: "sales",
  reply_style: "short",
  top_k: 6,
  answer_engine: "auto"
});
printAnswer("Normal chat", normalAnswer);

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

const agenticAnswer = await apiPost("/inventory/agentic/ask", {
  question: "which products should I restock first and why?",
  assistant_mode: "support",
  reply_style: "detailed",
  top_k: 6,
  answer_engine: "auto",
  max_reasoning_steps: 4,
  available_data_domains: [
    "catalog",
    "sales",
    "orders",
    "inventory_snapshots",
    "suppliers",
    "margins",
    "returns",
    "customers"
  ]
});
printAnswer("Agentic chat", agenticAnswer);
await printTraceProbe("Agentic trace", agenticAnswer.trace_id, "inventory_agentic");

async function readJson(url) {
  return JSON.parse(await readFile(url, "utf-8"));
}

async function apiGet(path) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: buildHeaders()
  });
  return parseApiResponse(response);
}

async function apiPost(path, body) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
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
      return { unavailable: true, endpoint: path, message: error.message };
    }
    throw error;
  }
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
    ? [
        `/inventory/agentic/trace/${encodedTraceId}`,
        `/inventory/chat/trace/${encodedTraceId}`
      ]
    : [
        `/inventory/chat/trace/${encodedTraceId}`,
        `/inventory/agentic/trace/${encodedTraceId}`
      ];
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

function buildHeaders() {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-API-Key": apiKey
  };
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
